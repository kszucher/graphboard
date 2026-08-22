from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
LOGS_DIR = BASE_DIR / "logs" / "copilot_runs"


def _append_to_log_file(log_file: Path, entry: dict[str, Any]) -> None:
    entries = []
    if log_file.exists():
        try:
            with open(log_file, encoding="utf-8") as f:
                entries = json.load(f)
                if not isinstance(entries, list):
                    entries = [entries]
        except Exception:
            entries = []
    entries.append(entry)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def log_llm_call(
    trace_id: str,
    node_name: str,
    model: str,
    messages: list[dict[str, Any]],
    response: Any = None,
    error: str | None = None,
    graph_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    initial_flow: dict[str, Any] | None = None,
) -> None:
    """Logs full LLM request and response details to flow run JSON file."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        logged_messages = []
        for msg in messages:
            msg_copy = dict(msg)
            content = msg_copy.get("content")
            if isinstance(content, str) and "\n" in content:
                msg_copy["content"] = content.split("\n")
            logged_messages.append(msg_copy)

        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "graph_id": graph_id,
            "node_name": node_name,
            "model": model,
            "initial_flow": initial_flow,
            "messages": logged_messages,
            "tools": tools,
            "error": error,
        }

        if response and not error:
            function_calls = getattr(response, "function_calls", None)
            text_content = None
            thoughts = []
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                content = getattr(candidates[0], "content", None)
                parts = getattr(content, "parts", None) or []
                for part in parts:
                    if getattr(part, "thought", False):
                        if getattr(part, "text", None):
                            thoughts.append(part.text)

            if not function_calls:
                try:
                    text_content = response.text
                except Exception:
                    pass

            message_info: dict[str, Any] = {
                "role": "model",
                "content": text_content,
            }
            if thoughts:
                message_info["thoughts"] = thoughts
            if function_calls:
                message_info["tool_calls"] = [
                    {
                        "id": f"call_{idx}",
                        "type": "function",
                        "function": {
                            "name": fc.name,
                            "arguments": fc.args,
                        },
                    }
                    for idx, fc in enumerate(function_calls)
                ]
            log_entry["response"] = message_info
            usage = getattr(response, "usage_metadata", None)
            if usage:
                log_entry["usage"] = {
                    "prompt_tokens": usage.prompt_token_count,
                    "completion_tokens": usage.candidates_token_count,
                    "total_tokens": usage.total_token_count,
                }
        else:
            log_entry["response"] = None
            log_entry["usage"] = None

        log_file = LOGS_DIR / f"flow_{trace_id}_full.json"
        _append_to_log_file(log_file, log_entry)

    except Exception as e:
        logger.error(f"Failed to log LLM call: {e}", exc_info=True)
