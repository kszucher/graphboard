from __future__ import annotations

from app.graphs.schemas import GraphFlowData


def serialize_flow_to_code(flow: GraphFlowData) -> str:
    """Serializes GraphFlowData into a highly compact, token-efficient text representation for LLMs.

    It represents variables with Python type hints and nodes as functional Python assignments
    with inline edge routing.
    """
    lines = []

    # 1. State Variables
    if flow.state:
        lines.append("State:")
        type_mapping = {
            "number": "int",
            "string": "str",
            "boolean": "bool",
            "array": "list",
            "object": "dict",
        }
        for var in flow.state:
            mapped_type = type_mapping.get(var.type.lower(), var.type)
            default_str = ""
            if var.default_value is not None:
                default_str = f" = {repr(var.default_value)}"
            lines.append(f"  {var.key}: {mapped_type}{default_str}")
        lines.append("")

    # Helper: Find standard successor target for a node (without source handle)
    def get_successor(node_id: str) -> str:
        edge = next((e for e in flow.edges if e.source == node_id and not e.source_handle), None)
        return f" -> {edge.target}" if edge else ""

    # 2. Flow Nodes
    if flow.nodes:
        lines.append("Flow:")
        for node in flow.nodes:
            node_type = node.node_type.value

            # A. Start Node
            if node_type == "START":
                lines.append(f"  start(){get_successor(node.id)}")

            # B. End Node
            elif node_type == "END":
                lines.append("  end()")

            # C. Logical Assigner (Assignments mapped inline)
            elif node_type == "LOGICAL_ASSIGNER":
                assignments_str_list = []
                for a in getattr(node, "assignments", []):
                    expr_str = ""
                    if a.expr_id and flow.expressions and a.expr_id in flow.expressions:
                        expr_str = flow.expressions[a.expr_id].expr
                        if expr_str.startswith("(") and expr_str.endswith(")"):
                            expr_str = expr_str[1:-1]
                    assignments_str_list.append(f"{a.target_var_key}={expr_str}")
                assignments_str = ", ".join(assignments_str_list)
                lines.append(f"  {node.id}: LOGICAL_ASSIGNER({assignments_str}){get_successor(node.id)}")

            # D. Agentic Assigner (Functional call representation)
            elif node_type == "AGENTIC_ASSIGNER":
                inputs = ", ".join(getattr(node, "agentic_inputs", []))
                outputs = ", ".join(getattr(node, "agentic_outputs", []))
                prompt = getattr(node, "prompt", "")
                prompt_escaped = prompt.replace('"', '\\"')
                lines.append(f'  {outputs} = {node.id}({inputs}, prompt="{prompt_escaped}"){get_successor(node.id)}')

            # E. RAG Retriever (Functional call representation)
            elif node_type == "RAG_RETRIEVER":
                query = getattr(node, "query_var", "")
                out = getattr(node, "context_output_var", "")
                kb = getattr(node, "knowledge_base", "")
                top_k = getattr(node, "top_k", 3)
                lines.append(f'  {out} = {node.id}(query={query}, kb="{kb}", top_k={top_k}){get_successor(node.id)}')

            # F. Interrupt Node
            elif node_type == "INTERRUPT":
                payload = ", ".join(getattr(node, "payload_vars", []))
                resume = getattr(node, "resume_var", "")
                lines.append(f"  {resume} = {node.id}({payload}){get_successor(node.id)}")

            # G. Logical Switch
            elif node_type == "LOGICAL_SWITCH":
                branches_str_list = []
                for b in getattr(node, "branches", []):
                    edge = next((e for e in flow.edges if e.source == node.id and e.source_handle == b.id), None)
                    target_str = f" -> {edge.target}" if edge else ""
                    expr_str = ""
                    if b.expr_id and flow.expressions and b.expr_id in flow.expressions:
                        expr_str = flow.expressions[b.expr_id].expr
                        if expr_str.startswith("(") and expr_str.endswith(")"):
                            expr_str = expr_str[1:-1]
                    branches_str_list.append(f"{b.label}={expr_str}{target_str}")
                branches_str = ", ".join(branches_str_list)
                lines.append(f"  {node.id}: LOGICAL_SWITCH({branches_str})")

            # H. Agentic Switch
            elif node_type == "AGENTIC_SWITCH":
                agentic_input = getattr(node, "agentic_input", "")
                branches_str_list = []
                for b in getattr(node, "branches", []):
                    edge = next((e for e in flow.edges if e.source == node.id and e.source_handle == b.id), None)
                    target_str = f" -> {edge.target}" if edge else ""
                    branches_str_list.append(f"{b.label}{target_str}")
                branches_str = ", ".join(branches_str_list)
                lines.append(f"  {node.id}: AGENTIC_SWITCH(in={agentic_input}, {branches_str})")

    return "\n".join(lines)
