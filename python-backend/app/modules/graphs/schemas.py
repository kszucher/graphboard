from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from app.modules.graphs.expressions.schemas import Expression
from app.modules.graphs.nodes import NodeRead


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class GraphCreate(BaseModel):
    user_id: uuid.UUID
    graph_name: str = Field(min_length=1, max_length=255)


class GraphRead(OrmModel):
    id: uuid.UUID
    name: str
    user_id: uuid.UUID


VariableType: TypeAlias = Literal["boolean", "bool", "string", "number", "float", "int", "integer"]


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


class ExpressionRecord(BaseModel):
    """A named, reusable expression stored in the graph's expression store."""

    id: str
    expr: Expression


class GraphFlowData(BaseModel):
    nodes: list[NodeRead] = Field(default_factory=list)
    edges: list[EdgeRead] = Field(default_factory=list)
    state: list[DefinerVariableSchema] = Field(default_factory=list)
    expressions: dict[str, ExpressionRecord] = Field(default_factory=dict)
