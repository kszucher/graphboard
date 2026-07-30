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


class DefinerVariableSchema(BaseModel):
    id: str = ""
    key: str
    type: Literal["boolean", "string", "number", "float"]
    default_value: Any = None
    description: str | None = None


class LogicalAssignmentSchema(BaseModel):
    id: str
    target_var_key: str
    value_type: Literal["boolean", "string", "number", "float"] = "string"
    value: Any = None
    expression: dict[str, Any] | None = None


class SlotRead(BaseModel):
    id: str = ""
    raw_string: str = ""
    expression: dict[str, Any] | None = None
    target_var_key: str | None = None


class NodeRead(BaseModel):
    id: str
    node_type: NodeType
    slots: list[SlotRead] = Field(default_factory=list)
    variables: list[DefinerVariableSchema] | None = None
    assignments: list[LogicalAssignmentSchema] | None = None
    prompt: str | None = None


class EdgeRead(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_id: str
    source_type: Literal["node", "slot"] = "node"
    target_id: str
    target_type: Literal["node", "slot"] = "node"


class GraphFlowRead(BaseModel):
    nodes: list[NodeRead]
    edges: list[EdgeRead]
    can_undo: bool = False
    can_redo: bool = False


class GraphCodeRead(BaseModel):
    code: str


class GraphFlowData(BaseModel):
    nodes: list[NodeRead] = Field(default_factory=list)
    edges: list[EdgeRead] = Field(default_factory=list)


class NodeCreateRequest(BaseModel):
    node_type: NodeType
    connector_id: str | None = None
    direction: Literal["before", "after"] | None = None


class NodeUpdateRequest(BaseModel):
    new_id: str | None = None


class DefinerVariableCreateRequest(BaseModel):
    key: str
    type: Literal["boolean", "string", "number", "float"] = "string"
    default_value: Any = None
    description: str | None = None


class DefinerVariableUpdateRequest(BaseModel):
    type: Literal["boolean", "string", "number", "float"] | None = None
    default_value: Any = None
    description: str | None = None


class LogicalAssignmentCreateRequest(BaseModel):
    target_var_key: str
    value_type: Literal["boolean", "string", "number", "float"] = "string"
    value: Any = None
    expression: dict[str, Any] | None = None


class LogicalAssignmentUpdateRequest(BaseModel):
    target_var_key: str | None = None
    value_type: Literal["boolean", "string", "number", "float"] | None = None
    value: Any = None
    expression: dict[str, Any] | None = None


class SlotCreateRequest(BaseModel):
    index: int


class SlotUpdateRequest(BaseModel):
    raw_string: str | None = None
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
