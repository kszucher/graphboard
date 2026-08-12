from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.constants import NodeType

from .base import BaseNode


class InterruptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.INTERRUPT] = NodeType.INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""


class InterruptNode(BaseNode, InterruptConfig):
    def get_variable_references(self) -> set[str]:
        refs = set(self.payload_vars)
        if self.resume_var:
            refs.add(self.resume_var)
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        self.payload_vars = [new_key if k == old_key else k for k in self.payload_vars]
        if self.resume_var == old_key:
            self.resume_var = new_key

    def serialize_compact(self) -> list[str]:
        lines = [f"  - {self.id} [{self.node_type.value}]"]
        if self.payload_vars:
            lines.append(f"    payload: {', '.join(self.payload_vars)}")
        if self.resume_var:
            lines.append(f"    resume: {self.resume_var}")
        return lines

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        if not self.resume_var:
            raise ValidationError(f"Interrupt node '{self.id}' must have a valid resume_var.")
