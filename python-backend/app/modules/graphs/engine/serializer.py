from __future__ import annotations

import json

from app.modules.graphs.schemas import GraphFlowData


def serialize_flow_to_code(flow: GraphFlowData) -> str:
    """Serializes GraphFlowData into clean, structured YAML format matching the tool schemas."""
    lines: list[str] = []

    # 1. State Variables
    if flow.state:
        lines.append("State:")
        for var in flow.state:
            def_val = f", default: {json.dumps(var.default_value)}" if var.default_value is not None else ""
            desc = f", description: {json.dumps(var.description)}" if var.description else ""
            lines.append(f'  - {{ key: "{var.key}", type: "{var.type}"{def_val}{desc} }}')
        lines.append("")

    # Helper: Get linear successor target
    def get_target(node_id: str) -> str | None:
        edge = next((e for e in flow.edges if e.source == node_id and not e.source_handle), None)
        return edge.target if edge else None

    # 2. Flow Nodes
    lines.append("Flow:")
    start_edge = next((e for e in flow.edges if e.source == "start"), None)
    if start_edge:
        lines.append(f"  start -> {start_edge.target}")

    for node in flow.nodes:
        ntype = node.node_type.value
        nid = node.id

        if ntype in {"START", "END"}:
            continue

        tgt = get_target(nid)
        tgt_str = f', target: "{tgt}"' if tgt else ""

        if ntype == "LOGICAL_ASSIGNER":
            lines.append(f"  {nid} [LOGICAL_ASSIGNER]{tgt_str}:")
            lines.append("    assignments:")
            for a in getattr(node, "assignments", []):
                expr = a.expression
                expr_str = f'"{expr}"' if isinstance(expr, str) else json.dumps(expr)
                lines.append(f'      - {{ target_var_key: "{a.target_var_key}", expression: {expr_str} }}')

        elif ntype == "AGENTIC_ASSIGNER":
            prompt_escaped = getattr(node, "prompt", "").replace('"', '\\"')
            inputs = json.dumps(getattr(node, "agentic_inputs", []))
            outputs_raw = getattr(node, "agentic_outputs", [])
            outputs_str = json.dumps([{"key": o, "type": "string"} for o in outputs_raw])
            lines.append(f"  {nid} [AGENTIC_ASSIGNER]{tgt_str}:")
            lines.append(f'    prompt: "{prompt_escaped}"')
            lines.append(f"    inputs: {inputs}")
            lines.append(f"    outputs: {outputs_str}")

        elif ntype == "RAG_RETRIEVER":
            q = getattr(node, "query_var", "")
            out = getattr(node, "context_output_var", "")
            kb = getattr(node, "knowledge_base", "")
            top_k = getattr(node, "top_k", 3)
            lines.append(f"  {nid} [RAG_RETRIEVER]{tgt_str}:")
            lines.append(f'    query_var: "{q}", context_output_var: "{out}", knowledge_base: "{kb}", top_k: {top_k}')

        elif ntype == "INTERRUPT":
            payload = json.dumps(getattr(node, "payload_vars", []))
            resume = getattr(node, "resume_var", "")
            lines.append(f"  {nid} [INTERRUPT]{tgt_str}:")
            lines.append(f'    resume_var: "{resume}", payload_vars: {payload}')

        elif ntype == "LOGICAL_SWITCH":
            lines.append(f"  {nid} [LOGICAL_SWITCH]:")
            for b in getattr(node, "branches", []):
                edge = next((e for e in flow.edges if e.source == nid and e.source_handle == b.id), None)
                br_target = edge.target if edge else "end"
                cond_val = getattr(b, "expression", None)
                if cond_val is not None and cond_val is not True:
                    lines.append(f'    - branch "{b.label}": "{cond_val}" -> {br_target}')
                else:
                    lines.append(f'    - branch "{b.label}": (default) -> {br_target}')

        elif ntype == "AGENTIC_SWITCH":
            inp = getattr(node, "agentic_input", "")
            lines.append(f"  {nid} [AGENTIC_SWITCH]:")
            lines.append(f'    agentic_input: "{inp}"')
            for b in getattr(node, "branches", []):
                edge = next((e for e in flow.edges if e.source == nid and e.source_handle == b.id), None)
                br_target = edge.target if edge else "end"
                lines.append(f'    - case "{b.label}" -> {br_target}')

    return "\n".join(lines)
