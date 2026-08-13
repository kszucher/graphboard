from __future__ import annotations

from app.graphs.expressions.schemas import (
    BinaryExpr,
    Expression,
    FunctionCallExpr,
    UnaryExpr,
    VariableExpr,
)


def get_variables_from_ast(expr: Expression) -> set[str]:
    match expr:
        case VariableExpr(name=name):
            return {name}
        case BinaryExpr(left=left, right=right):
            return get_variables_from_ast(left) | get_variables_from_ast(right)
        case UnaryExpr(argument=argument):
            return get_variables_from_ast(argument)
        case FunctionCallExpr(args=args):
            vars_set: set[str] = set()
            for arg in args:
                vars_set.update(get_variables_from_ast(arg))
            return vars_set
        case _:
            return set()


def rename_variables_in_ast(expr: Expression, old_key: str, new_key: str) -> None:
    match expr:
        case VariableExpr() as var:
            if var.name == old_key:
                var.name = new_key
        case BinaryExpr(left=left, right=right):
            rename_variables_in_ast(left, old_key, new_key)
            rename_variables_in_ast(right, old_key, new_key)
        case UnaryExpr(argument=argument):
            rename_variables_in_ast(argument, old_key, new_key)
        case FunctionCallExpr(args=args):
            for arg in args:
                rename_variables_in_ast(arg, old_key, new_key)


get_variables_from_comparison_ast = get_variables_from_ast
rename_variables_in_comparison_ast = rename_variables_in_ast
