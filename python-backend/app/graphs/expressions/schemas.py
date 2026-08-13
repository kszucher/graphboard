from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class LiteralExpr(BaseModel):
    type: Literal["literal"] = "literal"
    value: str | int | float | bool | None

    def to_string(self) -> str:
        return repr(self.value)


class VariableExpr(BaseModel):
    type: Literal["variable"] = "variable"
    name: str

    def to_string(self) -> str:
        return self.name


class BinaryExpr(BaseModel):
    type: Literal["binary"] = "binary"
    left: Expression
    op: Literal["+", "-", "*", "/", "%", "and", "or", "==", "!=", "<", ">", "<=", ">="]
    right: Expression

    def to_string(self) -> str:
        return f"({self.left.to_string()} {self.op} {self.right.to_string()})"


class UnaryExpr(BaseModel):
    type: Literal["unary"] = "unary"
    op: Literal["not", "-", "+"]
    argument: Expression

    def to_string(self) -> str:
        space = " " if self.op == "not" else ""
        return f"({self.op}{space}{self.argument.to_string()})"


class FunctionCallExpr(BaseModel):
    type: Literal["call"] = "call"
    func: Literal["str", "int", "float", "bool", "len", "random.choice", "random.sample"]
    args: list[Expression]

    def to_string(self) -> str:
        return f"{self.func}({', '.join(a.to_string() for a in self.args)})"


Expression = Annotated[
    LiteralExpr | VariableExpr | BinaryExpr | UnaryExpr | FunctionCallExpr,
    Field(discriminator="type"),
]

BinaryExpr.model_rebuild()
UnaryExpr.model_rebuild()
FunctionCallExpr.model_rebuild()


class ComparisonExpr(BaseModel):
    type: Literal["comparison"] = "comparison"
    left: Expression
    op: Literal["==", "!=", "<", ">", "<=", ">="]
    right: Expression

    def to_string(self) -> str:
        return f"({self.left.to_string()} {self.op} {self.right.to_string()})"


class LogicalExpr(BaseModel):
    type: Literal["logical"] = "logical"
    left: ComparisonExpression
    op: Literal["and", "or"]
    right: ComparisonExpression

    def to_string(self) -> str:
        return f"({self.left.to_string()} {self.op} {self.right.to_string()})"


class NotExpr(BaseModel):
    type: Literal["not"] = "not"
    argument: ComparisonExpression

    def to_string(self) -> str:
        return f"(not {self.argument.to_string()})"


ComparisonExpression = Annotated[
    ComparisonExpr | LogicalExpr | NotExpr | VariableExpr | LiteralExpr,
    Field(discriminator="type"),
]

LogicalExpr.model_rebuild()
NotExpr.model_rebuild()


def get_variables_from_ast(expr: Expression) -> set[str]:
    vars_set: set[str] = set()
    if isinstance(expr, VariableExpr):
        vars_set.add(expr.name)
    elif isinstance(expr, BinaryExpr):
        vars_set.update(get_variables_from_ast(expr.left))
        vars_set.update(get_variables_from_ast(expr.right))
    elif isinstance(expr, UnaryExpr):
        vars_set.update(get_variables_from_ast(expr.argument))
    elif isinstance(expr, FunctionCallExpr):
        for arg in expr.args:
            vars_set.update(get_variables_from_ast(arg))
    return vars_set


def get_variables_from_comparison_ast(expr: ComparisonExpression) -> set[str]:
    vars_set: set[str] = set()
    if isinstance(expr, ComparisonExpr):
        vars_set.update(get_variables_from_ast(expr.left))
        vars_set.update(get_variables_from_ast(expr.right))
    elif isinstance(expr, LogicalExpr):
        vars_set.update(get_variables_from_comparison_ast(expr.left))
        vars_set.update(get_variables_from_comparison_ast(expr.right))
    elif isinstance(expr, NotExpr):
        vars_set.update(get_variables_from_comparison_ast(expr.argument))
    elif isinstance(expr, VariableExpr):
        vars_set.add(expr.name)
    return vars_set


def rename_variables_in_ast(expr: Expression, old_key: str, new_key: str) -> None:
    if isinstance(expr, VariableExpr):
        if expr.name == old_key:
            expr.name = new_key
    elif isinstance(expr, BinaryExpr):
        rename_variables_in_ast(expr.left, old_key, new_key)
        rename_variables_in_ast(expr.right, old_key, new_key)
    elif isinstance(expr, UnaryExpr):
        rename_variables_in_ast(expr.argument, old_key, new_key)
    elif isinstance(expr, FunctionCallExpr):
        for arg in expr.args:
            rename_variables_in_ast(arg, old_key, new_key)


def rename_variables_in_comparison_ast(expr: ComparisonExpression, old_key: str, new_key: str) -> None:
    if isinstance(expr, ComparisonExpr):
        rename_variables_in_ast(expr.left, old_key, new_key)
        rename_variables_in_ast(expr.right, old_key, new_key)
    elif isinstance(expr, LogicalExpr):
        rename_variables_in_comparison_ast(expr.left, old_key, new_key)
        rename_variables_in_comparison_ast(expr.right, old_key, new_key)
    elif isinstance(expr, NotExpr):
        rename_variables_in_comparison_ast(expr.argument, old_key, new_key)
    elif isinstance(expr, VariableExpr):
        if expr.name == old_key:
            expr.name = new_key
    elif isinstance(expr, BinaryExpr):
        rename_variables_in_ast(expr, old_key, new_key)
    elif isinstance(expr, UnaryExpr):
        rename_variables_in_ast(expr, old_key, new_key)
    elif isinstance(expr, FunctionCallExpr):
        rename_variables_in_ast(expr, old_key, new_key)
