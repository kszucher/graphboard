from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.constants import NodeType

from .base import BaseNode


class InterruptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.INTERRUPT] = NodeType.INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""


class InterruptNode(BaseNode, InterruptConfig):
    def serialize_compact(self, *args: Any, **kwargs: Any) -> list[str]:
        parts = []
        if self.payload_vars:
            parts.append(f"payload=[{', '.join(self.payload_vars)}]")
        if self.resume_var:
            parts.append(f"resume={self.resume_var}")
        parts_str = f" {' '.join(parts)}" if parts else ""
        return [f"  - {self.id} [{self.node_type.value}]{parts_str}"]

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        if not self.resume_var:
            raise ValidationError(f"Interrupt node '{self.id}' must have a valid resume_var.")
