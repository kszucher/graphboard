from __future__ import annotations

import hashlib
import logging
import os
import random
import time

import httpx
from sqlalchemy import Engine, create_engine, text

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cache connection engine at module level
_engine: Engine | None = None


def get_sync_engine() -> Engine:
    global _engine
    if _engine is None:
        db_url = settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if not db_url:
            raise ValueError("Database URL is not configured.")
        _engine = create_engine(db_url, pool_pre_ping=True)
    return _engine


def get_huggingface_embedding(text_to_embed: str) -> list[float]:
    hf_key = os.environ.get("HF_API_KEY", "")
    url = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"

    headers = {}
    if hf_key:
        headers["Authorization"] = f"Bearer {hf_key}"

    payload = {"inputs": text_to_embed}

    try:
        with httpx.Client(timeout=5.0) as client:
            for _attempt in range(3):
                response = client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, list) and len(result) > 0:
                        if isinstance(result[0], list):
                            return result[0]
                        return result
                    raise ValueError(f"Unexpected response format from Hugging Face: {result}")
                elif response.status_code == 503:
                    err_data = response.json()
                    sleep_time = min(err_data.get("estimated_time", 2.0), 3.0)
                    time.sleep(sleep_time)
                    continue
                else:
                    raise RuntimeError(f"Hugging Face request failed: {response.status_code}")
    except Exception as e:
        logger.debug("Using deterministic pseudo-embedding fallback: %s", e)
        # Fallback to a fully deterministic 384-dim pseudo-embedding based on the text hash.
        hasher = hashlib.md5(text_to_embed.encode("utf-8"))
        seed = int(hasher.hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(384)]

    # Final fallback if retries expired
    hasher = hashlib.md5(text_to_embed.encode("utf-8"))
    seed = int(hasher.hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(384)]


def retrieve_documents(query: str, kb: str = "trivia", top_k: int = 3) -> list[str]:
    """Retrieves document chunks matching the query string using pgvector cosine distance."""
    if not query or not query.strip():
        return []

    try:
        # 1. Embed query
        query_vector = get_huggingface_embedding(query)

        # 2. Search Postgres index
        engine = get_sync_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT text 
                    FROM document_chunks 
                    WHERE knowledge_base = :kb 
                    ORDER BY embedding <=> CAST(:query_vector AS vector) 
                    LIMIT :top_k
                """),
                {"kb": kb.lower(), "query_vector": str(query_vector), "top_k": top_k},
            )
            return [row[0] for row in result]
    except Exception as e:
        return [f"RAG Retrieval failed: {str(e)}"]
