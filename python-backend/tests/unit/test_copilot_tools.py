from app.copilot.tools import translate_tool_calls_to_operations
from app.graphs.expressions.schemas import LiteralExpr
from app.graphs.mutations import sort_operations_by_dependency
from app.graphs.nodes import (
    Branch,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
)
from app.graphs.schemas import (
    ConnectOp,
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
    UpsertLogicalSwitchOp,
    UpsertStateVarOp,
)
from app.graphs.serializer import serialize_flow_to_code


def test_serialize_flow_to_code() -> None:
    from app.graphs.schemas import ExpressionRecord

    flow = GraphFlowData(
        state=[DefinerVariableSchema(id="v1", key="score", type="number", default_value=10)],
        expressions={
            "expr_1": ExpressionRecord(id="expr_1", expr=LiteralExpr(value=10)),
            "expr_2": ExpressionRecord(id="expr_2", expr=LiteralExpr(value=True)),
        },
        nodes=[
            LogicalAssignerNode(
                id="init",
                assignments=[
                    LogicalAssignmentSchema(
                        id="a1",
                        target_var_key="score",
                        expr_id="expr_1",
                    )
                ],
            ),
            LogicalSwitchNode(
                id="check",
                branches=[
                    Branch(
                        id="check_yes",
                        label="Yes",
                        expr_id="expr_2",
                    )
                ],
            ),
        ],
        edges=[
            EdgeRead(source="start", target="init"),
            EdgeRead(source="init", target="check"),
            EdgeRead(source="check", source_handle="check_yes", target="end"),
        ],
    )

    serialized = serialize_flow_to_code(flow)
    assert "- score: number [default: 10]" in serialized
    assert "- init [LOGICAL_ASSIGNER]" in serialized
    assert "score = expr_1" in serialized
    assert "- check [LOGICAL_SWITCH]" in serialized
    assert "branches: Yes (expr_2)" in serialized
    assert "- start -> init" in serialized
    assert "- init -> check" in serialized
    assert "- check -[Yes]-> end" in serialized


def test_serialize_flow_to_code_with_expressions() -> None:
    from app.graphs.schemas import ExpressionRecord

    flow = GraphFlowData(
        state=[DefinerVariableSchema(id="v1", key="score", type="number", default_value=10)],
        expressions={
            "expr_score": ExpressionRecord(id="expr_score", expr=LiteralExpr(value=10)),
            "expr_yes": ExpressionRecord(id="expr_yes", expr=LiteralExpr(value=True)),
        },
        nodes=[
            LogicalAssignerNode(
                id="init",
                assignments=[
                    LogicalAssignmentSchema(
                        id="a1",
                        target_var_key="score",
                        expr_id="expr_score",
                    )
                ],
            ),
            LogicalSwitchNode(
                id="check",
                branches=[
                    Branch(
                        id="check_yes",
                        label="Yes",
                        expr_id="expr_yes",
                    )
                ],
            ),
        ],
        edges=[],
    )

    serialized = serialize_flow_to_code(flow)
    assert "Expressions:" in serialized
    assert "- expr_score: 10" in serialized
    assert "- expr_yes: True" in serialized
    assert "score = expr_score" in serialized
    assert "branches: Yes (expr_yes)" in serialized


def test_sort_operations_by_dependency() -> None:
    from app.graphs.schemas import GraphOperation

    ops: list[GraphOperation] = [
        ConnectOp(op="connect", source="a", target="b"),
        UpsertLogicalSwitchOp(op="upsert_logical_switch", node_id="a", branches=[]),
        UpsertStateVarOp(op="upsert_state_var", key="x", type="number"),
    ]
    sorted_ops = sort_operations_by_dependency(ops)
    assert sorted_ops[0].op == "upsert_state_var"
    assert sorted_ops[1].op == "upsert_logical_switch"
    assert sorted_ops[2].op == "connect"


class MockToolCallFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, func_name: str, arguments: str):
        self.id = "mock_call"
        self.type = "function"
        self.function = MockToolCallFunction(func_name, arguments)


def test_translate_tool_calls_to_operations() -> None:
    import json

    tool_calls = [
        MockToolCall("upsert_state_var", json.dumps({"key": "score", "type": "number", "default_value": 0})),
        MockToolCall("connect", json.dumps({"source": "test_node", "target": "end", "case": "Yes"})),
    ]

    ops = translate_tool_calls_to_operations(tool_calls)
    assert len(ops) == 2
    assert isinstance(ops[0], UpsertStateVarOp)
    assert isinstance(ops[1], ConnectOp)
    assert ops[1].source_handle == "test_node_yes"


def test_strict_validation_forbids_extra_fields() -> None:
    import pytest
    from pydantic import ValidationError

    # Extra/invalid fields on UpsertLogicalSwitchOp should raise ValidationError
    with pytest.raises(ValidationError):
        UpsertLogicalSwitchOp(
            op="upsert_logical_switch",
            node_id="test",
            branches=[
                {"case": "Submit"}  # "case" is not a valid field — must be "label"
            ],
        )

    # Extra fields at operation root should also be forbidden
    with pytest.raises(ValidationError):
        UpsertLogicalSwitchOp(
            op="upsert_logical_switch",
            node_id="test",
            branches=[],
            some_invalid_extra_field="hello",
        )


def test_connect_op_case_resolution() -> None:
    # Verify that case field in ConnectOp gets resolved to source_handle
    op = ConnectOp(op="connect", source="switch_node", target="end", case="Submit")
    assert op.source_handle == "switch_node_submit"

    # Verify that passing case in source_handle directly (without f"{source}_") gets normalized correctly
    op2 = ConnectOp(op="connect", source="switch_node", target="end", source_handle="Submit")
    assert op2.source_handle == "switch_node_submit"
    assert op2.case == "Submit"

    # Verify DisconnectOp resolves case as well
    from app.graphs.schemas import DisconnectOp

    op_disc = DisconnectOp(op="disconnect", source="switch_node", target="end", case="Submit")
    assert op_disc.source_handle == "switch_node_submit"

    op_disc2 = DisconnectOp(op="disconnect", source="switch_node", target="end", source_handle="Submit")
    assert op_disc2.source_handle == "switch_node_submit"
    assert op_disc2.case == "Submit"
