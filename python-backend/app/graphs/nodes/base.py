from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict


def _make_slot_id(node_id: str, label: str) -> str:
    """Deterministically generate a branch handle ID from node_id and branch label."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "branch"
    return f"{node_id}_{slug}"


class BaseNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = ""

    @property
    def supports_branches(self) -> bool:
        return False

    def handle_node_rename(self, old_id: str, new_id: str) -> None:
        self.id = new_id

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        pass
