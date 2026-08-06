from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal, TypeAlias, TypedDict, Union

from pydantic import BaseModel, ConfigDict, Field

from app.constants import NodeType

VariableType: TypeAlias = Literal["boolean", "string", "number", "float"]


class LiteralExpression(BaseModel):
    kind: Literal["literal"]
    value: Any


class StateRefExpression(BaseModel):
    kind: Literal["stateRef"]
    varKey: str


class BinaryOpExpression(BaseModel):
    kind: Literal["binaryOp"]
    op: Literal["+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">="]
    left: Expression
    right: Expression


class UnaryOpExpression(BaseModel):
    kind: Literal["unaryOp"]
    op: Literal["not"]
    expr: Expression


Expression: TypeAlias = Annotated[
    Union["LiteralExpression", "StateRefExpression", "BinaryOpExpression", "UnaryOpExpression"],
    Field(discriminator="kind"),
]


BinaryOpExpression.model_rebuild()
UnaryOpExpression.model_rebuild()


class DefinerVariableUpdates(TypedDict, total=False):
    key: str
    type: VariableType
    default_value: Any
    description: str | None


class LogicalAssignmentUpdates(TypedDict, total=False):
    target_var_key: str
    value_type: VariableType
    value: Any
    expression: Expression | None


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
    expression: Expression | None = None


class SlotRead(BaseModel):
    id: str = ""
    raw_string: str = ""
    expression: Expression | None = None
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


class LogicalSwitchNode(BaseNode):
    node_type: Literal[NodeType.LOGICAL_SWITCH] = NodeType.LOGICAL_SWITCH
    slots: list[SlotRead] = Field(default_factory=list)


class InterruptNode(BaseNode):
    node_type: Literal[NodeType.INTERRUPT] = NodeType.INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""


class AgenticSwitchNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_SWITCH] = NodeType.AGENTIC_SWITCH
    slots: list[SlotRead] = Field(default_factory=list)
    agentic_input: str = ""


NodeRead: TypeAlias = Annotated[
    StartNode
    | EndNode
    | LogicalAssignerNode
    | AgenticAssignerNode
    | InterruptNode
    | LogicalSwitchNode
    | AgenticSwitchNode,
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


class UpsertNodeOp(BaseModel):
    op: Literal["upsert_node"] = "upsert_node"
    node_id: str
    node_type: NodeType
    config: dict[str, Any] = Field(default_factory=dict)


class DeleteNodeOp(BaseModel):
    op: Literal["delete_node"] = "delete_node"
    node_id: str


class ConnectOp(BaseModel):
    op: Literal["connect"] = "connect"
    source_id: str
    target_id: str
    source_type: Literal["node", "slot"] = "node"
    target_type: Literal["node", "slot"] = "node"


class DisconnectOp(BaseModel):
    op: Literal["disconnect"] = "disconnect"
    source_id: str
    target_id: str
    source_type: Literal["node", "slot"] = "node"
    target_type: Literal["node", "slot"] = "node"


class UpsertStateVarOp(BaseModel):
    op: Literal["upsert_state_var"] = "upsert_state_var"
    id: str | None = None
    key: str
    type: VariableType
    default_value: Any = None
    description: str | None = None


class DeleteStateVarOp(BaseModel):
    op: Literal["delete_state_var"] = "delete_state_var"
    key: str


GraphOperation: TypeAlias = Annotated[
    UpsertNodeOp | DeleteNodeOp | ConnectOp | DisconnectOp | UpsertStateVarOp | DeleteStateVarOp,
    Field(discriminator="op"),
]
