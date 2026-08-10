from app.constants import NodeType
from app.copilot.tools import translate_tool_call_to_operations
from app.graphs.mutations import sort_operations_by_dependency
from app.graphs.nodes import (
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    SlotRead,
)
from app.graphs.schemas import (
    ConnectOp,
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
    UpsertNodeOp,
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
                slots=[
                    SlotRead(
                        id="check_yes",
                        raw_string="Yes",
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
        UpsertNodeOp(op="upsert_node", node_id="a", node_type=NodeType.START),
        UpsertStateVarOp(op="upsert_state_var", key="x", type="number"),
    ]
    sorted_ops = sort_operations_by_dependency(ops)
    assert sorted_ops[0].op == "upsert_state_var"
    assert sorted_ops[1].op == "upsert_node"
    assert sorted_ops[2].op == "connect"


def test_translate_tool_call_to_operations() -> None:
    args = {
        "operations": [
            {"op": "upsert_state_var", "key": "score", "type": "number", "default_value": "0"},
            {"op": "upsert_node", "node_id": "test_node", "node_type": "LOGICAL_ASSIGNER"},
            {"op": "connect", "source": "test_node", "target": "end", "case": "Yes"},
        ]
    }
    ops = translate_tool_call_to_operations(args)
    assert len(ops) == 3
    assert isinstance(ops[0], UpsertStateVarOp)
    assert isinstance(ops[1], UpsertNodeOp)
    assert isinstance(ops[2], ConnectOp)
    assert ops[2].source_handle == "test_node_yes"


def test_strict_validation_forbids_extra_fields() -> None:
    import pytest
    from pydantic import ValidationError

    # Extra/invalid fields on UpsertNodeOp should raise ValidationError
    with pytest.raises(ValidationError):
        UpsertNodeOp(
            op="upsert_node",
            node_id="test",
            node_type=NodeType.AGENTIC_SWITCH,
            config={
                "agentic_input": "user_answer",
                "slots": [
                    {"case": "Submit"}  # "case" is not valid, must be "raw_string"
                ],
            },
        )

    # Extra fields at operation root should also be forbidden
    with pytest.raises(ValidationError):
        UpsertNodeOp(
            op="upsert_node", node_id="test", node_type=NodeType.START, config={}, some_invalid_extra_field="hello"
        )


def test_connect_op_case_resolution() -> None:
    # Verify that case field in ConnectOp gets resolved to source_handle
    op = ConnectOp(op="connect", source="switch_node", target="end", case="Submit")
    assert op.source_handle == "switch_node_submit"

    # Verify DisconnectOp resolves case as well
    from app.graphs.schemas import DisconnectOp

    op_disc = DisconnectOp(op="disconnect", source="switch_node", target="end", case="Submit")
    assert op_disc.source_handle == "switch_node_submit"
