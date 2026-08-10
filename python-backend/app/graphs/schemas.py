from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants import NodeType
from app.graphs.nodes import NodeRead


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
    op: Literal["upsert_node"] = "upsert_node"
    node_id: str
    node_type: NodeType
    new_id: str | None = None
    config: Any = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_config(self) -> UpsertNodeOp:
        if isinstance(self.config, dict):
            from app.graphs.nodes import NODE_CLASS_MAP

            node_cls = NODE_CLASS_MAP.get(self.node_type)
            if node_cls is not None:
                if self.node_type in (NodeType.LOGICAL_ASSIGNER, NodeType.LOGICAL_SWITCH):
                    from app.graphs.expressions import parse_expression

                    items = self.config.get("assignments") or self.config.get("slots") or []
                    for item in items:
                        if isinstance(item.get("expression"), str):
                            item["expression"] = parse_expression(item["expression"])

                # Validate using the unified Node schema by passing a temporary dict with id and node_type
                payload = {"id": self.node_id, "node_type": self.node_type, **self.config}
                node_cls.model_validate(payload)
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
