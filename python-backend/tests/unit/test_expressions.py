import pytest

from app.exceptions import ValidationError
from app.graphs.expressions import parse_expression


def test_parse_expression_literals() -> None:
    assert parse_expression("10") == {"kind": "literal", "value": 10}
    assert parse_expression("'hello'") == {"kind": "literal", "value": "hello"}
    assert parse_expression("True") == {"kind": "literal", "value": True}
    assert parse_expression("None") == {"kind": "literal", "value": None}


def test_parse_expression_name() -> None:
    assert parse_expression("score") == {"kind": "stateRef", "varKey": "score"}


def test_parse_expression_binops() -> None:
    assert parse_expression("score + 1") == {
        "kind": "binaryOp",
        "op": "+",
        "left": {"kind": "stateRef", "varKey": "score"},
        "right": {"kind": "literal", "value": 1},
    }


def test_parse_expression_compares() -> None:
    assert parse_expression("parsed == correct") == {
        "kind": "binaryOp",
        "op": "==",
        "left": {"kind": "stateRef", "varKey": "parsed"},
        "right": {"kind": "stateRef", "varKey": "correct"},
    }


def test_parse_expression_unary() -> None:
    assert parse_expression("not more_questions") == {
        "kind": "unaryOp",
        "op": "not",
        "expr": {"kind": "stateRef", "varKey": "more_questions"},
    }


def test_parse_expression_errors() -> None:
    with pytest.raises(ValidationError):
        parse_expression("score +")  # syntax error
    with pytest.raises(ValidationError):
        parse_expression("score % 2")  # unsupported op
