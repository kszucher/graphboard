from __future__ import annotations

from typing import Any, TypedDict

from app.modules.copilot.planner_schemas import ApplyGraphPlan
from app.modules.graphs.operations.schemas import GraphUpdateInput


class CopilotState(TypedDict, total=False):
    trace_id: str
    graph_id: str
    user_prompt: str
    serialized_state: str
    initial_flow_data: dict[str, Any]
    plan: ApplyGraphPlan | None
    operations: GraphUpdateInput | None
    validation_error: str | None
    applied: bool | None
    retry_count: int | None
    messages: list[dict[str, Any]] | None
