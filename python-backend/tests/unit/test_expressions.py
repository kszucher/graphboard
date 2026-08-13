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


def test_expression_safety_and_rules() -> None:
    from app.graphs.expressions import parse_expression

    # Test allowed functions
    assert parse_expression("len(name)") == "len(name)"
    assert parse_expression("str(10)") == "str(10)"
    assert parse_expression("random.choice(items)") == "random.choice(items)"
    assert parse_expression("random.sample(items, 2)") == "random.sample(items, 2)"

    # Test illegal functions/attributes
    with pytest.raises(ValidationError, match="Function call 'eval' is not allowed"):
        parse_expression("eval('1 + 1')")

    with pytest.raises(ValidationError, match="Only random.choice and random.sample"):
        parse_expression("random.randint(1, 10)")

    with pytest.raises(ValidationError, match="Only random.choice and random.sample"):
        parse_expression("os.system('clear')")


def test_parse_comparison_expression() -> None:
    from app.graphs.expressions import parse_comparison_expression

    # Valid comparisons
    assert parse_comparison_expression("x > 5") == "x > 5"
    assert parse_comparison_expression("status == 'success'") == "status == 'success'"
    assert parse_comparison_expression("not flag") == "not flag"
    assert parse_comparison_expression("flag and active") == "flag and active"

    # Invalid comparisons (e.g. arithmetic or other expressions at the top level)
    with pytest.raises(ValidationError, match="is not a valid comparison expression"):
        parse_comparison_expression("x + 5")


def test_structured_expression_pydantic_parsing() -> None:
    from app.graphs.nodes import Branch, LogicalAssignmentSchema

    # Test assignments parsing structured JSON into a string
    assignment = LogicalAssignmentSchema.model_validate(
        {
            "target_var_key": "score",
            "expression": {
                "type": "binary",
                "left": {"type": "variable", "name": "score"},
                "op": "+",
                "right": {"type": "literal", "value": 1},
            },
        }
    )
    assert assignment.expression is not None
    assert assignment.expression.to_string() == "(score + 1)"

    # Test branches parsing structured JSON into a string
    branch = Branch.model_validate(
        {
            "label": "Option A",
            "expression": {
                "type": "comparison",
                "left": {"type": "variable", "name": "score"},
                "op": ">",
                "right": {"type": "literal", "value": 10},
            },
        }
    )
    assert branch.expression is not None
    assert branch.expression.to_string() == "(score > 10)"


def test_copilot_tools_schema_restrictions() -> None:
    from app.copilot.tools import ALL_FLAT_TOOLS

    # Verify that the LLM tools do not accept string type for expression fields
    switch_tool = ALL_FLAT_TOOLS["upsert_logical_switch"]
    # Check that in the schema, branches items expression does NOT contain "string"
    defs = switch_tool["function"]["parameters"]["$defs"]
    branch_schema = defs["Branch"]
    expr_schema = branch_schema["properties"]["expression"]
    # Verify that string type is not anywhere in the expression options
    if "anyOf" in expr_schema:
        types = [item.get("type") for item in expr_schema["anyOf"] if "type" in item]
        assert "string" not in types
    else:
        # If it is a direct oneOf/ref discriminator, string is definitely excluded
        assert expr_schema.get("type") != "string"
