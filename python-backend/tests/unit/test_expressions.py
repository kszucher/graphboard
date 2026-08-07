import pytest

from app.exceptions import ValidationError
from app.graphs.expressions import (
    expression_to_code,
    get_expression_variables,
    parse_expression,
    rename_expression_variables,
)


def test_parse_expression_valid() -> None:
    assert parse_expression("10") == "10"
    assert parse_expression("'hello'") == "'hello'"
    assert parse_expression("True") == "True"
    assert parse_expression("None") == "None"
    assert parse_expression("score") == "score"
    assert parse_expression("score + 1") == "score + 1"
    assert parse_expression("parsed == correct") == "parsed == correct"
    assert parse_expression("not more_questions") == "not more_questions"


def test_parse_expression_errors() -> None:
    with pytest.raises(ValidationError):
        parse_expression("score +")  # syntax error


def test_get_expression_variables() -> None:
    assert get_expression_variables("score + 1") == {"score"}
    assert get_expression_variables("parsed == correct") == {"parsed", "correct"}
    assert get_expression_variables("not more_questions") == {"more_questions"}
    assert get_expression_variables("10 + 20") == set()
    assert get_expression_variables("True") == set()
    assert get_expression_variables(None) == set()


def test_rename_expression_variables() -> None:
    assert rename_expression_variables("score + 1", "score", "points") == "points + 1"
    assert rename_expression_variables("parsed == correct", "correct", "expected") == "parsed == expected"
    assert rename_expression_variables("not more_questions", "more_questions", "active") == "not active"
    assert rename_expression_variables("10 + 20", "x", "y") == "10 + 20"
    assert rename_expression_variables(None, "x", "y") is None


def test_expression_to_code() -> None:
    valid_keys = {"score", "parsed", "correct"}
    assert expression_to_code("score + 1", valid_keys) == "state.get('score') + 1"
    assert expression_to_code("parsed == correct", valid_keys) == "state.get('parsed') == state.get('correct')"
    assert expression_to_code("10 + 20", valid_keys) == "10 + 20"
    assert expression_to_code(None, valid_keys, fallback="False") == "False"
