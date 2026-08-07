from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants import NodeType

VariableType: TypeAlias = Literal["boolean", "string", "number", "float"]


class DefinerVariableUpdates(TypedDict, total=False):
    key: str
    type: VariableType
    default_value: Any
    description: str | None


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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_var_key: str
    expression: str | None = None


class SlotRead(BaseModel):
    id: str = ""
    raw_string: str = ""
    expression: str | None = None
    target_var_key: str | None = None


class AgenticSlotRead(BaseModel):
    id: str = ""
    raw_string: str = ""


class BaseNode(BaseModel):
    id: str

    def get_variable_references(self) -> set[str]:
        return set()

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        pass


class StartNode(BaseNode):
    node_type: Literal[NodeType.START] = NodeType.START


class EndNode(BaseNode):
    node_type: Literal[NodeType.END] = NodeType.END


class LogicalAssignerNode(BaseNode):
    node_type: Literal[NodeType.LOGICAL_ASSIGNER] = NodeType.LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)

    def get_variable_references(self) -> set[str]:
        from app.graphs.expressions import get_expression_variables

        refs = set()
        for asgn in self.assignments:
            if asgn.target_var_key:
                refs.add(asgn.target_var_key)
            if asgn.expression:
                refs.update(get_expression_variables(asgn.expression))
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        from app.graphs.expressions import rename_expression_variables

        for asgn in self.assignments:
            if asgn.target_var_key == old_key:
                asgn.target_var_key = new_key
            if asgn.expression:
                asgn.expression = rename_expression_variables(asgn.expression, old_key, new_key)


class AgenticAssignerNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_ASSIGNER] = NodeType.AGENTIC_ASSIGNER
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)

    def get_variable_references(self) -> set[str]:
        refs = set()
        if self.agentic_inputs:
            refs.update(self.agentic_inputs)
        if self.agentic_outputs:
            refs.update(self.agentic_outputs)
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        if self.agentic_inputs:
            self.agentic_inputs = [new_key if k == old_key else k for k in self.agentic_inputs]
        if self.agentic_outputs:
            self.agentic_outputs = [new_key if k == old_key else k for k in self.agentic_outputs]
        if self.prompt:
            self.prompt = self.prompt.replace(f"{{{old_key}}}", f"{{{new_key}}}")


class LogicalSwitchNode(BaseNode):
    node_type: Literal[NodeType.LOGICAL_SWITCH] = NodeType.LOGICAL_SWITCH
    slots: list[SlotRead] = Field(default_factory=list)

    def get_variable_references(self) -> set[str]:
        from app.graphs.expressions import get_expression_variables

        refs = set()
        for slot in self.slots:
            if slot.expression:
                refs.update(get_expression_variables(slot.expression))
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        from app.graphs.expressions import rename_expression_variables

        for slot in self.slots:
            if slot.expression:
                slot.expression = rename_expression_variables(slot.expression, old_key, new_key)


class InterruptNode(BaseNode):
    node_type: Literal[NodeType.INTERRUPT] = NodeType.INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""

    def get_variable_references(self) -> set[str]:
        refs = set()
        if self.payload_vars:
            refs.update(self.payload_vars)
        if self.resume_var:
            refs.add(self.resume_var)
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        if self.payload_vars:
            self.payload_vars = [new_key if k == old_key else k for k in self.payload_vars]
        if self.resume_var == old_key:
            self.resume_var = new_key


class AgenticSwitchNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_SWITCH] = NodeType.AGENTIC_SWITCH
    slots: list[AgenticSlotRead] = Field(default_factory=list)
    agentic_input: str = ""

    def get_variable_references(self) -> set[str]:
        return {self.agentic_input} if self.agentic_input else set()

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        if self.agentic_input == old_key:
            self.agentic_input = new_key


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


class StartNodeConfig(BaseModel):
    pass


class EndNodeConfig(BaseModel):
    pass


class LogicalAssignerConfig(BaseModel):
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class AgenticAssignerConfig(BaseModel):
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)


class LogicalSwitchConfig(BaseModel):
    slots: list[SlotRead] = Field(default_factory=list)


class InterruptConfig(BaseModel):
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""


class AgenticSwitchConfig(BaseModel):
    slots: list[AgenticSlotRead] = Field(default_factory=list)
    agentic_input: str = ""


NodeConfig: TypeAlias = (
    StartNodeConfig
    | EndNodeConfig
    | LogicalAssignerConfig
    | AgenticAssignerConfig
    | LogicalSwitchConfig
    | AgenticSwitchConfig
    | InterruptConfig
)


class UpsertNodeOp(BaseModel):
    op: Literal["upsert_node"] = "upsert_node"
    node_id: str
    node_type: NodeType
    new_id: str | None = None
    config: Any = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_config(self) -> UpsertNodeOp:
        if isinstance(self.config, dict):
            if self.node_type == NodeType.START:
                self.config = StartNodeConfig.model_validate(self.config)
            elif self.node_type == NodeType.END:
                self.config = EndNodeConfig.model_validate(self.config)
            elif self.node_type == NodeType.LOGICAL_ASSIGNER:
                from app.graphs.expressions import parse_expression

                for asgn in self.config.get("assignments", []):
                    if isinstance(asgn.get("expression"), str):
                        asgn["expression"] = parse_expression(asgn["expression"])
                self.config = LogicalAssignerConfig.model_validate(self.config)
            elif self.node_type == NodeType.AGENTIC_ASSIGNER:
                self.config = AgenticAssignerConfig.model_validate(self.config)
            elif self.node_type == NodeType.LOGICAL_SWITCH:
                from app.graphs.expressions import parse_expression

                for slot in self.config.get("slots", []):
                    if isinstance(slot.get("expression"), str):
                        slot["expression"] = parse_expression(slot["expression"])
                self.config = LogicalSwitchConfig.model_validate(self.config)
            elif self.node_type == NodeType.AGENTIC_SWITCH:
                self.config = AgenticSwitchConfig.model_validate(self.config)
            elif self.node_type == NodeType.INTERRUPT:
                self.config = InterruptConfig.model_validate(self.config)
        return self


class DeleteNodeOp(BaseModel):
    op: Literal["delete_node"] = "delete_node"
    node_id: str


class ConnectOp(BaseModel):
    op: Literal["connect"] = "connect"
    source: str
    source_handle: str | None = None
    target: str
    target_handle: str | None = None


class DisconnectOp(BaseModel):
    op: Literal["disconnect"] = "disconnect"
    source: str
    source_handle: str | None = None
    target: str
    target_handle: str | None = None


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
