from app.graphs.schemas import GraphFlowData


def serialize_flow_to_code(flow: GraphFlowData) -> str:
    """Serializes GraphFlowData into a highly compact, token-efficient text representation for LLMs."""
    lines = []

    # 1. State Variables
    if flow.state:
        lines.append("Variables:")
        for var in flow.state:
            default_str = f" = {var.default_value}" if var.default_value is not None else ""
            lines.append(f"  - {var.key}: {var.type}{default_str}")
        lines.append("")

    # 2. Expressions
    if flow.expressions:
        lines.append("Expressions:")
        for expr_id, record in sorted(flow.expressions.items()):
            expr_str = record.expr.to_string()
            if expr_str.startswith("(") and expr_str.endswith(")"):
                expr_str = expr_str[1:-1]
            lines.append(f"  - {expr_id}: {expr_str}")
        lines.append("")

    # 3. Nodes
    if flow.nodes:
        lines.append("Nodes:")
        for node in flow.nodes:
            lines.extend(node.serialize_compact(expressions=flow.expressions))
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
