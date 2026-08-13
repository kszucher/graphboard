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
    def serialize_compact(self, *args: Any, **kwargs: Any) -> list[str]:
        parts = []
        if self.agentic_inputs:
            parts.append(f"in=[{', '.join(self.agentic_inputs)}]")
        if self.agentic_outputs:
            parts.append(f"out=[{', '.join(self.agentic_outputs)}]")
        if self.prompt:
            # Keep prompt compact and escape double quotes
            prompt_escaped = self.prompt.replace('"', '\\"')
            parts.append(f'prompt="{prompt_escaped}"')
        parts_str = f" {' '.join(parts)}" if parts else ""
        return [f"  - {self.id} [{self.node_type.value}]{parts_str}"]

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        if not self.prompt or not self.prompt.strip():
            raise ValidationError(f"Node '{self.id}' has an empty prompt.")
        if not self.agentic_outputs:
            raise ValidationError(f"Agentic Assigner node '{self.id}' must have at least one output variable.")
