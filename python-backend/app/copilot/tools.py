from __future__ import annotations

from typing import Any

from app.constants import NodeType
from app.graphs.nodes import _make_slot_id
from app.graphs.schemas import (
    ConnectOp,
    DeleteNodeOp,
    DeleteStateVarOp,
    DisconnectOp,
    GraphOperation,
    UpsertNodeOp,
    UpsertStateVarOp,
)

# The JSON tool schema defining the planner's structured output
SUBMIT_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": "Submits a structured plan of operations to perform on the graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "graph_analysis": {
                    "type": "string",
                    "description": "Step-by-step reasoning explaining the existing graph topology, switch choices, and where the new logic logically integrates.",
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "High-level operation type (e.g. declare_variable, add_node, connect_nodes).",
                            },
                            "description": {
                                "type": "string",
                                "description": "Short human-readable summary of what this step does.",
                            },
                            "details": {
                                "type": "string",
                                "description": "Specific details (e.g. variable name, node type, source, target).",
                            },
                        },
                        "required": ["action", "description"],
                    },
                },
            },
            "required": ["graph_analysis", "steps"],
        },
    },
}

# The JSON tool schema defining the single `patch_graph` tool
PATCH_GRAPH_TOOL = {
    "type": "function",
    "function": {
        "name": "patch_graph",
        "description": "Applies a set of operations to modify the graph variables, nodes, and connections.",
        "parameters": {
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": [
                                    "upsert_state_var",
                                    "delete_state_var",
                                    "upsert_node",
                                    "delete_node",
                                    "connect",
                                    "disconnect",
                                ],
                            },
                            # upsert_state_var
                            "key": {"type": "string"},
                            "type": {"type": "string", "enum": ["boolean", "string", "number", "float"]},
                            "default_value": {"type": "string"},  # passed as python expression strings
                            "description": {"type": "string"},
                            # upsert_node
                            "node_id": {"type": "string"},
                            "node_type": {
                                "type": "string",
                                "enum": [
                                    "START",
                                    "END",
                                    "LOGICAL_ASSIGNER",
                                    "AGENTIC_ASSIGNER",
                                    "LOGICAL_SWITCH",
                                    "AGENTIC_SWITCH",
                                    "INTERRUPT",
                                ],
                            },
                            "config": {
                                "type": "object",
                                "properties": {
                                    # LOGICAL_ASSIGNER
                                    "assignments": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "target_var_key": {"type": "string"},
                                                "expression": {"type": "string"},
                                            },
                                            "required": ["target_var_key", "expression"],
                                        },
                                    },
                                    # AGENTIC_ASSIGNER
                                    "prompt": {"type": "string"},
                                    "agentic_inputs": {"type": "array", "items": {"type": "string"}},
                                    "agentic_outputs": {"type": "array", "items": {"type": "string"}},
                                    # LOGICAL_SWITCH / AGENTIC_SWITCH
                                    "slots": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "raw_string": {"type": "string"},
                                                "expression": {"type": "string"},
                                            },
                                            "required": ["raw_string"],
                                        },
                                    },
                                    # AGENTIC_SWITCH
                                    "agentic_input": {"type": "string"},
                                    # INTERRUPT
                                    "payload_vars": {"type": "array", "items": {"type": "string"}},
                                    "resume_var": {"type": "string"},
                                },
                            },
                            # connect / disconnect
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "case": {"type": "string"},  # human label representing source handle for switch nodes
                        },
                        "required": ["op"],
                    },
                }
            },
            "required": ["operations"],
        },
    },
}


def translate_tool_call_to_operations(tool_call_args: dict[str, Any]) -> list[GraphOperation]:
    """Translates the structured operations from Groq's tool call back to app GraphOperations."""
    raw_ops = tool_call_args.get("operations", [])
    translated: list[GraphOperation] = []

    for item in raw_ops:
        op_type = item.get("op")
        if op_type == "upsert_state_var":
            translated.append(
                UpsertStateVarOp(
                    op="upsert_state_var",
                    key=item["key"],
                    type=item["type"],
                    default_value=item.get("default_value"),
                    description=item.get("description"),
                )
            )
        elif op_type == "delete_state_var":
            translated.append(DeleteStateVarOp(op="delete_state_var", key=item["key"]))
        elif op_type == "upsert_node":
            config = item.get("config") or {}
            translated.append(
                UpsertNodeOp(
                    op="upsert_node",
                    node_id=item["node_id"],
                    node_type=NodeType(item["node_type"]),
                    config=config,
                )
            )
        elif op_type == "delete_node":
            translated.append(DeleteNodeOp(op="delete_node", node_id=item["node_id"]))
        elif op_type == "connect":
            source = item["source"]
            case_label = item.get("case")
            source_handle = _make_slot_id(source, case_label) if case_label else None
            translated.append(
                ConnectOp(
                    op="connect",
                    source=source,
                    source_handle=source_handle,
                    target=item["target"],
                    target_handle=None,
                )
            )
        elif op_type == "disconnect":
            source = item["source"]
            case_label = item.get("case")
            source_handle = _make_slot_id(source, case_label) if case_label else None
            translated.append(
                DisconnectOp(
                    op="disconnect",
                    source=source,
                    source_handle=source_handle,
                    target=item["target"],
                    target_handle=None,
                )
            )

    return translated
