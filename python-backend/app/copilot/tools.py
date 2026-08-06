from __future__ import annotations

from typing import Any

from app.constants import NodeType
from app.graphs.mutations import _make_slot_id
from app.graphs.schemas import (
    ConnectOp,
    DeleteNodeOp,
    DeleteStateVarOp,
    DisconnectOp,
    GraphFlowData,
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
                }
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



def format_expression_as_string(node: Any) -> str:
    """Converts a visual AST Expression back into a clean python expression string."""
    if not node:
        return ""
    kind = getattr(node, "kind", None)
    if kind == "literal":
        return repr(getattr(node, "value", None))
    if kind == "stateRef":
        return getattr(node, "varKey", "")
    if kind == "binaryOp":
        left = format_expression_as_string(getattr(node, "left", None))
        right = format_expression_as_string(getattr(node, "right", None))
        return f"({left} {getattr(node, 'op', '')} {right})"
    if kind == "unaryOp":
        expr = format_expression_as_string(getattr(node, "expr", None))
        return f"({getattr(node, 'op', '')} {expr})"
    return ""


def serialize_flow_to_code(flow: GraphFlowData) -> str:
    """Serializes GraphFlowData into a human-readable mock Python representation for LLMs."""
    lines = []

    # 1. State Variables
    for var in flow.state:
        desc_str = f", description={repr(var.description)}" if var.description else ""
        default_str = f", default_value={repr(var.default_value)}" if var.default_value is not None else ""
        lines.append(f"declare_variable(key={repr(var.key)}, type={repr(var.type)}{default_str}{desc_str})")

    if flow.state:
        lines.append("")

    # 2. Nodes
    for node in flow.nodes:
        if node.node_type == NodeType.START:
            lines.append(f"add_start(node_id={repr(node.id)})")
        elif node.node_type == NodeType.END:
            lines.append(f"add_end(node_id={repr(node.id)})")
        elif node.node_type == NodeType.LOGICAL_ASSIGNER:
            assignments = []
            for a in getattr(node, "assignments", []):
                expr_str = format_expression_as_string(a.expression)
                assignments.append({"target_var_key": a.target_var_key, "expression": expr_str})
            lines.append(f"add_assigner(node_id={repr(node.id)}, assignments={assignments})")
        elif node.node_type == NodeType.AGENTIC_ASSIGNER:
            lines.append(
                f"add_agentic_assigner(node_id={repr(node.id)}, prompt={repr(node.prompt)}, "
                f"inputs={node.agentic_inputs}, outputs={node.agentic_outputs})"
            )
        elif node.node_type == NodeType.LOGICAL_SWITCH:
            slots = []
            for s in getattr(node, "slots", []):
                expr_str = format_expression_as_string(s.expression)
                slots.append({"raw_string": s.raw_string, "expression": expr_str})
            lines.append(f"add_switch(node_id={repr(node.id)}, slots={slots})")
        elif node.node_type == NodeType.AGENTIC_SWITCH:
            slots = [{"raw_string": s.raw_string} for s in getattr(node, "slots", [])]
            lines.append(
                f"add_agentic_switch(node_id={repr(node.id)}, agentic_input={repr(node.agentic_input)}, slots={slots})"
            )
        elif node.node_type == NodeType.INTERRUPT:
            lines.append(
                f"add_interrupt(node_id={repr(node.id)}, payload_vars={node.payload_vars}, resume_var={repr(node.resume_var)})"
            )

    if flow.nodes:
        lines.append("")

    # 3. Connections
    for edge in flow.edges:
        source_node = next((n for n in flow.nodes if n.id == edge.source), None)
        case_val = None
        if source_node and hasattr(source_node, "slots") and edge.source_handle:
            slot = next((s for s in getattr(source_node, "slots", []) if s.id == edge.source_handle), None)
            if slot:
                case_val = slot.raw_string

        case_str = f", case={repr(case_val)}" if case_val else ""
        lines.append(f"connect(source={repr(edge.source)}, target={repr(edge.target)}{case_str})")

    return "\n".join(lines)


def sort_operations_by_dependency(ops: list[GraphOperation]) -> list[GraphOperation]:
    """Sorts operations: State declarations -> Node additions/deletes -> Connections/disconnects."""
    state_ops = []
    node_ops = []
    connect_ops = []
    delete_ops = []  # Run deletes first to avoid constraints

    for op in ops:
        if op.op in ("delete_node", "delete_state_var", "disconnect"):
            delete_ops.append(op)
        elif op.op == "upsert_state_var":
            state_ops.append(op)
        elif op.op == "upsert_node":
            node_ops.append(op)
        elif op.op == "connect":
            connect_ops.append(op)

    return delete_ops + state_ops + node_ops + connect_ops


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
