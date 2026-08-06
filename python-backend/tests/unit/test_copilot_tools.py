from app.constants import NodeType
from app.graphs.schemas import (
    GraphFlowData,
    DefinerVariableSchema,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    SlotRead,
    EdgeRead,
)
from app.graphs.expressions import LiteralExpression
from app.copilot.tools import (
    serialize_graph_to_tool_calls,
    sort_operations_by_dependency,
    translate_tool_call_to_operations,
)
from app.graphs.schemas import UpsertStateVarOp, UpsertNodeOp, ConnectOp


def test_serialize_graph_to_tool_calls() -> None:
    flow = GraphFlowData(
        state=[DefinerVariableSchema(id="v1", key="score", type="number", default_value=10)],
        nodes=[
            LogicalAssignerNode(
                id="init",
                assignments=[
                    LogicalAssignmentSchema(
                        id="a1",
                        target_var_key="score",
                        expression=LiteralExpression(kind="literal", value=10),
                    )
                ],
            ),
            LogicalSwitchNode(
                id="check",
                slots=[
                    SlotRead(
                        id="check_yes",
                        raw_string="Yes",
                        expression=LiteralExpression(kind="literal", value=True),
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

    serialized = serialize_graph_to_tool_calls(flow)
    assert "declare_state(key='score', type='number', default_value=10)" in serialized
    assert "add_assigner(node_id='init'" in serialized
    assert "add_switch(node_id='check'" in serialized
    assert "connect(source='start', target='init')" in serialized
    assert "connect(source='init', target='check')" in serialized
    assert "connect(source='check', target='end', case='Yes')" in serialized


def test_sort_operations_by_dependency() -> None:
    ops = [
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
