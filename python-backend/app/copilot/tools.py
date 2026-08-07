from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from app.graphs.nodes import _make_slot_id
from app.graphs.schemas import (
    GraphOperation,
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
