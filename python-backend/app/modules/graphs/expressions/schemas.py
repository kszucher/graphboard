from __future__ import annotations

from typing import Any, TypeAlias

from pydantic import BaseModel, Field


class ComparisonFilter(BaseModel):
    equals: Any | None = Field(
        default=None, description="Matches exactly the value or another variable reference: {'var': 'name'}"
    )
    not_: Any | None = Field(default=None, alias="not", description="Negates matching value or filter")
    in_: list[Any] | None = Field(default=None, alias="in", description="Matches any value in the list")
    lt: Any | None = Field(default=None, description="Less than value or variable")
    lte: Any | None = Field(default=None, description="Less than or equal to")
    gt: Any | None = Field(default=None, description="Greater than")
    gte: Any | None = Field(default=None, description="Greater than or equal to")


class AtomicUpdate(BaseModel):
    increment: Any | None = Field(
        default=None, description="Increments number field by this value or other variable: {'var': 'name'}"
    )
    decrement: Any | None = Field(default=None, description="Decrements number field")
    multiply: Any | None = Field(default=None, description="Multiplies number field")
    divide: Any | None = Field(default=None, description="Divides number field")
    set: Any | None = Field(default=None, description="Sets field to this value or other variable: {'var': 'name'}")


Expression: TypeAlias = str | int | float | bool | dict[str, Any]
ComparisonExpression: TypeAlias = dict[str, Any]
