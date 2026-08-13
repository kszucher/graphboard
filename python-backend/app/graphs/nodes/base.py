from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict


def _make_slot_id(node_id: str, label: str) -> str:
    """Deterministically generate a branch handle ID from node_id and branch label."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "branch"
    return f"{node_id}_{slug}"


class BaseNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = ""

    def serialize_compact(self, *args: Any, **kwargs: Any) -> list[str]:
        node_type = getattr(self, "node_type", None)
        type_str = node_type.value if node_type else "unknown"
        return [f"  - {self.id} [{type_str}]"]

    @property
    def supports_branches(self) -> bool:
        return False

    def handle_node_rename(self, old_id: str, new_id: str) -> None:
        self.id = new_id

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        pass
