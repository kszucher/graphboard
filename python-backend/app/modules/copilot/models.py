from __future__ import annotations

from typing import Any, TypedDict


class CopilotState(TypedDict):
    trace_id: str
    graph_id: str
    user_prompt: str
    serialized_state: str
    initial_flow_data: dict[str, Any]
    tool_calls: list[dict[str, Any]] | None
    operations: dict[str, Any] | None
    validation_error: str | None
    applied: bool | None
    retry_count: int | None
    messages: list[dict[str, Any]] | None
