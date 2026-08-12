from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants import NodeType

from .base import BaseNode, _make_slot_id
from .logical_switch import Branch


class AgenticSwitchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.AGENTIC_SWITCH] = NodeType.AGENTIC_SWITCH
    branches: list[Branch] = Field(default_factory=list)
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

    def merge_config(self, config_fields: dict[str, Any]) -> None:
        for k, v in config_fields.items():
            if k != "branches" and v is not None and hasattr(self, k):
                setattr(self, k, v)
        if "branches" in config_fields and config_fields["branches"] is not None:
            merged_branches = [b.model_dump(mode="json") for b in self.branches]
            for new_b in config_fields["branches"]:
                label = new_b.get("label")
                existing_b = next((x for x in merged_branches if x.get("label") == label), None)
                if existing_b:
                    existing_b.update({k: v for k, v in new_b.items() if v is not None})
                else:
                    merged_branches.append(new_b)
            self.branches = [Branch.model_validate(b) for b in merged_branches]

    def handle_node_rename(self, old_id: str, new_id: str) -> None:
        self.id = new_id
        for branch in self.branches:
            if branch.id.startswith(f"{old_id}_"):
                branch.id = branch.id.replace(f"{old_id}_", f"{new_id}_", 1)

    def get_variable_references(self) -> set[str]:
        refs = set()
        if self.agentic_input:
            refs.add(self.agentic_input)
        for b in self.branches:
            if b.target_var_key:
                refs.add(b.target_var_key)
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        if self.agentic_input == old_key:
            self.agentic_input = new_key
        for b in self.branches:
            if b.target_var_key == old_key:
                b.target_var_key = new_key

    def serialize_compact(self) -> list[str]:
        lines = [f"  - {self.id} [{self.node_type.value}]"]
        if self.agentic_input:
            lines.append(f"    in: {self.agentic_input}")
        branches_str = [b.label for b in self.branches]
        if branches_str:
            lines.append(f"    branches: {', '.join(branches_str)}")
        return lines

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        for branch in self.branches:
            if (self.id, branch.id) not in edge_sources:
                raise ValidationError(
                    f"Agentic Switch option '{branch.label}' on node '{self.id}' is not connected to any target node."
                )
