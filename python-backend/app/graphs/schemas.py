from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.constants import NodeType
from app.graphs.nodes import Branch, LogicalAssignmentSchema, NodeRead


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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


class UpsertNodeOp(BaseModel):
    """Flat node upsert operation.

    All node-type-specific fields live at the top level alongside node_id and node_type.
    The relevant subset of fields depends on node_type:
      - LOGICAL_ASSIGNER  → assignments
      - AGENTIC_ASSIGNER  → prompt, agentic_inputs, agentic_outputs
      - LOGICAL_SWITCH    → branches (each branch needs a label + expression)
      - AGENTIC_SWITCH    → agentic_input, branches (each branch needs only a label)
      - INTERRUPT         → payload_vars, resume_var
    """

    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_node"] = "upsert_node"
    node_id: str
    node_type: NodeType
    new_id: str | None = None

    # LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)

    # AGENTIC_ASSIGNER
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)

    # LOGICAL_SWITCH & AGENTIC_SWITCH — unified branch type
    branches: list[Branch] = Field(default_factory=list)

    # AGENTIC_SWITCH
    agentic_input: str = ""

    # INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""

    @model_validator(mode="after")
    def parse_branch_and_assignment_expressions(self) -> UpsertNodeOp:
        if self.node_type in (NodeType.LOGICAL_ASSIGNER, NodeType.LOGICAL_SWITCH):
            from app.graphs.expressions import parse_expression

            for assignment in self.assignments:
                if isinstance(assignment.expression, str):
                    assignment.expression = parse_expression(assignment.expression)
            for branch in self.branches:
                if isinstance(branch.expression, str):
                    branch.expression = parse_expression(branch.expression)
        return self


class DeleteNodeOp(BaseModel):
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
    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_state_var"] = "upsert_state_var"
    id: str | None = None
    key: str
    type: VariableType
    default_value: Any = None
    description: str | None = None


class DeleteStateVarOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["delete_state_var"] = "delete_state_var"
    key: str


GraphOperation: TypeAlias = Annotated[
    UpsertNodeOp | DeleteNodeOp | ConnectOp | DisconnectOp | UpsertStateVarOp | DeleteStateVarOp,
    Field(discriminator="op"),
]
