from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.constants import NodeType

from .base import BaseNode, _make_slot_id


class Branch(BaseModel):
    """A routing branch on a switch node.

    Invariant: `label` retains the original human-readable casing (e.g. 'Submit').
    `id` is auto-generated from `label` via `_make_slot_id` and is not part of the
    JSON schema exposed to the LLM — do NOT set it manually.
    """

    model_config = ConfigDict(extra="forbid")
    id: SkipJsonSchema[str] = ""
    label: str  # required — the human-readable routing label
    expr_id: str | None = None  # LogicalSwitch condition (Python expression)
    target_var_key: str | None = None  # optional variable binding for integrity tracking


class LogicalSwitchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.LOGICAL_SWITCH] = NodeType.LOGICAL_SWITCH
    branches: list[Branch] = Field(default_factory=list)


class LogicalSwitchNode(BaseNode, LogicalSwitchConfig):
    @model_validator(mode="after")
    def populate_branch_ids(self) -> LogicalSwitchNode:
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

    def serialize_compact(self, *args: Any, **kwargs: Any) -> list[str]:
        lines = [f"  - {self.id} [{self.node_type.value}]"]
        branches_str = []
        for b in self.branches:
            expr_str = b.expr_id or ""
            branches_str.append(f"{b.label} ({expr_str})")
        if branches_str:
            lines.append(f"    branches: {', '.join(branches_str)}")
        return lines

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        for branch in self.branches:
            if branch.expr_id is None:
                raise ValidationError(
                    f"Logical Switch node '{self.id}' has an unset condition on option '{branch.label}'."
                )
            if (self.id, branch.id) not in edge_sources:
                raise ValidationError(
                    f"Logical Switch option '{branch.label}' on node '{self.id}' is not connected to any target node."
                )
