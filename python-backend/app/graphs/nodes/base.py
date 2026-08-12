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

    def get_variable_references(self) -> set[str]:
        from app.graphs.expressions import get_expression_variables

        refs: set[str] = set()
        # Scan fields dynamically
        for field in getattr(self, "_variable_fields", []):
            val = getattr(self, field, None)
            if isinstance(val, str) and val:
                refs.add(val)
            elif isinstance(val, list):
                refs.update(item for item in val if isinstance(item, str) and item)

        # Scan nested lists (assignments, branches)
        for field in ("assignments", "branches"):
            for item in getattr(self, field, []):
                t_var = getattr(item, "target_var_key", None)
                if t_var:
                    refs.add(t_var)
                expr = getattr(item, "expression", None)
                if expr:
                    refs.update(get_expression_variables(expr))
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        from app.graphs.expressions import rename_expression_variables

        # Rename in direct variable fields
        for field in getattr(self, "_variable_fields", []):
            val = getattr(self, field, None)
            if isinstance(val, str) and val == old_key:
                setattr(self, field, new_key)
            elif isinstance(val, list):
                setattr(self, field, [new_key if k == old_key else k for k in val])

        # Rename in nested lists
        for field in ("assignments", "branches"):
            for item in getattr(self, field, []):
                if getattr(item, "target_var_key", None) == old_key:
                    item.target_var_key = new_key
                expr = getattr(item, "expression", None)
                if expr:
                    item.expression = rename_expression_variables(expr, old_key, new_key)

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        pass
