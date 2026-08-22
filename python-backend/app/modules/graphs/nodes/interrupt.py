from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.core.constants import NodeType

from .base import BaseNode


class InterruptNode(BaseNode):
    node_type: Literal[NodeType.INTERRUPT] = NodeType.INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.core.exceptions import ValidationError

        if not self.resume_var:
            raise ValidationError(f"Interrupt node '{self.id}' must have a valid resume_var.")
