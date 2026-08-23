from __future__ import annotations

import ast
from typing import Any, TypeAlias

from app.core.exceptions import ValidationError

Expression: TypeAlias = str | int | float | bool
ComparisonExpression: TypeAlias = str | bool

ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.BoolOp,
    ast.Constant,
    ast.Name,
    ast.List,
    ast.Dict,
    ast.Tuple,
    ast.Set,
    ast.Subscript,
    ast.Slice,
    ast.FormattedValue,
    ast.JoinedStr,
    ast.Call,
    ast.Attribute,
    ast.IfExp,
    # Operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.Invert,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
    ast.Load,
)

ALLOWED_BUILTIN_FUNCTIONS = {
    "len",
    "min",
    "max",
    "round",
    "int",
    "float",
    "str",
    "bool",
    "list",
    "dict",
    "set",
    "abs",
    "sum",
    "sample",
    "choice",
    "random_int",
    "random_float",
}


class SafeExpressionValidator(ast.NodeVisitor):
    """Validates that a Python expression string conforms to safe AST invariants and valid state keys."""

    def __init__(self, valid_state_keys: set[str] | None = None):
        self.valid_state_keys = valid_state_keys
        self.referenced_vars: set[str] = set()

    def generic_visit(self, node: ast.AST) -> None:
        if not isinstance(node, ALLOWED_AST_NODES):
            raise ValidationError(f"Forbidden syntax in expression: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in ALLOWED_BUILTIN_FUNCTIONS or node.id in {"random", "True", "False", "None"}:
            return
        if self.valid_state_keys is not None and node.id not in self.valid_state_keys:
            raise ValidationError(f"Variable '{node.id}' is not defined in the graph state.")
        self.referenced_vars.add(node.id)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id not in ALLOWED_BUILTIN_FUNCTIONS:
                raise ValidationError(f"Unauthorized function call: '{node.func.id}()'.")
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "random":
                if node.func.attr not in {"randint", "choice", "sample", "uniform", "random"}:
                    raise ValidationError(f"Unauthorized random function: 'random.{node.func.attr}()'.")
            else:
                if node.func.attr.startswith("_"):
                    raise ValidationError(f"Dunder or private attribute access forbidden: '{node.func.attr}'.")
        else:
            raise ValidationError("Unsupported function call target.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise ValidationError(f"Dunder attribute access forbidden: '{node.attr}'.")
        self.generic_visit(node)


class VariableRenamer(ast.NodeTransformer):
    def __init__(self, old_key: str, new_key: str):
        self.old_key = old_key
        self.new_key = new_key

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id == self.old_key:
            return ast.copy_location(ast.Name(id=self.new_key, ctx=node.ctx), node)
        return node


def validate_expression(expr_data: Any | None, valid_keys: set[str] | None = None) -> set[str]:
    """Validates an expression and returns referenced variable names."""
    if expr_data is None:
        return set()
    if isinstance(expr_data, (int, float, bool)):
        return set()
    if not isinstance(expr_data, str) or not expr_data.strip():
        return set()

    try:
        tree = ast.parse(expr_data.strip(), mode="eval")
    except SyntaxError as e:
        raise ValidationError(f"Syntax error in expression '{expr_data}': {e}")

    validator = SafeExpressionValidator(valid_keys)
    validator.visit(tree)
    return validator.referenced_vars


def expression_to_code(
    expr_data: Any | None,
    valid_keys: set[str] | None = None,
    fallback: str = "True",
    target_var_key: str | None = None,
) -> str:
    """Validates and returns the executable Python expression code."""
    if expr_data is None:
        return fallback
    if isinstance(expr_data, bool):
        return "True" if expr_data else "False"
    if isinstance(expr_data, (int, float)):
        return str(expr_data)
    if isinstance(expr_data, str):
        cleaned = expr_data.strip()
        if not cleaned:
            return fallback
        validate_expression(cleaned, valid_keys)
        return cleaned
    return fallback


def get_expression_variables(expr_data: Any | None) -> set[str]:
    """Recursively extracts all variable name references from the expression."""
    if expr_data is None:
        return set()
    if not isinstance(expr_data, str) or not expr_data.strip():
        return set()
    try:
        tree = ast.parse(expr_data.strip(), mode="eval")
        validator = SafeExpressionValidator()
        validator.visit(tree)
        return validator.referenced_vars
    except Exception:
        return set()


def rename_expression_variables(expr_data: Any | None, old_key: str, new_key: str) -> Any | None:
    """Renames variable references inside the expression string."""
    if expr_data is None or not isinstance(expr_data, str) or not expr_data.strip():
        return expr_data
    try:
        tree = ast.parse(expr_data.strip(), mode="eval")
        renamer = VariableRenamer(old_key, new_key)
        new_tree = renamer.visit(tree)
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)
    except Exception:
        return expr_data
