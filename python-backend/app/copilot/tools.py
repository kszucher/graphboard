from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.copilot.enums import PlannerAction
from app.graphs.schemas import (
    ConnectOp,
    DeleteNodeOp,
    DeleteStateVarOp,
    DisconnectOp,
    GraphOperation,
    UpsertAgenticAssignerOp,
    UpsertAgenticSwitchOp,
    UpsertInterruptOp,
    UpsertLogicalAssignerOp,
    UpsertLogicalSwitchOp,
    UpsertStateVarOp,
)


class PlannerStepSchema(BaseModel):
    action: PlannerAction = Field(
        description=f"High-level operation type. Must be one of: {', '.join(a.value for a in PlannerAction)}."
    )
    description: str = Field(description="Short human-readable summary of what this step does.")
    details: dict[str, Any] | None = Field(
        default=None, description="Specific details (e.g. variable name, node type, source, target)."
    )


class SubmitPlanArgsSchema(BaseModel):
    graph_analysis: str = Field(
        description="Step-by-step reasoning explaining the existing graph topology, switch choices, and where the new logic logically integrates."
    )
    steps: list[PlannerStepSchema]


SUBMIT_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": "Submits a structured plan of operations to perform on the graph.",
        "parameters": SubmitPlanArgsSchema.model_json_schema(),
    },
}

ALL_FLAT_TOOLS = {
    "upsert_logical_assigner": {
        "type": "function",
        "function": {
            "name": "upsert_logical_assigner",
            "description": "Add or update a logical assigner node with deterministic inline variable assignments.",
            "parameters": UpsertLogicalAssignerOp.model_json_schema(),
        },
    },
    "upsert_agentic_assigner": {
        "type": "function",
        "function": {
            "name": "upsert_agentic_assigner",
            "description": "Add or update an agentic assigner node that invokes LLMs for structured state mutations.",
            "parameters": UpsertAgenticAssignerOp.model_json_schema(),
        },
    },
    "upsert_logical_switch": {
        "type": "function",
        "function": {
            "name": "upsert_logical_switch",
            "description": "Add or update a logical switch node to evaluate deterministic expression branching logic.",
            "parameters": UpsertLogicalSwitchOp.model_json_schema(),
        },
    },
    "upsert_agentic_switch": {
        "type": "function",
        "function": {
            "name": "upsert_agentic_switch",
            "description": "Add or update an agentic switch node for LLM-driven decision routing across options.",
            "parameters": UpsertAgenticSwitchOp.model_json_schema(),
        },
    },
    "upsert_interrupt": {
        "type": "function",
        "function": {
            "name": "upsert_interrupt",
            "description": "Add or update an interrupt node to pause workflow execution for user payloads.",
            "parameters": UpsertInterruptOp.model_json_schema(),
        },
    },
    "delete_node": {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "Delete a node and all of its incoming/outgoing connections.",
            "parameters": DeleteNodeOp.model_json_schema(),
        },
    },
    "connect": {
        "type": "function",
        "function": {
            "name": "connect",
            "description": "Draw a connection edge from a source node/branch to a target node. Automatically registers branches on Switch nodes if a case label is provided.",
            "parameters": ConnectOp.model_json_schema(),
        },
    },
    "disconnect": {
        "type": "function",
        "function": {
            "name": "disconnect",
            "description": "Remove a connection edge between a source node/handle and target node/handle.",
            "parameters": DisconnectOp.model_json_schema(),
        },
    },
    "upsert_state_var": {
        "type": "function",
        "function": {
            "name": "upsert_state_var",
            "description": "Declare or update a global state variable key, type, and default value.",
            "parameters": UpsertStateVarOp.model_json_schema(),
        },
    },
    "delete_state_var": {
        "type": "function",
        "function": {
            "name": "delete_state_var",
            "description": "Delete a global state variable.",
            "parameters": DeleteStateVarOp.model_json_schema(),
        },
    },
}


def translate_tool_calls_to_operations(tool_calls: list[Any]) -> list[GraphOperation]:
    """Translates raw LLM tool call dictionaries to GraphOperation instances."""
    from pydantic import TypeAdapter

    ops: list[GraphOperation] = []
    for tc in tool_calls:
        func_name = tc.function.name
        args_str = tc.function.arguments

        import json

        try:
            args = json.loads(args_str)
        except Exception:
            args = {}

        args["op"] = func_name
        ops.append(TypeAdapter(GraphOperation).validate_python(args))
    return ops
