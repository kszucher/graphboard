from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.graphs.expressions.schemas import ComparisonExpression, Expression
from app.graphs.nodes import Branch, NodeRead


class LogicalAssignmentOpSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_var_key: str
    expression: Expression


class BranchOpSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    expression: ComparisonExpression
    target_var_key: str | None = None


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
 
# ... keep other models ...
class GraphCreate(BaseModel):
    user_id: uuid.UUID
    graph_name: str = Field(min_length=1, max_length=255)


class GraphRead(OrmModel):
    id: uuid.UUID
    name: str
    user_id: uuid.UUID


VariableType: TypeAlias = Literal["boolean", "string", "number", "float"]


class DefinerVariableSchema(BaseModel):
    id: str = ""
    key: str
    type: VariableType
    default_value: Any = None
    description: str | None = None


class EdgeRead(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source: str
    source_handle: str | None = None
    target: str
    target_handle: str | None = None


class GraphVersionRead(BaseModel):
    sequence_number: int
    name: str
    created_at: datetime


class GraphFlowRead(OrmModel):
    nodes: list[NodeRead]
    edges: list[EdgeRead]
    state: list[DefinerVariableSchema] = Field(default_factory=list)
    versions: list[GraphVersionRead] = Field(default_factory=list)
    current_version: int = 0


class GraphCodeRead(BaseModel):
    code: str


class GraphFlowData(BaseModel):
    nodes: list[NodeRead] = Field(default_factory=list)
    edges: list[EdgeRead] = Field(default_factory=list)
    state: list[DefinerVariableSchema] = Field(default_factory=list)


class UpsertLogicalAssignerOp(BaseModel):
    """Add or update a logical assigner node with deterministic inline variable assignments."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_logical_assigner"] = "upsert_logical_assigner"
    node_id: str
    new_id: str | None = None
    assignments: list[LogicalAssignmentOpSchema] = Field(default_factory=list)


class UpsertAgenticAssignerOp(BaseModel):
    """Add or update an agentic assigner node that invokes LLMs for structured state mutations."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_agentic_assigner"] = "upsert_agentic_assigner"
    node_id: str
    new_id: str | None = None
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)


class UpsertLogicalSwitchOp(BaseModel):
    """Add or update a logical switch node to evaluate deterministic expression branching logic."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_logical_switch"] = "upsert_logical_switch"
    node_id: str
    new_id: str | None = None
    branches: list[BranchOpSchema] = Field(default_factory=list)


class UpsertAgenticSwitchOp(BaseModel):
    """Add or update an agentic switch node for LLM-driven decision routing across options."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_agentic_switch"] = "upsert_agentic_switch"
    node_id: str
    new_id: str | None = None
    branches: list[Branch] = Field(default_factory=list)
    agentic_input: str = ""


class UpsertInterruptOp(BaseModel):
    """Add or update an interrupt node to pause workflow execution for user payloads."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_interrupt"] = "upsert_interrupt"
    node_id: str
    new_id: str | None = None
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""


class UpsertRagRetrieverOp(BaseModel):
    """Add or update a RAG node that queries a Neon Postgres vector index using Hugging Face embeddings."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_rag_retriever"] = "upsert_rag_retriever"
    node_id: str
    new_id: str | None = None
    query_var: str = ""
    context_output_var: str = ""
    knowledge_base: str = "trivia"
    top_k: int = 3


class DeleteNodeOp(BaseModel):
    """Delete a node and all of its incoming/outgoing connections."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["delete_node"] = "delete_node"
    node_id: str


def _resolve_case_handle_fields(
    source: str, case: str | None, source_handle: str | None
) -> tuple[str | None, str | None]:
    """Returns (resolved_source_handle, resolved_case) from whichever field the caller provided.

    Invariant: `case` always retains the original human-readable casing (e.g. "Submit").
    `source_handle` is always a slug produced by `_make_slot_id` (e.g. "node_submit").
    Do NOT normalise `case` to lower-case — it is used as a display label in prompts and the UI.
    """
    case_val = case
    if not case_val and source_handle and not source_handle.startswith(f"{source}_"):
        case_val = source_handle
    if case_val:
        from app.graphs.nodes import _make_slot_id

        return _make_slot_id(source, case_val), case_val
    return source_handle, case


class ConnectOp(BaseModel):
    """Draw a connection edge from a source node/branch to a target node. The branch (case label) must already exist on the switch node prior to connecting."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["connect"] = "connect"
    source: str
    source_handle: SkipJsonSchema[str | None] = None
    target: str
    target_handle: SkipJsonSchema[str | None] = None
    case: str | None = None

    @model_validator(mode="after")
    def resolve_case_handle(self) -> ConnectOp:
        self.source_handle, self.case = _resolve_case_handle_fields(self.source, self.case, self.source_handle)
        return self


class DisconnectOp(BaseModel):
    """Remove a connection edge between a source node/handle and target node/handle."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["disconnect"] = "disconnect"
    source: str
    source_handle: SkipJsonSchema[str | None] = None
    target: str
    target_handle: SkipJsonSchema[str | None] = None
    case: str | None = None

    @model_validator(mode="after")
    def resolve_case_handle(self) -> DisconnectOp:
        self.source_handle, self.case = _resolve_case_handle_fields(self.source, self.case, self.source_handle)
        return self


class UpsertStateVarOp(BaseModel):
    """Declare or update a global state variable key, type, and default value."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_state_var"] = "upsert_state_var"
    id: str | None = None
    key: str
    type: VariableType
    default_value: Any = None
    description: str | None = None


class DeleteStateVarOp(BaseModel):
    """Delete a global state variable."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["delete_state_var"] = "delete_state_var"
    key: str


class DeleteBranchOp(BaseModel):
    """Delete a branch from a switch node and clean up its outgoing connections."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["delete_branch"] = "delete_branch"
    node_id: str
    label: str


GraphOperation: TypeAlias = Annotated[
    UpsertLogicalAssignerOp
    | UpsertAgenticAssignerOp
    | UpsertLogicalSwitchOp
    | UpsertAgenticSwitchOp
    | UpsertInterruptOp
    | UpsertRagRetrieverOp
    | DeleteNodeOp
    | ConnectOp
    | DisconnectOp
    | UpsertStateVarOp
    | DeleteStateVarOp
    | DeleteBranchOp,
    Field(discriminator="op"),
]
