from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import NodeType
from app.modules.graphs.expressions.schemas import Expression

from .base import BaseNode


class LogicalAssignmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_var_key: str
    expression: Expression | None = None


class LogicalAssignerNode(BaseNode):
    node_type: Literal[NodeType.LOGICAL_ASSIGNER] = NodeType.LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)
