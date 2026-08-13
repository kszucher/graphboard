from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.constants import NodeType
from app.graphs.expressions.schemas import (
    Expression,
)
from app.graphs.expressions.utils import (
    get_variables_from_ast,
    rename_variables_in_ast,
)

from .base import BaseNode


class LogicalAssignmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_var_key: str
    expression: Expression | None = None


class LogicalAssignerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.LOGICAL_ASSIGNER] = NodeType.LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class LogicalAssignerNode(BaseNode, LogicalAssignerConfig):
    def get_variable_references(self) -> set[str]:
        refs = set()
        for a in self.assignments:
            if a.target_var_key:
                refs.add(a.target_var_key)
            if a.expression:
                refs.update(get_variables_from_ast(a.expression))
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        for a in self.assignments:
            if a.target_var_key == old_key:
                a.target_var_key = new_key
            if a.expression:
                rename_variables_in_ast(a.expression, old_key, new_key)

    def serialize_compact(self, expressions: dict[str, Any] | None = None, *args: Any, **kwargs: Any) -> list[str]:
        lines = [f"  - {self.id} [{self.node_type.value}]"]
        for a in self.assignments:
            expr_str = ""
            if a.expression:
                matched_id = None
                if expressions:
                    for eid, record in expressions.items():
                        if getattr(record, "expr", None) == a.expression:
                            matched_id = eid
                            break
                if matched_id:
                    expr_str = matched_id
                else:
                    expr_str = a.expression.to_string()
            lines.append(f"    {a.target_var_key} = {expr_str}")
        return lines
