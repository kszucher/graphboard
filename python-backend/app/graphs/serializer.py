from app.constants import NodeType
from app.graphs.schemas import GraphFlowData


def serialize_flow_to_code(flow: GraphFlowData) -> str:
    """Serializes GraphFlowData into a highly compact, token-efficient text representation for LLMs."""
    lines = []

    # 1. State Variables
    if flow.state:
        lines.append("Variables:")
        for var in flow.state:
            default_str = f" [default: {var.default_value}]" if var.default_value is not None else ""
            desc_str = f" ({var.description})" if var.description else ""
            lines.append(f"  - {var.key}: {var.type}{default_str}{desc_str}")
        lines.append("")

    # 2. Nodes
    if flow.nodes:
        lines.append("Nodes:")
        for node in flow.nodes:
            lines.append(f"  - {node.id} [{node.node_type.value}]")

            if node.node_type == NodeType.LOGICAL_ASSIGNER:
                for a in getattr(node, "assignments", []):
                    lines.append(f"    {a.target_var_key} = {a.expression or ''}")
            elif node.node_type == NodeType.AGENTIC_ASSIGNER:
                lines.append(f"    prompt: {node.prompt}")
                if node.agentic_inputs:
                    lines.append(f"    in: {', '.join(node.agentic_inputs)}")
                if node.agentic_outputs:
                    lines.append(f"    out: {', '.join(node.agentic_outputs)}")
            elif node.node_type == NodeType.LOGICAL_SWITCH:
                branches = []
                for b in getattr(node, "branches", []):
                    branches.append(f"{b.label} ({b.expression or ''})")
                if branches:
                    lines.append(f"    branches: {', '.join(branches)}")
            elif node.node_type == NodeType.AGENTIC_SWITCH:
                if node.agentic_input:
                    lines.append(f"    in: {node.agentic_input}")
                branches = [b.label for b in getattr(node, "branches", [])]
                if branches:
                    lines.append(f"    branches: {', '.join(branches)}")
            elif node.node_type == NodeType.INTERRUPT:
                if node.payload_vars:
                    lines.append(f"    payload: {', '.join(node.payload_vars)}")
                if node.resume_var:
                    lines.append(f"    resume: {node.resume_var}")
        lines.append("")

    # 3. Edges
    if flow.edges:
        lines.append("Edges:")
        for edge in flow.edges:
            source_node = next((n for n in flow.nodes if n.id == edge.source), None)
            case_val = None
            if source_node and hasattr(source_node, "branches") and edge.source_handle:
                branch = next((b for b in getattr(source_node, "branches", []) if b.id == edge.source_handle), None)
                if branch:
                    case_val = branch.label

            if case_val:
                lines.append(f"  - {edge.source} -[{case_val}]-> {edge.target}")
            else:
                lines.append(f"  - {edge.source} -> {edge.target}")

    return "\n".join(lines)
