import pytest

from app.core.exceptions import ValidationError
from app.modules.graphs.schemas import (
    expression_to_code,
    get_expression_variables,
    rename_expression_variables,
)


def test_expression_to_code() -> None:
    valid_keys = {"score", "more", "limit", "user_input", "parsed_answer", "correct_answer", "options"}

    # Basic comparison
    assert expression_to_code("score > 5", valid_keys) == "score > 5"
    assert expression_to_code("score == 10", valid_keys) == "score == 10"
    assert expression_to_code("score != 10", valid_keys) == "score != 10"

    # Comparison with variable reference
    assert expression_to_code("parsed_answer == correct_answer", valid_keys) == "parsed_answer == correct_answer"

    # Logical composition
    assert expression_to_code("score > 5 and not more", valid_keys) == "score > 5 and not more"

    # Assignment expressions
    assert expression_to_code("score + 10", valid_keys) == "score + 10"
    assert expression_to_code("'hello'", valid_keys) == "'hello'"
    assert expression_to_code(10, valid_keys) == "10"
    assert expression_to_code(True, valid_keys) == "True"


def test_expression_to_code_errors() -> None:
    valid_keys = {"score"}

    # Undefined variable reference
    with pytest.raises(ValidationError, match="Variable 'not_real' is not defined"):
        expression_to_code("score > not_real", valid_keys)

    # Unauthorized function / dunder access
    with pytest.raises(ValidationError, match="Dunder attribute access forbidden"):
        expression_to_code("score.__class__", valid_keys)

    with pytest.raises(ValidationError, match="Variable 'os' is not defined"):
        expression_to_code("os.system('ls')", valid_keys)

    with pytest.raises(ValidationError, match="Unauthorized function call"):
        expression_to_code("exec('1')", valid_keys | {"exec"})


def test_get_expression_variables() -> None:
    assert get_expression_variables("score > 5") == {"score"}
    assert get_expression_variables("parsed_answer == correct_answer") == {"parsed_answer", "correct_answer"}
    assert get_expression_variables("score > 5 and more == limit") == {"score", "more", "limit"}
    assert get_expression_variables("user_input") == {"user_input"}
    assert get_expression_variables(10) == set()
    assert get_expression_variables(None) == set()


def test_rename_expression_variables() -> None:
    assert rename_expression_variables("score > 5", "score", "points") == "points > 5"
    assert rename_expression_variables("parsed_answer == score", "score", "points") == "parsed_answer == points"
    assert (
        rename_expression_variables("score > 5 and more == limit", "score", "points")
        == "points > 5 and more == limit"
    )


def test_allowed_functions_and_builtins() -> None:
    valid_keys = {"score", "options", "bonus"}

    assert expression_to_code("min(100, score + 10)", valid_keys) == "min(100, score + 10)"
    assert expression_to_code("len(options)", valid_keys) == "len(options)"
    assert expression_to_code("random.choice(options)", valid_keys) == "random.choice(options)"
    assert expression_to_code("random.randint(1, 10)", valid_keys) == "random.randint(1, 10)"
