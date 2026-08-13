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
