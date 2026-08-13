from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.constants import NodeType

from .base import BaseNode


class AgenticAssignerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.AGENTIC_ASSIGNER] = NodeType.AGENTIC_ASSIGNER
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)


class AgenticAssignerNode(BaseNode, AgenticAssignerConfig):
    def get_variable_references(self) -> set[str]:
        return set(self.agentic_inputs) | set(self.agentic_outputs)

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        self.agentic_inputs = [new_key if k == old_key else k for k in self.agentic_inputs]
        self.agentic_outputs = [new_key if k == old_key else k for k in self.agentic_outputs]
        if self.prompt:
            self.prompt = self.prompt.replace(f"{{{old_key}}}", f"{{{new_key}}}")

    def serialize_compact(self, *args: Any, **kwargs: Any) -> list[str]:
        lines = [
            f"  - {self.id} [{self.node_type.value}]",
            f"    prompt: {self.prompt}",
        ]
        if self.agentic_inputs:
            lines.append(f"    in: {', '.join(self.agentic_inputs)}")
        if self.agentic_outputs:
            lines.append(f"    out: {', '.join(self.agentic_outputs)}")
        return lines

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        if not self.prompt or not self.prompt.strip():
            raise ValidationError(f"Node '{self.id}' has an empty prompt.")
        if not self.agentic_outputs:
            raise ValidationError(f"Agentic Assigner node '{self.id}' must have at least one output variable.")
