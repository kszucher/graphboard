from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.exceptions import ValidationError
from app.graphs.expressions.schemas import Expression
from app.graphs.schemas import (
    DefinerVariableSchema,
    ExpressionRecord,
    GraphFlowData,
    VariableType,
)

PYTHON_KEYWORDS = {
    "False", "None", "True", "and", "as", "assert", "async", "await", "break",
    "class", "continue", "def", "del", "elif", "else", "except", "finally",
    "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
    "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
}


def validate_default_value_type(var_type: str, val: Any) -> Any:
    if val is None or val == "":
        return None

    if var_type == "number":
        if isinstance(val, int) and not isinstance(val, bool):
            return val
    elif var_type == "float":
        if isinstance(val, (float, int)) and not isinstance(val, bool):
            return float(val)
    elif var_type == "boolean":
        if isinstance(val, bool):
            return val
    elif var_type == "string":
        if isinstance(val, str):
            return val

    raise ValidationError(f"Default value '{val}' is not of type '{var_type}'.")


class DeclareVariableOp(BaseModel):
    """Declare or update a global state variable key, type, and default value."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["declare_variable"] = "declare_variable"
    id: str | None = None
    key: str
    type: VariableType
    default_value: Any = None
    description: str | None = None


class DeleteVariableOp(BaseModel):
    """Delete a global state variable."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["delete_variable"] = "delete_variable"
    key: str


class DefineExpressionOp(BaseModel):
    """Declare or update a named expression in the graph's expression store."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["define_expression"] = "define_expression"
    id: str
    expr: Expression


def declare_variable(flow_data: GraphFlowData, op: DeclareVariableOp) -> GraphFlowData:
    key = op.key.strip()
    if not re.match(r"^[a-z_][a-z0-9_]*$", key):
        raise ValidationError(f"Variable name '{key}' must be valid snake_case.")

    if key in PYTHON_KEYWORDS:
        raise ValidationError(f"Variable name '{key}' cannot be a Python keyword.")

    existing_var = None
    if op.id:
        existing_var = next((v for v in flow_data.state if v.id == op.id), None)
    if not existing_var:
        existing_var = next((v for v in flow_data.state if v.key == key), None)

    validated_default = validate_default_value_type(op.type, op.default_value)

    if existing_var is None:
        new_var = DefinerVariableSchema(
            id=op.id or str(uuid.uuid4()),
            key=key,
            type=op.type,
            default_value=validated_default,
            description=op.description,
        )
        flow_data.state.append(new_var)
    else:
        old_key = existing_var.key
        existing_var.key = key
        existing_var.type = op.type
        existing_var.default_value = validated_default
        existing_var.description = op.description

        if key != old_key:
            from app.graphs.expressions.utils import rename_variables_in_ast
            from app.graphs.variables import rename_node_variable_references

            for node in flow_data.nodes:
                rename_node_variable_references(node, old_key, key)
            for record in flow_data.expressions.values():
                rename_variables_in_ast(record.expr, old_key, key)

    return flow_data


def delete_variable(flow_data: GraphFlowData, op: DeleteVariableOp) -> GraphFlowData:
    var_key = op.key
    target_var = next((v for v in flow_data.state if v.key == var_key), None)
    if not target_var:
        return flow_data

    from app.graphs.variables import get_node_variable_references

    for node in flow_data.nodes:
        node_refs = get_node_variable_references(node, flow_data.expressions)
        if var_key in node_refs:
            raise ValidationError(f"Cannot delete variable '{var_key}' because it is referenced in node '{node.id}'.")

    flow_data.state = [v for v in flow_data.state if v.key != var_key]
    return flow_data


def define_expression(flow_data: GraphFlowData, op: DefineExpressionOp) -> GraphFlowData:
    flow_data.expressions[op.id] = ExpressionRecord(id=op.id, expr=op.expr)
    return flow_data
