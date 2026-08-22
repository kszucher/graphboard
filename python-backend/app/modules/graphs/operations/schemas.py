from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import NodeType
from app.modules.graphs.expressions.schemas import ComparisonExpression, Expression
from app.modules.graphs.schemas import VariableType

# Snake-case identifier pattern: must start with a letter, only letters/digits/underscores.
_IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_]*$"


class AssignmentInput(BaseModel):
    target_var_key: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    expression: Expression


class BranchValueInput(BaseModel):
    expression: ComparisonExpression | None = None
    target: str | None = None


class AgenticOutputInput(BaseModel):
    key: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    type: VariableType


class VariableUpsertInput(BaseModel):
    key: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    type: VariableType
    default_value: Any = None
    description: str | None = None


class NodeUpsertInput(BaseModel):
    id: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    node_type: NodeType
    target: str | None = None

    # LOGICAL_ASSIGNER
    assignments: list[AssignmentInput] | None = None

    # AGENTIC_ASSIGNER
    agentic_inputs: list[str] | None = None
    agentic_outputs: list[AgenticOutputInput] | None = None
    prompt: str | None = None

    # LOGICAL_SWITCH / AGENTIC_SWITCH
    branches: dict[str, BranchValueInput] | None = Field(default=None, min_length=1)
    agentic_input: str | None = None

    # RAG_RETRIEVER
    query_var: str | None = None
    context_output_var: str | None = None
    knowledge_base: str | None = None
    top_k: int | None = None

    # INTERRUPT
    payload_vars: list[str] | None = None
    resume_var: str | None = None


class RenameInput(BaseModel):
    old_key: str
    new_key: str


class VariablesUpdate(BaseModel):
    upsert: list[VariableUpsertInput] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)


class NodesUpdate(BaseModel):
    upsert: list[NodeUpsertInput] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)


class GraphUpdateInput(BaseModel):
    start_target: str | None = None
    variables: VariablesUpdate | None = None
    nodes: NodesUpdate | None = None
    rename_nodes: list[RenameInput] | None = None
    rename_variables: list[RenameInput] | None = None
