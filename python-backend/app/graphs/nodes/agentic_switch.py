from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.constants import NodeType

from .base import BaseNode, _make_slot_id


class AgenticBranch(BaseModel):
    """A routing branch on an agentic switch node.

    Doesn't contain any code evaluation expressions.
    """

    model_config = ConfigDict(extra="forbid")
    id: SkipJsonSchema[str] = ""
    label: str  # required — the human-readable routing label
    target_var_key: str | None = None  # optional variable binding for integrity tracking


class AgenticSwitchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.AGENTIC_SWITCH] = NodeType.AGENTIC_SWITCH
    branches: list[AgenticBranch] = Field(default_factory=list)
    agentic_input: str = ""


class AgenticSwitchNode(BaseNode, AgenticSwitchConfig):
    @model_validator(mode="after")
    def populate_branch_ids(self) -> AgenticSwitchNode:
        for branch in self.branches:
            branch.id = _make_slot_id(self.id, branch.label)
        return self

    @property
    def supports_branches(self) -> bool:
        return True

    def handle_node_rename(self, old_id: str, new_id: str) -> None:
        self.id = new_id
        for branch in self.branches:
            if branch.id.startswith(f"{old_id}_"):
                branch.id = branch.id.replace(f"{old_id}_", f"{new_id}_", 1)

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        for branch in self.branches:
            if (self.id, branch.id) not in edge_sources:
                raise ValidationError(
                    f"Agentic Switch option '{branch.label}' on node '{self.id}' is not connected to any target node."
                )
