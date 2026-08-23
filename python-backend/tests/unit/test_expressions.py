import pytest

from app.core.exceptions import ValidationError
from app.modules.graphs.schemas import (
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


def test_orthogonal_math_expressions() -> None:
    valid_keys = {"score", "bonus", "multiplier"}

    # Binary arithmetic
    assert (
        expression_to_code({"op": "add", "left": {"var": "score"}, "right": 10}, valid_keys)
        == "(state.get('score') + 10)"
    )
    assert (
        expression_to_code({"op": "multiply", "left": {"var": "score"}, "right": {"var": "multiplier"}}, valid_keys)
        == "(state.get('score') * state.get('multiplier'))"
    )
    assert (
        expression_to_code({"op": "modulo", "left": {"var": "score"}, "right": 2}, valid_keys)
        == "(state.get('score') % 2)"
    )

    # Functions
    assert (
        expression_to_code({"op": "round", "val": {"var": "score"}, "ndigits": 2}, valid_keys)
        == "round(state.get('score'), 2)"
    )
    assert (
        expression_to_code({"op": "max", "args": [{"var": "score"}, {"var": "bonus"}, 100]}, valid_keys)
        == "max(state.get('score'), state.get('bonus'), 100)"
    )

    # Random numbers
    assert expression_to_code({"op": "random_int", "min": 1, "max": 6}, valid_keys) == "random.randint(1, 6)"
    assert expression_to_code({"op": "random_float", "min": 0.0, "max": 1.0}, valid_keys) == "random.uniform(0.0, 1.0)"


def test_orthogonal_string_expressions() -> None:
    valid_keys = {"question", "options", "csv_line"}

    # Template format
    assert (
        expression_to_code(
            {"op": "format", "template": "Q: {question}\nOpts: {options}", "vars": ["question", "options"]}, valid_keys
        )
        == "'Q: {question}\\nOpts: {options}'.format(question=state.get('question'), options=state.get('options'))"
    )

    # Join
    assert (
        expression_to_code({"op": "join", "list": {"var": "options"}, "sep": "\n"}, valid_keys)
        == "'\\n'.join(str(x) for x in (state.get('options') or []))"
    )

    # Split
    assert (
        expression_to_code({"op": "split", "str": {"var": "csv_line"}, "sep": ","}, valid_keys)
        == "(state.get('csv_line') or '').split(',')"
    )


def test_orthogonal_collection_expressions() -> None:
    valid_keys = {"options", "wrong_options", "correct_answer"}

    # Sample & Choice
    assert (
        expression_to_code({"op": "sample", "list": {"var": "options"}, "count": 2}, valid_keys)
        == "random.sample((state.get('options') or []), min(len(state.get('options') or []), 2))"
    )
    assert (
        expression_to_code({"op": "choice", "list": {"var": "options"}}, valid_keys)
        == "(random.choice(state.get('options')) if (state.get('options')) else None)"
    )

    # Remove item from list
    assert (
        expression_to_code({"op": "remove", "list": {"var": "options"}, "item": {"var": "correct_answer"}}, valid_keys)
        == "[x for x in (state.get('options') or []) if (x not in state.get('correct_answer') if isinstance(state.get('correct_answer'), list) else x != state.get('correct_answer'))]"
    )

    # Append
    assert (
        expression_to_code({"op": "append", "list": {"var": "options"}, "item": "Option D"}, valid_keys)
        == "((state.get('options') or []) + ['Option D'])"
    )

    # Length & Slice
    assert (
        expression_to_code({"op": "length", "list": {"var": "options"}}, valid_keys)
        == "len(state.get('options') or [])"
    )
    assert (
        expression_to_code({"op": "slice", "list": {"var": "options"}, "start": 0, "end": 2}, valid_keys)
        == "((state.get('options') or [])[0:2])"
    )


def test_orthogonal_variable_extraction_and_renaming() -> None:
    expr = {
        "op": "remove",
        "list": {"var": "options"},
        "item": {"var": "correct_answer"},
    }
    assert get_expression_variables(expr) == {"options", "correct_answer"}

    renamed = rename_expression_variables(expr, "options", "all_choices")
    assert renamed == {
        "op": "remove",
        "list": {"var": "all_choices"},
        "item": {"var": "correct_answer"},
    }
