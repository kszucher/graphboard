from __future__ import annotations

from app.constants import NodeType
from app.graphs.schemas import GraphFlowData


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
                assignments.append({"target_var_key": a.target_var_key, "expression": a.expression or ""})
            lines.append(f"add_assigner(node_id={repr(node.id)}, assignments={assignments})")
        elif node.node_type == NodeType.AGENTIC_ASSIGNER:
            lines.append(
                f"add_agentic_assigner(node_id={repr(node.id)}, prompt={repr(node.prompt)}, "
                f"inputs={node.agentic_inputs}, outputs={node.agentic_outputs})"
            )
        elif node.node_type == NodeType.LOGICAL_SWITCH:
            slots = []
            for s in getattr(node, "slots", []):
                slots.append({"raw_string": s.raw_string, "expression": s.expression or ""})
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
