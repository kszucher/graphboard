from __future__ import annotations

import ast
from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter

from app.exceptions import ValidationError
from app.graphs.schemas import (
    BinaryOpExpression,
    Expression,
    LiteralExpression,
    StateRefExpression,
    UnaryOpExpression,
)


def parse_expression(expr_str_or_dict: str | dict[str, Any] | Expression | None) -> Expression | None:
    """Parses a Python expression string into the custom AST Expression schema.

    If given an Expression or None, returns it directly. If given a dictionary,
    validates it using Pydantic.
    """
    if expr_str_or_dict is None:
        return None

    if isinstance(expr_str_or_dict, BaseModel):
        return expr_str_or_dict

    if isinstance(expr_str_or_dict, dict):
        try:
            return TypeAdapter(Expression).validate_python(expr_str_or_dict)
        except Exception as e:
            raise ValidationError(f"Invalid expression dictionary structure: {e}")

    clean_str = expr_str_or_dict.strip()
    if not clean_str:
        return None

    try:
        tree = ast.parse(clean_str, mode="eval")
        return _convert_node(tree.body)
    except SyntaxError as e:
        raise ValidationError(f"Invalid expression syntax in '{clean_str}': {e.msg}")
    except ValueError as e:
        raise ValidationError(str(e))


def _convert_node(node: ast.AST) -> Expression:
    if isinstance(node, ast.Constant):
        return LiteralExpression(kind="literal", value=node.value)

    elif isinstance(node, ast.Name):
        # Handle booleans / None (just in case they are parsed as Names depending on Python version/context)
        if node.id == "True":
            return LiteralExpression(kind="literal", value=True)
        elif node.id == "False":
            return LiteralExpression(kind="literal", value=False)
        elif node.id == "None":
            return LiteralExpression(kind="literal", value=None)
        return StateRefExpression(kind="stateRef", varKey=node.id)

    elif isinstance(node, ast.BinOp):
        bin_op_map: dict[type[ast.operator], Literal["+", "-", "*", "/"]] = {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.Div: "/",
        }
        bin_op_type = type(node.op)
        if bin_op_type not in bin_op_map:
            raise ValidationError(f"Unsupported mathematical operator: {bin_op_type.__name__}")
        return BinaryOpExpression(
            kind="binaryOp",
            op=bin_op_map[bin_op_type],
            left=_convert_node(node.left),
            right=_convert_node(node.right),
        )

    elif isinstance(node, ast.Compare):
        cmp_op_map: dict[type[ast.cmpop], Literal["==", "!=", "<", "<=", ">", ">="]] = {
            ast.Eq: "==",
            ast.NotEq: "!=",
            ast.Lt: "<",
            ast.LtE: "<=",
            ast.Gt: ">",
            ast.GtE: ">=",
        }
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValidationError("Only simple binary comparisons are supported (e.g. x == y).")
        cmp_op_type = type(node.ops[0])
        if cmp_op_type not in cmp_op_map:
            raise ValidationError(f"Unsupported comparison operator: {cmp_op_type.__name__}")
        return BinaryOpExpression(
            kind="binaryOp",
            op=cmp_op_map[cmp_op_type],
            left=_convert_node(node.left),
            right=_convert_node(node.comparators[0]),
        )

    elif isinstance(node, ast.UnaryOp):
        unary_op_map: dict[type[ast.unaryop], Literal["not"]] = {
            ast.Not: "not",
        }
        unary_op_type = type(node.op)
        if unary_op_type not in unary_op_map:
            raise ValidationError(f"Unsupported unary operator: {unary_op_type.__name__}")
        return UnaryOpExpression(
            kind="unaryOp",
            op=unary_op_map[unary_op_type],
            expr=_convert_node(node.operand),
        )

    else:
        raise ValidationError(f"Unsupported expression construct: {type(node).__name__}")


def expression_to_code(node: Expression | None, fallback: str = "True") -> str:
    """Converts a visual AST expression to Python code string."""
    if not node:
        return fallback

    if isinstance(node, LiteralExpression):
        return repr(node.value)
    if isinstance(node, StateRefExpression):
        return f"state.get({repr(node.varKey)})"
    if isinstance(node, BinaryOpExpression):
        op = node.op
        left = expression_to_code(node.left, fallback)
        right = expression_to_code(node.right, fallback)
        return f"({left} {op} {right})"
    if isinstance(node, UnaryOpExpression):
        op_str = node.op
        expr_str = expression_to_code(node.expr, fallback)
        return f"({op_str} {expr_str})"

    return fallback


def get_expression_variables(expr: Expression | None) -> set[str]:
    """Recursively traverses the expression AST and returns all referenced state keys."""
    if not expr:
        return set()

    if isinstance(expr, StateRefExpression):
        return {expr.varKey} if expr.varKey else set()
    elif isinstance(expr, BinaryOpExpression):
        return get_expression_variables(expr.left) | get_expression_variables(expr.right)
    elif isinstance(expr, UnaryOpExpression):
        return get_expression_variables(expr.expr)

    return set()


def rename_expression_variables(expr: Expression | None, old_key: str, new_key: str) -> None:
    """Recursively walks the expression AST and renames matching state reference keys in-place."""
    if not expr:
        return

    if isinstance(expr, StateRefExpression):
        if expr.varKey == old_key:
            expr.varKey = new_key
    elif isinstance(expr, BinaryOpExpression):
        rename_expression_variables(expr.left, old_key, new_key)
        rename_expression_variables(expr.right, old_key, new_key)
    elif isinstance(expr, UnaryOpExpression):
        rename_expression_variables(expr.expr, old_key, new_key)
