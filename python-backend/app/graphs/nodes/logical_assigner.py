from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.constants import NodeType

from .base import BaseNode


class LogicalAssignmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_var_key: str
    expr_id: str | None = None


class LogicalAssignerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.LOGICAL_ASSIGNER] = NodeType.LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class LogicalAssignerNode(BaseNode, LogicalAssignerConfig):
    def serialize_compact(self, *args: Any, **kwargs: Any) -> list[str]:
        assigns = [f"{a.target_var_key}={a.expr_id or ''}" for a in self.assignments]
        assigns_str = f" assignments={{{', '.join(assigns)}}}" if assigns else ""
        return [f"  - {self.id} [{self.node_type.value}]{assigns_str}"]
