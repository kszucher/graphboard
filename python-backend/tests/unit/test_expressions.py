import pytest

from app.core.exceptions import ValidationError
from app.modules.graphs import (
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


def test_expression_safety_and_rules() -> None:
    from app.modules.graphs import parse_expression

    # Test allowed functions
    assert parse_expression("len(name)") == "len(name)"
    assert parse_expression("str(10)") == "str(10)"
    assert parse_expression("random.choice(items)") == "random.choice(items)"
    assert parse_expression("random.sample(items, 2)") == "random.sample(items, 2)"
    assert parse_expression("random.sample(['A', 'B', 'C', 'D'], 2)") == "random.sample(['A', 'B', 'C', 'D'], 2)"

    # Test illegal functions/attributes
    with pytest.raises(ValidationError, match="Function call 'eval' is not allowed"):
        parse_expression("eval('1 + 1')")

    with pytest.raises(ValidationError, match="Only random.choice and random.sample"):
        parse_expression("random.randint(1, 10)")

    with pytest.raises(ValidationError, match="Only random.choice and random.sample"):
        parse_expression("os.system('clear')")


def test_parse_comparison_expression() -> None:
    from app.modules.graphs import parse_comparison_expression

    # Valid comparisons
    assert parse_comparison_expression("x > 5") == "x > 5"
    assert parse_comparison_expression("status == 'success'") == "status == 'success'"
    assert parse_comparison_expression("not flag") == "not flag"
    assert parse_comparison_expression("flag and active") == "flag and active"

    # Invalid comparisons (e.g. arithmetic or other expressions at the top level)
    with pytest.raises(ValidationError, match="is not a valid comparison expression"):
        parse_comparison_expression("x + 5")


def test_translate_polars_to_python() -> None:
    from app.modules.graphs import translate_polars_to_python

    # Valid translations
    assert translate_polars_to_python("col('score').eq(5)") == "score == 5"
    assert translate_polars_to_python("col('score').ne(5)") == "score != 5"
    assert translate_polars_to_python("col('score').gt(10) & col('more').lt(20)") == "score > 10 and more < 20"
    assert translate_polars_to_python("col('facts').len().gt(0)") == "len(facts) > 0"
    assert translate_polars_to_python("~col('more')") == "not more"
    assert translate_polars_to_python("col('answer').is_in(['A', 'B'])") == "answer in ['A', 'B']"

    # Validation errors
    with pytest.raises(ValidationError, match="Unsupported method or attribute call"):
        translate_polars_to_python("col('score').non_existent_method()")

    with pytest.raises(ValidationError, match="must be referenced using col"):
        translate_polars_to_python("score.eq(5)")

    with pytest.raises(ValidationError, match="is not defined in the graph state"):
        translate_polars_to_python("col('not_real').eq(5)", valid_variables={"score"})
