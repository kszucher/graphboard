import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOG_FILE = LOGS_DIR / "llm_calls.jsonl"


def log_llm_call(
    node_name: str,
    model: str,
    messages: list[dict[str, Any]],
    response: Any = None,
    error: str | None = None,
    graph_id: str | None = None,
) -> None:
    """Appends LLM request and response details to logs/llm_calls.jsonl."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        log_entry: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "graph_id": graph_id,
            "node_name": node_name,
            "model": model,
            "messages": messages,
            "error": error,
        }

        if response and not error:
            choice = response.choices[0]
            message_info: dict[str, Any] = {
                "role": choice.message.role,
                "content": choice.message.content,
            }
            if choice.message.tool_calls:
                message_info["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]

            log_entry["response"] = message_info

            usage = getattr(response, "usage", None)
            if usage:
                log_entry["usage"] = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                }
        else:
            log_entry["response"] = None
            log_entry["usage"] = None

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

    except Exception as e:
        logger.error(f"Failed to log LLM call: {e}", exc_info=True)


def add_feedback_to_log(graph_id: str, feedback_data: dict[str, Any]) -> bool:
    """Finds the most recent log entry for graph_id and appends feedback data to it."""
    try:
        if not LOG_FILE.exists():
            return False

        with open(LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return False

        # Search backwards to find the last LLM call for this graph_id
        target_idx = -1
        for i in range(len(lines) - 1, -1, -1):
            try:
                entry = json.loads(lines[i])
                if entry.get("graph_id") == graph_id:
                    target_idx = i
                    break
            except json.JSONDecodeError:
                continue

        if target_idx != -1:
            entry = json.loads(lines[target_idx])
            entry["feedback"] = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                **feedback_data,
            }
            lines[target_idx] = json.dumps(entry) + "\n"

            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return True

        return False
    except Exception as e:
        logger.error(f"Failed to add feedback to log: {e}", exc_info=True)
        return False
