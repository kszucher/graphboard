import pytest

from app.exceptions import ValidationError
from app.graphs.expressions import parse_expression
from app.graphs.schemas import (
    BinaryOpExpression,
    LiteralExpression,
    StateRefExpression,
    UnaryOpExpression,
)


def test_parse_expression_literals() -> None:
    assert parse_expression("10") == LiteralExpression(kind="literal", value=10)
    assert parse_expression("'hello'") == LiteralExpression(kind="literal", value="hello")
    assert parse_expression("True") == LiteralExpression(kind="literal", value=True)
    assert parse_expression("None") == LiteralExpression(kind="literal", value=None)


def test_parse_expression_name() -> None:
    assert parse_expression("score") == StateRefExpression(kind="stateRef", varKey="score")


def test_parse_expression_binops() -> None:
    assert parse_expression("score + 1") == BinaryOpExpression(
        kind="binaryOp",
        op="+",
        left=StateRefExpression(kind="stateRef", varKey="score"),
        right=LiteralExpression(kind="literal", value=1),
    )


def test_parse_expression_compares() -> None:
    assert parse_expression("parsed == correct") == BinaryOpExpression(
        kind="binaryOp",
        op="==",
        left=StateRefExpression(kind="stateRef", varKey="parsed"),
        right=StateRefExpression(kind="stateRef", varKey="correct"),
    )


def test_parse_expression_unary() -> None:
    assert parse_expression("not more_questions") == UnaryOpExpression(
        kind="unaryOp",
        op="not",
        expr=StateRefExpression(kind="stateRef", varKey="more_questions"),
    )


def test_parse_expression_errors() -> None:
    with pytest.raises(ValidationError):
        parse_expression("score +")  # syntax error
    with pytest.raises(ValidationError):
        parse_expression("score % 2")  # unsupported op
