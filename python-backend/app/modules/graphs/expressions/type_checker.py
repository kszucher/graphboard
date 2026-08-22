from __future__ import annotations

from typing import Any

from app.modules.graphs.schemas import VariableType

MATH_OPS = {"add", "subtract", "multiply", "divide", "modulo", "round", "random_int", "random_float", "length"}
ARRAY_OPS = {"sample", "remove", "append", "slice", "split"}
STRING_OPS = {"format", "join"}


def infer_expression_type(expr_data: Any, var_types: dict[str, VariableType]) -> VariableType | None:
    """Infers the VariableType result of an expression given existing variable type definitions."""
    if expr_data is None:
        return None

    if isinstance(expr_data, bool):
        return "boolean"
    if isinstance(expr_data, (int, float)):
        return "number"
    if isinstance(expr_data, str):
        return "string"
    if isinstance(expr_data, list):
        return "array"

    if isinstance(expr_data, dict):
        if "var" in expr_data and isinstance(expr_data["var"], str):
            return var_types.get(expr_data["var"])

        if "set" in expr_data:
            return infer_expression_type(expr_data["set"], var_types)

        atomic_ops = {"increment", "decrement", "multiply", "divide"}
        if any(op in expr_data for op in atomic_ops):
            return "number"

        if "AND" in expr_data or "OR" in expr_data or "NOT" in expr_data:
            return "boolean"

        if "op" in expr_data:
            op = expr_data["op"]
            if op in MATH_OPS:
                return "number"
            if op in STRING_OPS:
                return "string"
            if op in ARRAY_OPS:
                return "array"
            if op == "choice":
                # Could be any element type of the collection
                return None

        # Check for field comparisons e.g. {"score": {"gt": 5}}
        if any(isinstance(v, dict) for v in expr_data.values()):
            return "boolean"

    return None
