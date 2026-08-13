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
    from app.graphs.schemas import ExpressionRecord

    # Test ExpressionRecord parsing structured JSON into a string
    record = ExpressionRecord.model_validate(
        {
            "id": "expr_score_plus_1",
            "expr": {
                "type": "binary",
                "left": {"type": "variable", "name": "score"},
                "op": "+",
                "right": {"type": "literal", "value": 1},
            },
        }
    )
    assert record.expr is not None
    assert record.expr.to_string() == "(score + 1)"


def test_copilot_tools_schema_restrictions() -> None:
    import json

    import tiktoken

    from app.copilot.tools import ALL_FLAT_TOOLS, STATE_TOOLS, TOPOLOGY_TOOLS, CONFIG_TOOLS

    encoding = tiktoken.get_encoding("cl100k_base")
    # 1. Token budget per sub-agent must be under 4000
    for agent_tools, name in [(STATE_TOOLS, "state"), (TOPOLOGY_TOOLS, "topology"), (CONFIG_TOOLS, "config")]:
        tokens = len(encoding.encode(json.dumps(agent_tools, indent=2)))
        assert tokens < 4000, f"{name} schemas exceed 4000 token limit: {tokens}"

    # 2. define_expression is the sole carrier of the AST — must have func enum constraint
    expr_tool = ALL_FLAT_TOOLS["define_expression"]
    expr_schema_str = json.dumps(expr_tool)
    assert "random.choice" in expr_schema_str, "func enum must include random.choice"
    assert "random.sample" in expr_schema_str, "func enum must include random.sample"

    # 3. Assigner and switch tools must NOT embed expression schema (no AST bleed)
    assigner_schema_str = json.dumps(ALL_FLAT_TOOLS["bind_logical_assignment"])
    assert "random.choice" not in assigner_schema_str, "assigner must not carry expression schema"

    switch_schema_str = json.dumps(ALL_FLAT_TOOLS["bind_branch_condition"])
    assert "random.choice" not in switch_schema_str, "switch must not carry expression schema"

    # 4. No $defs blocks should remain (all refs inlined and dropped)
    for tool in ALL_FLAT_TOOLS.values():
        assert "$defs" not in json.dumps(tool), f"Tool {tool['function']['name']} still has $defs"
