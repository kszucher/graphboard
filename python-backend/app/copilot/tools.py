from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, TypeAdapter

from app.copilot.enums import PlannerAction
from app.graphs.nodes import _make_slot_id
from app.graphs.schemas import (
    GraphOperation,
)


class PlannerStepSchema(BaseModel):
    action: PlannerAction = Field(
        description=f"High-level operation type. Must be one of: {', '.join(a.value for a in PlannerAction)}."
    )
    description: str = Field(description="Short human-readable summary of what this step does.")
    details: dict[str, Any] | str | None = Field(
        default=None, description="Specific details (e.g. variable name, node type, source, target)."
    )


class SubmitPlanArgsSchema(BaseModel):
    graph_analysis: str = Field(
        description="Step-by-step reasoning explaining the existing graph topology, switch choices, and where the new logic logically integrates."
    )
    steps: list[PlannerStepSchema]


class PatchGraphArgsSchema(BaseModel):
    operations: list[GraphOperation] = Field(
        description="Applies a set of operations to modify the graph variables, nodes, and connections."
    )


PatchGraphArgsSchema.model_rebuild()


SUBMIT_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": "Submits a structured plan of operations to perform on the graph.",
        "parameters": SubmitPlanArgsSchema.model_json_schema(),
    },
}

PATCH_GRAPH_TOOL = {
    "type": "function",
    "function": {
        "name": "patch_graph",
        "description": "Applies a set of operations to modify the graph variables, nodes, and connections.",
        "parameters": PatchGraphArgsSchema.model_json_schema(),
    },
}


def translate_tool_call_to_operations(tool_call_args: dict[str, Any]) -> list[GraphOperation]:
    """Translates the structured operations from Groq's tool call back to app GraphOperations."""
    raw_ops = tool_call_args.get("operations", [])
    translated: list[GraphOperation] = []
    adapter: TypeAdapter[GraphOperation] = TypeAdapter(GraphOperation)

    for item in raw_ops:
        op_type = item.get("op")
        if op_type in ("connect", "disconnect"):
            source = item.get("source")
            case_label = item.get("case")
            if source:
                item["source_handle"] = _make_slot_id(source, case_label) if case_label else None
        translated.append(adapter.validate_python(item))

    return translated
