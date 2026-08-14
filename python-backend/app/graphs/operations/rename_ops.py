from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.exceptions import ValidationError
from app.graphs.schemas import GraphFlowData


class RenameNodeOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["rename_node"] = "rename_node"
    old_id: str
    new_id: str


def rename_node(flow_data: GraphFlowData, op: RenameNodeOp) -> GraphFlowData:
    node = next((n for n in flow_data.nodes if n.id == op.old_id), None)
    if not node:
        raise ValidationError(f"Node '{op.old_id}' not found.")

    if any(n.id == op.new_id for n in flow_data.nodes):
        raise ValidationError(f"Node '{op.new_id}' already exists.")

    # 1. Rename the node itself (updates its branches too)
    node.handle_node_rename(op.old_id, op.new_id)

    # 2. Update all edges referencing this node
    for edge in flow_data.edges:
        if edge.source == op.old_id:
            edge.source = op.new_id
            if edge.source_handle and edge.source_handle.startswith(f"{op.old_id}_"):
                edge.source_handle = edge.source_handle.replace(f"{op.old_id}_", f"{op.new_id}_", 1)
        if edge.target == op.old_id:
            edge.target = op.new_id
            if edge.target_handle and edge.target_handle.startswith(f"{op.old_id}_"):
                edge.target_handle = edge.target_handle.replace(f"{op.old_id}_", f"{op.new_id}_", 1)

    return flow_data


class RenameVariableOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["rename_variable"] = "rename_variable"
    old_key: str
    new_key: str


def rename_variable(flow_data: GraphFlowData, op: RenameVariableOp) -> GraphFlowData:
    var_schema = next((v for v in flow_data.state if v.key == op.old_key), None)
    if not var_schema:
        raise ValidationError(f"Variable '{op.old_key}' not found in the graph state.")

    if any(v.key == op.new_key for v in flow_data.state):
        raise ValidationError(f"Variable '{op.new_key}' already exists in the graph state.")

    # 1. Rename the variable schema key
    var_schema.key = op.new_key

    # 2. Cascade update to all expressions
    from app.graphs.expressions import rename_expression_variables

    for expr_record in flow_data.expressions.values():
        expr_record.expr = rename_expression_variables(expr_record.expr, op.old_key, op.new_key) or ""

    # 3. Cascade update to all node structures
    for node in flow_data.nodes:
        # Logical Assigner
        if hasattr(node, "assignments"):
            for a in getattr(node, "assignments", []):
                if a.target_var_key == op.old_key:
                    a.target_var_key = op.new_key
        # Agentic Assigner
        if hasattr(node, "agentic_inputs"):
            inputs = getattr(node, "agentic_inputs", [])
            node.agentic_inputs = [op.new_key if x == op.old_key else x for x in inputs]
        if hasattr(node, "agentic_outputs"):
            outputs = getattr(node, "agentic_outputs", [])
            node.agentic_outputs = [op.new_key if x == op.old_key else x for x in outputs]
        # RAG Retriever
        if hasattr(node, "query_var") and getattr(node, "query_var", "") == op.old_key:
            node.query_var = op.new_key
        if hasattr(node, "context_output_var") and getattr(node, "context_output_var", "") == op.old_key:
            node.context_output_var = op.new_key
        # Agentic Switch
        if hasattr(node, "agentic_input") and getattr(node, "agentic_input", "") == op.old_key:
            node.agentic_input = op.new_key
        # Interrupt
        if hasattr(node, "payload_vars"):
            payload = getattr(node, "payload_vars", [])
            node.payload_vars = [op.new_key if x == op.old_key else x for x in payload]
        if hasattr(node, "resume_var") and getattr(node, "resume_var", "") == op.old_key:
            node.resume_var = op.new_key

    return flow_data
