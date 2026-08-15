import pytest

from app.core.exceptions import ValidationError
from app.modules.graphs.expressions import (
    expression_to_code,
    get_expression_variables,
    rename_expression_variables,
)


def test_expression_to_code() -> None:
    valid_keys = {"score", "more", "limit", "user_input", "parsed_answer", "correct_answer"}

    # Basic comparison
    assert expression_to_code({"score": {"gt": 5}}, valid_keys) == "(state.get('score') > 5)"
    assert expression_to_code({"score": {"equals": 10}}, valid_keys) == "(state.get('score') == 10)"

    # Shorthand comparison
    assert expression_to_code({"score": 10}, valid_keys) == "(state.get('score') == 10)"

    # Comparison with variable reference
    assert (
        expression_to_code({"parsed_answer": {"equals": {"var": "correct_answer"}}}, valid_keys)
        == "(state.get('parsed_answer') == state.get('correct_answer'))"
    )

    # Logical composition
    assert (
        expression_to_code({"AND": [{"score": {"gt": 5}}, {"more": {"equals": False}}]}, valid_keys)
        == "((state.get('score') > 5) and (state.get('more') == False))"
    )

    # Set assignment
    assert expression_to_code({"set": {"var": "user_input"}}, valid_keys) == "state.get('user_input')"
    assert expression_to_code({"set": "hello"}, valid_keys) == "'hello'"
    assert expression_to_code(10, valid_keys) == "10"


def test_expression_to_code_errors() -> None:
    valid_keys = {"score"}

    # Undefined variable reference
    with pytest.raises(ValidationError, match="Variable 'not_real' is not defined"):
        expression_to_code({"score": {"gt": {"var": "not_real"}}}, valid_keys)

    with pytest.raises(ValidationError, match="Variable 'not_real' is not defined"):
        expression_to_code({"not_real": {"gt": 5}}, valid_keys)


def test_get_expression_variables() -> None:
    # Variable key and nested variable reference
    assert get_expression_variables({"score": {"gt": 5}}) == {"score"}
    assert get_expression_variables({"parsed_answer": {"equals": {"var": "correct_answer"}}}) == {
        "parsed_answer",
        "correct_answer",
    }

    # Logical composition variables
    assert get_expression_variables({"AND": [{"score": {"gt": 5}}, {"more": {"equals": {"var": "limit"}}}]}) == {
        "score",
        "more",
        "limit",
    }

    # Assignment variables
    assert get_expression_variables({"set": {"var": "user_input"}}) == {"user_input"}
    assert get_expression_variables(10) == set()


def test_rename_expression_variables() -> None:
    # Rename queried variable
    assert rename_expression_variables({"score": {"gt": 5}}, "score", "points") == {"points": {"gt": 5}}

    # Rename variable reference value
    assert rename_expression_variables({"parsed_answer": {"equals": {"var": "score"}}}, "score", "points") == {
        "parsed_answer": {"equals": {"var": "points"}}
    }

    # Rename nested composition
    expr = {"AND": [{"score": {"gt": 5}}, {"more": {"equals": {"var": "limit"}}}]}
    expected = {"AND": [{"points": {"gt": 5}}, {"more": {"equals": {"var": "limit"}}}]}
    assert rename_expression_variables(expr, "score", "points") == expected
