from __future__ import annotations

import uuid
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants import NodeType
from app.graphs.expressions.schemas import Expression

from .base import BaseNode


class LogicalAssignmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_var_key: str
    expression: Expression | str | None = None

    @model_validator(mode="after")
    def convert_expression_to_string(self) -> LogicalAssignmentSchema:
        if self.expression is not None:
            if not isinstance(self.expression, str):
                self.expression = self.expression.to_string()
            else:
                from app.graphs.expressions import parse_expression

                self.expression = parse_expression(self.expression)
        return self


class LogicalAssignerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.LOGICAL_ASSIGNER] = NodeType.LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class LogicalAssignerNode(BaseNode, LogicalAssignerConfig):
    def get_variable_references(self) -> set[str]:
        from app.graphs.expressions import get_expression_variables

        refs = set()
        for a in self.assignments:
            if a.target_var_key:
                refs.add(a.target_var_key)
            if a.expression:
                refs.update(get_expression_variables(cast(str, a.expression)))
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        from app.graphs.expressions import rename_expression_variables

        for a in self.assignments:
            if a.target_var_key == old_key:
                a.target_var_key = new_key
            if a.expression:
                a.expression = rename_expression_variables(cast(str, a.expression), old_key, new_key)

    def serialize_compact(self) -> list[str]:
        lines = [f"  - {self.id} [{self.node_type.value}]"]
        for a in self.assignments:
            lines.append(f"    {a.target_var_key} = {a.expression or ''}")
        return lines
