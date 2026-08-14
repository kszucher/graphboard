from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.constants import NodeType
from app.core.exceptions import ValidationError
from app.modules.graphs.schemas import DefinerVariableSchema, ExpressionRecord, GraphFlowData, VariableType


# Helper to get default values for state variables
def get_default_value_for_type(t: str) -> Any:
    if t.lower() in ("boolean", "bool"):
        return False
    if t.lower() in ("number", "int", "float"):
        return 0
    return ""


# Helper to infer expression types statically
def infer_expression_type(expr_str: str) -> tuple[VariableType, Any]:
    import ast

    try:
        tree = ast.parse(expr_str, mode="eval")
        node = tree.body
        if isinstance(node, ast.Compare):
            return "boolean", False
        if isinstance(node, ast.BoolOp):
            return "boolean", False
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return "boolean", False
        if isinstance(node, ast.Constant):
            val = node.value
            if isinstance(val, bool):
                return "boolean", val
            if isinstance(val, (int, float)):
                return "number", val
            if isinstance(val, str):
                return "string", val
        return "string", ""
    except Exception:
        return "string", ""


# Helper to auto-declare variable on write references
def auto_declare_variable(
    flow_data: GraphFlowData,
    key: str,
    var_type: VariableType,
    default_value: Any = None,
    description: str | None = None,
) -> None:
    if not any(v.key == key for v in flow_data.state):
        new_var = DefinerVariableSchema(
            id=str(uuid.uuid4()), key=key, type=var_type, default_value=default_value, description=description
        )
        flow_data.state.append(new_var)


# Helper to validate read reference initialization
def ensure_variables_initialized(flow_data: GraphFlowData, referenced_vars: set[str], node_id: str) -> None:
    valid_keys = {v.key for v in flow_data.state}
    for var in referenced_vars:
        if var not in valid_keys:
            raise ValidationError(
                f"Variable '{var}' is referenced in node '{node_id}' but has never been initialized or declared. "
                "Please initialize it first in an assignment or starting node."
            )


# 1. LOGICAL_ASSIGNER
class AssignmentSchema(BaseModel):
    target_var_key: str
    expression: str


class UpsertLogicalAssignerOp(BaseModel):
    op: Literal["upsert_logical_assigner"] = "upsert_logical_assigner"
    node_id: str
    assignments: list[AssignmentSchema] = Field(default_factory=list)


def upsert_logical_assigner(flow_data: GraphFlowData, op: UpsertLogicalAssignerOp) -> GraphFlowData:
    from app.modules.graphs.expressions import get_expression_variables
    from app.modules.graphs.expressions.translator import translate_polars_to_python
    from app.modules.graphs.nodes.logical_assigner import LogicalAssignerNode, LogicalAssignmentSchema

    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if node:
        if node.node_type != NodeType.LOGICAL_ASSIGNER:
            raise ValidationError(f"Node '{op.node_id}' already exists but is not a LOGICAL_ASSIGNER.")
    else:
        node = LogicalAssignerNode(id=op.node_id)
        flow_data.nodes.append(node)

    assignments = []
    for a in op.assignments:
        python_expr = translate_polars_to_python(a.expression, valid_variables=None)
        referenced = get_expression_variables(python_expr)
        ensure_variables_initialized(flow_data, referenced, op.node_id)

        inferred_type, inferred_default = infer_expression_type(python_expr)
        auto_declare_variable(flow_data, a.target_var_key, inferred_type, inferred_default)

        expr_id = f"expr_{op.node_id}_{a.target_var_key}"
        flow_data.expressions[expr_id] = ExpressionRecord(id=expr_id, expr=python_expr)

        assignments.append(
            LogicalAssignmentSchema(id=str(uuid.uuid4()), target_var_key=a.target_var_key, expr_id=expr_id)
        )

    node.assignments = assignments
    return flow_data


# 2. AGENTIC_ASSIGNER
class VariableTypeSchema(BaseModel):
    key: str
    type: VariableType
    description: str = ""


class UpsertAgenticAssignerOp(BaseModel):
    op: Literal["upsert_agentic_assigner"] = "upsert_agentic_assigner"
    node_id: str
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[VariableTypeSchema] = Field(default_factory=list)
    prompt: str = ""


def upsert_agentic_assigner(flow_data: GraphFlowData, op: UpsertAgenticAssignerOp) -> GraphFlowData:
    import re

    from app.modules.graphs.nodes.agentic_assigner import AgenticAssignerNode

    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if node:
        if node.node_type != NodeType.AGENTIC_ASSIGNER:
            raise ValidationError(f"Node '{op.node_id}' already exists but is not an AGENTIC_ASSIGNER.")
    else:
        node = AgenticAssignerNode(id=op.node_id)
        flow_data.nodes.append(node)

    # Auto-infer variables referenced in the prompt that match valid state keys
    valid_keys = {v.key for v in flow_data.state if v.key}
    prompt_vars = {var for var in re.findall(r"\{([a-zA-Z0-9_]+)\}", op.prompt or "") if var in valid_keys}
    merged_inputs = list(set(op.agentic_inputs) | prompt_vars)

    ensure_variables_initialized(flow_data, set(merged_inputs), op.node_id)

    for out in op.agentic_outputs:
        default_val = get_default_value_for_type(out.type)
        auto_declare_variable(flow_data, out.key, out.type, default_val, out.description)

    node.agentic_inputs = merged_inputs
    node.agentic_outputs = [out.key for out in op.agentic_outputs]
    node.prompt = op.prompt
    return flow_data


