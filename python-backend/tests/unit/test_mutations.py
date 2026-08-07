import pytest

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs import mutations
from app.graphs.schemas import (
    ConnectOp,
    DefinerVariableSchema,
    DeleteStateVarOp,
    DisconnectOp,
    GraphFlowData,
    LogicalAssignerNode,
    LogicalSwitchNode,
    StartNode,
    UpsertNodeOp,
    UpsertStateVarOp,
)


def test_apply_patch_upsert_node_basic() -> None:
    flow = GraphFlowData(nodes=[], edges=[])
    patch = [
        UpsertNodeOp(op="upsert_node", node_id="start_1", node_type=NodeType.START),
        UpsertNodeOp(
            op="upsert_node",
            node_id="logical_assigner_1",
            node_type=NodeType.LOGICAL_ASSIGNER,
            config={},
        ),
    ]
    updated = mutations.apply_patch(flow, patch)
    assert len(updated.nodes) == 2
    assert isinstance(updated.nodes[0], StartNode)
    assert isinstance(updated.nodes[1], LogicalAssignerNode)


def test_apply_patch_upsert_node_switch_with_slots() -> None:
    flow = GraphFlowData(
        nodes=[],
        edges=[],
        state=[DefinerVariableSchema(id="var_x", key="x", type="number", default_value=10)],
    )
    # Creating a switch node and immediately setting up its slots and expressions
    patch = [
        UpsertNodeOp(
            op="upsert_node",
            node_id="switch_1",
            node_type=NodeType.LOGICAL_SWITCH,
            config={
                "slots": [
                    {
                        "raw_string": "option_a",
                        "expression": "x == 10",
                    },
                    {
                        "raw_string": "option_b",
                        "expression": "True",
                    },
                ]
            },
        )
    ]
    updated = mutations.apply_patch(flow, patch)
    assert len(updated.nodes) == 1
    node = updated.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.slots) == 2
    assert node.slots[0].raw_string == "option_a"
    expr = node.slots[0].expression
    assert expr == "x == 10"


def test_apply_patch_connect_disconnect() -> None:
    flow = GraphFlowData(nodes=[], edges=[])
    patch_nodes = [
        UpsertNodeOp(op="upsert_node", node_id="node_a", node_type=NodeType.START),
        UpsertNodeOp(op="upsert_node", node_id="node_b", node_type=NodeType.END),
    ]
    flow = mutations.apply_patch(flow, patch_nodes)

    patch_connect = [ConnectOp(op="connect", source="node_a", target="node_b", source_handle=None, target_handle=None)]
    flow = mutations.apply_patch(flow, patch_connect)
    assert len(flow.edges) == 1
    assert flow.edges[0].source == "node_a"
    assert flow.edges[0].target == "node_b"

    patch_disconnect = [
        DisconnectOp(op="disconnect", source="node_a", target="node_b", source_handle=None, target_handle=None)
    ]
    flow = mutations.apply_patch(flow, patch_disconnect)
    assert len(flow.edges) == 0


def test_apply_patch_state_var_cascade() -> None:
    flow = GraphFlowData(nodes=[], edges=[])

    # 1. Upsert State Variable "old_key"
    flow = mutations.apply_patch(
        flow, [UpsertStateVarOp(op="upsert_state_var", id="var_x", key="old_key", type="string", default_value="hello")]
    )
    assert len(flow.state) == 1
    assert flow.state[0].key == "old_key"

    # 2. Add an Assigner Node that references it
    flow = mutations.apply_patch(
        flow,
        [
            UpsertNodeOp(
                op="upsert_node",
                node_id="assigner_1",
                node_type=NodeType.LOGICAL_ASSIGNER,
                config={
                    "assignments": [
                        {
                            "target_var_key": "old_key",
                            "expression": "old_key + ' world'",
                        }
                    ]
                },
            )
        ],
    )
    node = flow.nodes[0]
    assert isinstance(node, LogicalAssignerNode)
    assert len(node.assignments) == 1
    assert node.assignments[0].target_var_key == "old_key"

    # 3. Rename the Variable to "new_key" by providing same ID but different key
    flow = mutations.apply_patch(
        flow, [UpsertStateVarOp(op="upsert_state_var", id="var_x", key="new_key", type="string", default_value="hello")]
    )

    # Check cascading updates
    assigner = flow.nodes[0]
    assert isinstance(assigner, LogicalAssignerNode)
    assert assigner.assignments[0].target_var_key == "new_key"
    expr = assigner.assignments[0].expression
    assert expr == "new_key + ' world'"


def test_apply_patch_delete_var_blocked_if_referenced() -> None:
    flow = GraphFlowData(nodes=[], edges=[])

    # 1. Upsert State Variable
    flow = mutations.apply_patch(
        flow, [UpsertStateVarOp(op="upsert_state_var", key="x", type="number", default_value=10)]
    )

    # 2. Add node referencing variable
    flow = mutations.apply_patch(
        flow,
        [
            UpsertNodeOp(
                op="upsert_node",
                node_id="assigner_1",
                node_type=NodeType.LOGICAL_ASSIGNER,
                config={
                    "assignments": [
                        {
                            "target_var_key": "x",
                            "expression": "15",
                        }
                    ]
                },
            )
        ],
    )

    # 3. Try to delete variable and expect validation error
    with pytest.raises(ValidationError) as excinfo:
        mutations.apply_patch(flow, [DeleteStateVarOp(op="delete_state_var", key="x")])
    assert "Cannot delete variable" in str(excinfo.value)
