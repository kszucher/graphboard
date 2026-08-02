import uuid
from typing import Annotated, Any, Literal, TypeAlias, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.constants import NodeType

VariableType: TypeAlias = Literal["boolean", "string", "number", "float"]


class DefinerVariableUpdates(TypedDict, total=False):
    key: str
    type: VariableType
    default_value: Any
    description: str | None


class LogicalAssignmentUpdates(TypedDict, total=False):
    target_var_key: str
    value_type: VariableType
    value: Any
    expression: dict[str, Any] | None


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
    type: VariableType
    default_value: Any = None
    description: str | None = None


class LogicalAssignmentSchema(BaseModel):
    id: str
    target_var_key: str
    value_type: VariableType = "string"
    value: Any = None
    expression: dict[str, Any] | None = None


class SlotRead(BaseModel):
    id: str = ""
    raw_string: str = ""
    expression: dict[str, Any] | None = None
    target_var_key: str | None = None


class BaseNode(BaseModel):
    id: str


class StartNode(BaseNode):
    node_type: Literal[NodeType.START] = NodeType.START


class EndNode(BaseNode):
    node_type: Literal[NodeType.END] = NodeType.END


class LogicalAssignerNode(BaseNode):
    node_type: Literal[NodeType.LOGICAL_ASSIGNER] = NodeType.LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class AgenticAssignerNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_ASSIGNER] = NodeType.AGENTIC_ASSIGNER
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)


class SwitchNode(BaseNode):
    node_type: Literal[NodeType.SWITCH] = NodeType.SWITCH
    slots: list[SlotRead] = Field(default_factory=list)


# ── Sequential (no slots) ────────────────────────────────────────


class InterruptNode(BaseNode):
    node_type: Literal[NodeType.INTERRUPT] = NodeType.INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""


class ExtractNode(BaseNode):
    node_type: Literal[NodeType.EXTRACT] = NodeType.EXTRACT
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class ValidateNode(BaseNode):
    node_type: Literal[NodeType.VALIDATE] = NodeType.VALIDATE
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class ReviewNode(BaseNode):
    node_type: Literal[NodeType.REVIEW] = NodeType.REVIEW


# ── Routing (have slots) ─────────────────────────────────────────


class AgenticSwitchNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_SWITCH] = NodeType.AGENTIC_SWITCH
    slots: list[SlotRead] = Field(default_factory=list)
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)


class RetryNode(BaseNode):
    node_type: Literal[NodeType.RETRY] = NodeType.RETRY
    slots: list[SlotRead] = Field(default_factory=list)
    max_attempts: int = 3
    valid_expression: dict[str, Any] | None = None


class ConfirmNode(BaseNode):
    node_type: Literal[NodeType.CONFIRM] = NodeType.CONFIRM
    slots: list[SlotRead] = Field(default_factory=list)
    payload_vars: list[str] = Field(default_factory=list)


NodeRead: TypeAlias = Annotated[
    StartNode
    | EndNode
    | LogicalAssignerNode
    | AgenticAssignerNode
    | InterruptNode
    | ExtractNode
    | ValidateNode
    | ReviewNode
    | SwitchNode
    | AgenticSwitchNode
    | RetryNode
    | ConfirmNode,
    Field(discriminator="node_type"),
]


class EdgeRead(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_id: str
    source_type: Literal["node", "slot"] = "node"
    target_id: str
    target_type: Literal["node", "slot"] = "node"


class GraphFlowRead(OrmModel):
    nodes: list[NodeRead]
    edges: list[EdgeRead]
    state: list[DefinerVariableSchema] = Field(default_factory=list)
    can_undo: bool = False
    can_redo: bool = False


class GraphCodeRead(BaseModel):
    code: str


class GraphFlowData(BaseModel):
    nodes: list[NodeRead] = Field(default_factory=list)
    edges: list[EdgeRead] = Field(default_factory=list)
    state: list[DefinerVariableSchema] = Field(default_factory=list)


class NodeCreateRequest(BaseModel):
    node_type: NodeType
    connector_id: str | None = None
    direction: Literal["before", "after"] | None = None


class NodeUpdateRequest(BaseModel):
    new_id: str | None = None
    prompt: str | None = None
    agentic_inputs: list[str] | None = None
    agentic_outputs: list[str] | None = None
    payload_vars: list[str] | None = None
    resume_var: str | None = None
    max_attempts: int | None = None
    valid_expression: dict[str, Any] | None = None


class DefinerVariableCreateRequest(BaseModel):
    key: str
    type: VariableType = "string"
    default_value: Any = None
    description: str | None = None


class DefinerVariableUpdateRequest(BaseModel):
    key: str | None = None
    type: VariableType | None = None
    default_value: Any = None
    description: str | None = None


class LogicalAssignmentCreateRequest(BaseModel):
    target_var_key: str
    value_type: VariableType = "string"
    value: Any = None
    expression: dict[str, Any] | None = None


class LogicalAssignmentUpdateRequest(BaseModel):
    target_var_key: str | None = None
    value_type: VariableType | None = None
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
