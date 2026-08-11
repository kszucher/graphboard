from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

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


class UpsertLogicalAssignerOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_logical_assigner"] = "upsert_logical_assigner"
    node_id: str
    new_id: str | None = None
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def parse_expressions(self) -> UpsertLogicalAssignerOp:
        from app.graphs.expressions import parse_expression

        for assignment in self.assignments:
            if isinstance(assignment.expression, str):
                assignment.expression = parse_expression(assignment.expression)
        return self


class UpsertAgenticAssignerOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_agentic_assigner"] = "upsert_agentic_assigner"
    node_id: str
    new_id: str | None = None
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)


class UpsertLogicalSwitchOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_logical_switch"] = "upsert_logical_switch"
    node_id: str
    new_id: str | None = None
    branches: list[Branch] = Field(default_factory=list)

    @model_validator(mode="after")
    def parse_expressions(self) -> UpsertLogicalSwitchOp:
        from app.graphs.expressions import parse_expression

        for branch in self.branches:
            if isinstance(branch.expression, str):
                branch.expression = parse_expression(branch.expression)
        return self


class UpsertAgenticSwitchOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_agentic_switch"] = "upsert_agentic_switch"
    node_id: str
    new_id: str | None = None
    branches: list[Branch] = Field(default_factory=list)
    agentic_input: str = ""


class UpsertInterruptOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["upsert_interrupt"] = "upsert_interrupt"
    node_id: str
    new_id: str | None = None
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""


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
    expression: str | None = None

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
    UpsertLogicalAssignerOp
    | UpsertAgenticAssignerOp
    | UpsertLogicalSwitchOp
    | UpsertAgenticSwitchOp
    | UpsertInterruptOp
    | DeleteNodeOp
    | ConnectOp
    | DisconnectOp
    | UpsertStateVarOp
    | DeleteStateVarOp,
    Field(discriminator="op"),
]
