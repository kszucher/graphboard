import json

import pytest
from pydantic import ValidationError

from app.copilot.tools import translate_tool_calls_to_operations
from app.graphs.expressions.schemas import LiteralExpr
from app.graphs.nodes import (
    Branch,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
)
from app.graphs.operations import sort_operations_by_dependency
from app.graphs.operations.pipeline import GraphOperation
from app.graphs.operations.state_ops import DeclareVariableOp
from app.graphs.operations.topology_ops import ConnectOp, CreateNodeOp
from app.graphs.schemas import (
    DefinerVariableSchema,
    EdgeRead,
    ExpressionRecord,
    GraphFlowData,
)
from app.graphs.serializer import serialize_flow_to_code


def test_serialize_flow_to_code() -> None:
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
    assert "- score: number = 10" in serialized
    assert "init [LOGICAL_ASSIGNER] assignments={score=expr_1}" in serialized
    assert "check [LOGICAL_SWITCH] branches=[Yes(expr_2)]" in serialized


def test_sort_operations_by_dependency() -> None:
    ops: list[GraphOperation] = [
        ConnectOp(op="connect", source="a", target="b"),
        CreateNodeOp(op="create_node", node_id="a", node_type="LOGICAL_SWITCH"),
        DeclareVariableOp(op="declare_variable", key="x", type="number"),
    ]
    sorted_ops = sort_operations_by_dependency(ops)
    assert sorted_ops[0].op == "declare_variable"
    assert sorted_ops[1].op == "create_node"
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
    tool_calls = [
        MockToolCall("declare_variable", json.dumps({"key": "score", "type": "number", "default_value": 0})),
        MockToolCall("connect", json.dumps({"source": "test_node", "target": "end", "case": "Yes"})),
    ]

    ops = translate_tool_calls_to_operations(tool_calls)
    assert len(ops) == 2
    assert isinstance(ops[0], DeclareVariableOp)
    assert ops[0].key == "score"

    assert isinstance(ops[1], ConnectOp)
    assert ops[1].source_handle == "test_node_yes"


def test_strict_validation_forbids_extra_fields() -> None:
    # Extra/invalid fields on CreateNodeOp should raise ValidationError
    with pytest.raises(ValidationError):
        CreateNodeOp(
            op="create_node",
            node_id="test",
            node_type="LOGICAL_SWITCH",
            invalid_extra_field="hello",
        )


def test_connect_op_case_resolution() -> None:
    # Verify that case field in ConnectOp gets resolved to source_handle
    op = ConnectOp(op="connect", source="switch_node", target="end", case="Submit")
    assert op.source_handle == "switch_node_submit"

    op2 = ConnectOp(op="connect", source="switch_node", target="end", source_handle="Submit")
    assert op2.source_handle == "switch_node_submit"
    assert op2.case == "Submit"
