from app.copilot.tools import translate_tool_calls_to_operations
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
    UpsertLogicalAssignerOp,
    UpsertLogicalSwitchOp,
    UpsertStateVarOp,
)
from app.graphs.serializer import serialize_flow_to_code


def test_serialize_flow_to_code() -> None:
    flow = GraphFlowData(
        state=[DefinerVariableSchema(id="v1", key="score", type="number", default_value=10)],
        nodes=[
            LogicalAssignerNode(
                id="init",
                assignments=[
                    LogicalAssignmentSchema(
                        id="a1",
                        target_var_key="score",
                        expression="10",
                    )
                ],
            ),
            LogicalSwitchNode(
                id="check",
                branches=[
                    Branch(
                        id="check_yes",
                        label="Yes",
                        expression="True",
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
    assert "declare_variable(key='score', type='number', default_value=10)" in serialized
    assert "add_node(node_id='init', type='LOGICAL_ASSIGNER')" in serialized
    assert "add_variable_assignment(node_id='init', target_var_key='score', expression='10')" in serialized
    assert "add_node(node_id='check', type='LOGICAL_SWITCH')" in serialized
    assert "add_routing_branch(node_id='check', case='Yes', expression='True')" in serialized
    assert "connect_nodes(source='start', target='init')" in serialized
    assert "connect_nodes(source='init', target='check')" in serialized
    assert "connect_nodes(source='check', target='end', case='Yes')" in serialized


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
        MockToolCall("upsert_logical_assigner", json.dumps({"node_id": "test_node", "assignments": []})),
        MockToolCall("connect", json.dumps({"source": "test_node", "target": "end", "case": "Yes"})),
    ]

    ops = translate_tool_calls_to_operations(tool_calls)
    assert len(ops) == 3
    assert isinstance(ops[0], UpsertStateVarOp)
    assert isinstance(ops[1], UpsertLogicalAssignerOp)
    assert isinstance(ops[2], ConnectOp)
    assert ops[2].source_handle == "test_node_yes"


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
