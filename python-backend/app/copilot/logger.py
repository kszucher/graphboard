import contextvars
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"

# ContextVar to track the flow run ID within a single asynchronous task lifecycle
flow_run_id = contextvars.ContextVar("flow_run_id", default="")


def log_llm_call(
    node_name: str,
    model: str,
    messages: list[dict[str, Any]],
    response: Any = None,
    error: str | None = None,
    graph_id: str | None = None,
) -> None:
    """Logs LLM request and response details to a separate pretty-printed JSON file per flow run."""
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
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "graph_id": graph_id,
            "node_name": node_name,
            "model": model,
            "messages": logged_messages,
            "error": error,
        }

        if response and not error:
            choice = response.choices[0]
            message_info: dict[str, Any] = {
                "role": choice.message.role,
                "content": choice.message.content,
            }
            if choice.message.tool_calls:
                message_info["tool_calls"] = []
                for tc in choice.message.tool_calls:
                    args_val = tc.function.arguments
                    try:
                        args_val = json.loads(tc.function.arguments)
                    except Exception:
                        pass
                    message_info["tool_calls"].append(
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": args_val,
                            },
                        }
                    )

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

        run_name = flow_run_id.get()
        if not run_name:
            # Fallback if ContextVar is not set
            timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            run_name = f"{timestamp_str}_{graph_id or 'unknown'}"

        log_file = LOGS_DIR / f"flow_{run_name}.json"

        # Load existing run entries if the file already exists
        entries = []
        if log_file.exists():
            try:
                with open(log_file, encoding="utf-8") as f:
                    entries = json.load(f)
                    if not isinstance(entries, list):
                        entries = [entries]
            except Exception:
                entries = []

        entries.append(log_entry)

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Failed to log LLM call: {e}", exc_info=True)


def log_validation_error(graph_id: str | None, error: str) -> None:
    """Logs validation error details to the flow run's JSON file."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_entry: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "graph_id": graph_id,
            "step": "validation",
            "error": error,
        }
        run_name = flow_run_id.get()
        if not run_name:
            timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            run_name = f"{timestamp_str}_{graph_id or 'unknown'}"

        log_file = LOGS_DIR / f"flow_{run_name}.json"
        entries = []
        if log_file.exists():
            try:
                with open(log_file, encoding="utf-8") as f:
                    entries = json.load(f)
                    if not isinstance(entries, list):
                        entries = [entries]
            except Exception:
                entries = []

        entries.append(log_entry)

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to log validation error: {e}", exc_info=True)


def add_feedback_to_log(graph_id: str, feedback_data: dict[str, Any]) -> bool:
    """Obsolete feedback logger helper."""
    return False
