from __future__ import annotations

from sqlalchemy import text

from app.modules.graphs.rag_helper import get_huggingface_embedding, get_sync_engine

# Sample document chunks to seed the RAG knowledge base
SEED_DATA = {
    "trivia": [
        "The planet Venus has a runaway greenhouse effect making its surface hot enough to melt lead.",
        "Mars has the largest volcano in the Solar System named Olympus Mons, which is three times the height of Mount Everest.",
        "A day on Venus is longer than a year on Venus; it takes 243 Earth days to rotate once on its axis.",
        "Voyager 1 is the most distant human-made object from Earth, launched in 1977 and currently in interstellar space.",
        "Neutron stars are so dense that a single teaspoon of their material would weigh about 6 billion tons on Earth.",
        "The Great Pyramid of Giza was the tallest human-made structure for over 3,800 years until Lincoln Cathedral was built in 1311.",
        "Julius Caesar was assassinated on the Ides of March (March 15) in 44 BC by a group of Roman senators.",
        "The Magna Carta was signed by King John at Runnymede in 1215, establishing the principle that everyone is subject to the law.",
        "The Aztec Empire fell in 1521 after Hernán Cortés captured their capital city Tenochtitlan.",
    ]
}


def seed_database() -> None:
    engine = get_sync_engine()

    print("Clearing existing document chunks...")
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM document_chunks;"))
        conn.commit()

    print("Generating embeddings and seeding trivia facts...")
    for kb, chunks in SEED_DATA.items():
        for chunk in chunks:
            print(f"Embedding: '{chunk[:40]}...'")
            embedding = get_huggingface_embedding(chunk)

            with engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO document_chunks (knowledge_base, text, embedding)
                        VALUES (:kb, :text, CAST(:embedding AS vector))
                    """),
                    {"kb": kb.lower(), "text": chunk, "embedding": str(embedding)},
                )
                conn.commit()
    print("Database seeding completed successfully!")


if __name__ == "__main__":
    # Ensure environment variables are loaded
    from dotenv import load_dotenv

    load_dotenv()
    seed_database()