# 3. RAG_RETRIEVER
class UpsertRagRetrieverOp(BaseModel):
    op: Literal["upsert_rag_retriever"] = "upsert_rag_retriever"
    node_id: str
    query_var: str
    context_output_var: str
    knowledge_base: str = "trivia"
    top_k: int = 3


def upsert_rag_retriever(flow_data: GraphFlowData, op: UpsertRagRetrieverOp) -> GraphFlowData:
    from app.modules.graphs.nodes.rag_retriever import RagRetrieverNode

    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if node:
        if node.node_type != NodeType.RAG_RETRIEVER:
            raise ValidationError(f"Node '{op.node_id}' already exists but is not a RAG_RETRIEVER.")
    else:
        node = RagRetrieverNode(id=op.node_id)
        flow_data.nodes.append(node)

    ensure_variables_initialized(flow_data, {op.query_var}, op.node_id)
    auto_declare_variable(flow_data, op.context_output_var, "string", "")

    node.query_var = op.query_var
    node.context_output_var = op.context_output_var
    node.knowledge_base = op.knowledge_base
    node.top_k = op.top_k
    return flow_data


# 4. LOGICAL_SWITCH
class SwitchBranchSchema(BaseModel):
    label: str
    expression: str


class UpsertLogicalSwitchOp(BaseModel):
    op: Literal["upsert_logical_switch"] = "upsert_logical_switch"
    node_id: str
    branches: list[SwitchBranchSchema] = Field(default_factory=list)


def upsert_logical_switch(flow_data: GraphFlowData, op: UpsertLogicalSwitchOp) -> GraphFlowData:
    from app.modules.graphs.expressions import get_expression_variables
    from app.modules.graphs.expressions.translator import translate_polars_to_python
    from app.modules.graphs.nodes.logical_switch import Branch, LogicalSwitchNode, _make_slot_id

    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    old_branch_ids = set()
    if node:
        if node.node_type != NodeType.LOGICAL_SWITCH:
            raise ValidationError(f"Node '{op.node_id}' already exists but is not a LOGICAL_SWITCH.")
        old_branch_ids = {b.id for b in node.branches}
    else:
        node = LogicalSwitchNode(id=op.node_id)
        flow_data.nodes.append(node)

    branches = []
    new_branch_ids = set()
    for b in op.branches:
        branch_id = _make_slot_id(op.node_id, b.label)
        new_branch_ids.add(branch_id)

        python_expr = translate_polars_to_python(b.expression, valid_variables=None)
        referenced = get_expression_variables(python_expr)
        ensure_variables_initialized(flow_data, referenced, op.node_id)

        expr_id = f"expr_{op.node_id}_{b.label.lower()}"
        flow_data.expressions[expr_id] = ExpressionRecord(id=expr_id, expr=python_expr)

        branches.append(Branch(id=branch_id, label=b.label, expr_id=expr_id))

    node.branches = branches

    # Switch-Branch Edge Cleanup
    deleted_branch_ids = old_branch_ids - new_branch_ids
    if deleted_branch_ids:
        flow_data.edges = [
            e for e in flow_data.edges if not (e.source == op.node_id and e.source_handle in deleted_branch_ids)
        ]

    return flow_data


# 5. AGENTIC_SWITCH
class UpsertAgenticSwitchOp(BaseModel):
    op: Literal["upsert_agentic_switch"] = "upsert_agentic_switch"
    node_id: str
    agentic_input: str
    branches: list[str] = Field(default_factory=list)


def upsert_agentic_switch(flow_data: GraphFlowData, op: UpsertAgenticSwitchOp) -> GraphFlowData:
    from app.modules.graphs.nodes.agentic_switch import AgenticBranch, AgenticSwitchNode, _make_slot_id

    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    old_branch_ids = set()
    if node:
        if node.node_type != NodeType.AGENTIC_SWITCH:
            raise ValidationError(f"Node '{op.node_id}' already exists but is not an AGENTIC_SWITCH.")
        old_branch_ids = {b.id for b in node.branches}
    else:
        node = AgenticSwitchNode(id=op.node_id)
        flow_data.nodes.append(node)

    ensure_variables_initialized(flow_data, {op.agentic_input}, op.node_id)

    branches = []
    new_branch_ids = set()
    for label in op.branches:
        branch_id = _make_slot_id(op.node_id, label)
        new_branch_ids.add(branch_id)
        branches.append(AgenticBranch(id=branch_id, label=label))

    node.branches = branches
    node.agentic_input = op.agentic_input

    # Switch-Branch Edge Cleanup
    deleted_branch_ids = old_branch_ids - new_branch_ids
    if deleted_branch_ids:
        flow_data.edges = [
            e for e in flow_data.edges if not (e.source == op.node_id and e.source_handle in deleted_branch_ids)
        ]

    return flow_data


# 6. INTERRUPT
class UpsertInterruptOp(BaseModel):
    op: Literal["upsert_interrupt"] = "upsert_interrupt"
    node_id: str
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str
    resume_var_type: VariableType = "string"


def upsert_interrupt(flow_data: GraphFlowData, op: UpsertInterruptOp) -> GraphFlowData:
    from app.modules.graphs.nodes.interrupt import InterruptNode

    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if node:
        if node.node_type != NodeType.INTERRUPT:
            raise ValidationError(f"Node '{op.node_id}' already exists but is not an INTERRUPT.")
    else:
        node = InterruptNode(id=op.node_id)
        flow_data.nodes.append(node)

    ensure_variables_initialized(flow_data, set(op.payload_vars), op.node_id)

    default_val = get_default_value_for_type(op.resume_var_type)
    auto_declare_variable(flow_data, op.resume_var, op.resume_var_type, default_val)

    node.payload_vars = op.payload_vars
    node.resume_var = op.resume_var
    return flow_data
