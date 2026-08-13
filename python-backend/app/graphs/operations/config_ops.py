from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.exceptions import ValidationError
from app.graphs.nodes import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    RagRetrieverNode,
)
from app.graphs.schemas import GraphFlowData


def _resolve_expr_id(flow_data: GraphFlowData, expr_id: str | None, context: str) -> None:
    if expr_id is not None and expr_id not in flow_data.expressions:
        raise ValidationError(
            f"{context}: expr_id '{expr_id}' does not exist in the expression store. Define expression first."
        )


class BindLogicalAssignmentOp(BaseModel):
    """Bind a state variable assignment formula to a logical assigner node."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["bind_logical_assignment"] = "bind_logical_assignment"
    node_id: str
    target_var_key: str
    expr_id: str


class BindBranchConditionOp(BaseModel):
    """Bind a boolean expression condition to a specific branch on a logical switch node."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["bind_branch_condition"] = "bind_branch_condition"
    node_id: str
    branch_label: str
    expr_id: str


class ConfigureAgenticPromptOp(BaseModel):
    """Configure the LLM prompt and variable dependencies for an agentic assigner node."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["configure_agentic_prompt"] = "configure_agentic_prompt"
    node_id: str
    prompt: str
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)


class ConfigureAgenticSwitchOp(BaseModel):
    """Configure the agentic input variable for an agentic switch node."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["configure_agentic_switch"] = "configure_agentic_switch"
    node_id: str
    agentic_input: str


class ConfigureRagSearchOp(BaseModel):
    """Configure vector search parameters for a RAG retriever node."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["configure_rag_search"] = "configure_rag_search"
    node_id: str
    knowledge_base: str = "trivia"
    top_k: int = 3
    query_var: str
    context_output_var: str


class ConfigureInterruptOp(BaseModel):
    """Configure payload and resume variables for an interrupt node."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["configure_interrupt"] = "configure_interrupt"
    node_id: str
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str


def bind_logical_assignment(flow_data: GraphFlowData, op: BindLogicalAssignmentOp) -> GraphFlowData:
    _resolve_expr_id(flow_data, op.expr_id, f"bind_logical_assignment('{op.node_id}')")

    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if not isinstance(node, LogicalAssignerNode):
        raise ValidationError(f"Node '{op.node_id}' is not a LOGICAL_ASSIGNER.")

    from app.graphs.nodes import LogicalAssignmentSchema

    node.assignments = [a for a in getattr(node, "assignments", []) if a.target_var_key != op.target_var_key]
    node.assignments.append(LogicalAssignmentSchema(target_var_key=op.target_var_key, expr_id=op.expr_id))
    return flow_data


def bind_branch_condition(flow_data: GraphFlowData, op: BindBranchConditionOp) -> GraphFlowData:
    _resolve_expr_id(flow_data, op.expr_id, f"bind_branch_condition('{op.node_id}')")

    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if not isinstance(node, LogicalSwitchNode):
        raise ValidationError(f"Node '{op.node_id}' is not a LOGICAL_SWITCH.")

    branch = next((b for b in getattr(node, "branches", []) if b.label == op.branch_label), None)
    if not branch:
        raise ValidationError(f"Branch '{op.branch_label}' not found on node '{op.node_id}'.")

    branch.expr_id = op.expr_id
    return flow_data


def configure_agentic_prompt(flow_data: GraphFlowData, op: ConfigureAgenticPromptOp) -> GraphFlowData:
    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if not isinstance(node, AgenticAssignerNode):
        raise ValidationError(f"Node '{op.node_id}' is not an AGENTIC_ASSIGNER.")

    node.prompt = op.prompt
    node.agentic_inputs = op.agentic_inputs
    node.agentic_outputs = op.agentic_outputs
    return flow_data


def configure_agentic_switch(flow_data: GraphFlowData, op: ConfigureAgenticSwitchOp) -> GraphFlowData:
    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if not isinstance(node, AgenticSwitchNode):
        raise ValidationError(f"Node '{op.node_id}' is not an AGENTIC_SWITCH.")

    node.agentic_input = op.agentic_input
    return flow_data


def configure_rag_search(flow_data: GraphFlowData, op: ConfigureRagSearchOp) -> GraphFlowData:
    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if not isinstance(node, RagRetrieverNode):
        raise ValidationError(f"Node '{op.node_id}' is not a RAG_RETRIEVER.")

    node.knowledge_base = op.knowledge_base
    node.top_k = op.top_k
    node.query_var = op.query_var
    node.context_output_var = op.context_output_var
    return flow_data


def configure_interrupt(flow_data: GraphFlowData, op: ConfigureInterruptOp) -> GraphFlowData:
    node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if not isinstance(node, InterruptNode):
        raise ValidationError(f"Node '{op.node_id}' is not an INTERRUPT.")

    node.payload_vars = op.payload_vars
    node.resume_var = op.resume_var
    return flow_data
