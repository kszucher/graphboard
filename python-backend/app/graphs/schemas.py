import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.constants import NodeType


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class GraphCreate(BaseModel):
    user_id: uuid.UUID
    graph_name: str = Field(min_length=1, max_length=255)


class GraphRead(OrmModel):
    id: uuid.UUID
    name: str
    user_id: uuid.UUID


class StateVariableSchema(BaseModel):
    id: str
    key: str
    type: Literal["boolean", "string", "number", "float"]
    default_value: Any = None
    description: str | None = None


class SlotRead(BaseModel):
    id: str
    raw_string: str
    expression: dict[str, Any] | None = None
    target_var_key: str | None = None
    selected: bool = False


class NodeRead(BaseModel):
    id: str
    node_type: NodeType
    is_input: bool = False
    is_output: bool = False
    slots: list[SlotRead]
    code: str = ""
    selected: bool = False


class EdgeRead(BaseModel):
    id: uuid.UUID
    source_id: str
    source_type: Literal["node", "slot"]
    target_id: str
    target_type: Literal["node", "slot"]


class DiagnosticRead(BaseModel):
    line: int
    column: int
    code: str
    message: str
    severity: Literal["error", "warning"]
    node_id: str | None = None
    slot_id: str | None = None


class GraphFlowRead(BaseModel):
    code: str = ""
    nodes: list[NodeRead]
    edges: list[EdgeRead]
    state_schema: list[StateVariableSchema] = []
    diagnostics: list[DiagnosticRead] = []
    can_undo: bool = False
    can_redo: bool = False


class GraphSyncPayload(BaseModel):
    nodes: list[NodeRead]
    edges: list[EdgeRead]
    state_schema: list[StateVariableSchema] = []


class NodeCreateRequest(BaseModel):
    node_type: NodeType
    connector_id: str | None = None
    direction: Literal["before", "after"] | None = None


class NodeUpdateRequest(BaseModel):
    new_id: str | None = None
    is_input: bool | None = None
    is_output: bool | None = None


class SlotCreateRequest(BaseModel):
    index: int


class SlotUpdateRequest(BaseModel):
    raw_string: str
    expression: dict[str, Any] | None = None
    target_var_key: str | None = None


class SlotMoveRequest(BaseModel):
    direction: Literal["up", "down", "top", "bottom"]


class EdgeCreateRequest(BaseModel):
    source: str
    target: str
    source_handle: str
    target_handle: str


class EdgeReconnectRequest(BaseModel):
    source: str
    target: str
    source_handle: str
    target_handle: str
