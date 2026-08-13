from __future__ import annotations

from typing import Any, TypedDict


class CopilotState(TypedDict):
    trace_id: str
    graph_id: str
    user_prompt: str
    serialized_state: str
    initial_flow_data: dict[str, Any]
    agent_checklist: dict[str, Any] | None

    plan: list[dict[str, Any]] | None
    plan_approved: bool | None

    operations: list[dict[str, Any]] | None
    validation_error: str | None

    apply_approved: bool | None
    applied: bool | None
