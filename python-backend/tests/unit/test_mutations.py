import pytest

from app.exceptions import ValidationError
from app.graphs import mutations
from app.graphs.nodes import (
    LogicalAssignerNode,
    LogicalSwitchNode,
    StartNode,
)
from app.graphs.schemas import (
    ConnectOp,
    DefinerVariableSchema,
    DeleteStateVarOp,
    DisconnectOp,
    GraphFlowData,
    UpsertLogicalAssignerOp,
    UpsertLogicalSwitchOp,
    UpsertStateVarOp,
)


def test_apply_patch_upsert_node_basic() -> None:
    flow = GraphFlowData(nodes=[], edges=[])
    patch = [
        UpsertLogicalSwitchOp(
            op="upsert_logical_switch",
            node_id="logical_switch_1",
            branches=[],
        ),
        UpsertLogicalAssignerOp(
            op="upsert_logical_assigner",
            node_id="logical_assigner_1",
            assignments=[],
        ),
    ]
    updated = mutations.apply_patch(flow, patch)
    assert len(updated.nodes) == 2
    assert isinstance(updated.nodes[0], LogicalSwitchNode)
    assert isinstance(updated.nodes[1], LogicalAssignerNode)


def test_apply_patch_upsert_node_switch_with_slots() -> None:
    flow = GraphFlowData(
        nodes=[],
        edges=[],
        state=[DefinerVariableSchema(id="var_x", key="x", type="number", default_value=10)],
    )
    # Creating a switch node and setup its branches and expressions
    patch = [
        UpsertLogicalSwitchOp(
            op="upsert_logical_switch",
            node_id="switch_1",
            branches=[
                {
                    "label": "option_a",
                    "expression": {
                        "type": "comparison",
                        "left": {"type": "variable", "name": "x"},
                        "op": "==",
                        "right": {"type": "literal", "value": 10},
                    },
                },
                {
                    "label": "option_b",
                    "expression": {
                        "type": "literal",
                        "value": True,
                    },
                },
            ],
        )
    ]
    updated = mutations.apply_patch(flow, patch)
    assert len(updated.nodes) == 1
    node = updated.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.branches) == 2
    assert node.branches[0].label == "option_a"
    expr = node.branches[0].expression
    assert expr == "(x == 10)"


def test_apply_patch_connect_disconnect() -> None:
    flow = GraphFlowData(nodes=[], edges=[])

    from app.graphs.nodes import EndNode

    flow.nodes.append(StartNode(id="node_a"))
    flow.nodes.append(EndNode(id="node_b"))

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
            UpsertLogicalAssignerOp(
                op="upsert_logical_assigner",
                node_id="assigner_1",
                assignments=[
                    {
                        "target_var_key": "old_key",
                        "expression": {
                            "type": "binary",
                            "left": {"type": "variable", "name": "old_key"},
                            "op": "+",
                            "right": {"type": "literal", "value": " world"},
                        },
                    }
                ],
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
            UpsertLogicalAssignerOp(
                op="upsert_logical_assigner",
                node_id="assigner_1",
                assignments=[
                    {
                        "target_var_key": "x",
                        "expression": {"type": "literal", "value": 15},
                    }
                ],
            )
        ],
    )

    # 3. Try to delete variable and expect validation error
    with pytest.raises(ValidationError) as excinfo:
        mutations.apply_patch(flow, [DeleteStateVarOp(op="delete_state_var", key="x")])
    assert "Cannot delete variable" in str(excinfo.value)


def test_apply_patch_merge_branches() -> None:
    flow = GraphFlowData(nodes=[], edges=[])

    # 1. Create a switch node with one branch
    flow = mutations.apply_patch(
        flow,
        [
            UpsertLogicalSwitchOp(
                op="upsert_logical_switch",
                node_id="switch_1",
                branches=[{"label": "option_a", "expression": {"type": "literal", "value": True}}],
            )
        ],
    )
    node = flow.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.branches) == 1
    assert node.branches[0].label == "option_a"
    assert node.branches[0].expression == "True"

    # 2. Add another branch by upserting a list containing ONLY the new branch (delta projection test)
    flow = mutations.apply_patch(
        flow,
        [
            UpsertLogicalSwitchOp(
                op="upsert_logical_switch",
                node_id="switch_1",
                branches=[{"label": "option_b", "expression": {"type": "literal", "value": False}}],
            )
        ],
    )
    node = flow.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.branches) == 2
    assert node.branches[0].label == "option_a"
    assert node.branches[1].label == "option_b"
    assert node.branches[1].expression == "False"

    # 3. Update option_a's expression with another partial upsert
    flow = mutations.apply_patch(
        flow,
        [
            UpsertLogicalSwitchOp(
                op="upsert_logical_switch",
                node_id="switch_1",
                branches=[{"label": "option_a", "expression": {
                    "type": "comparison",
                    "left": {"type": "variable", "name": "x"},
                    "op": "==",
                    "right": {"type": "literal", "value": 5},
                }}],
            )
        ],
    )
    node = flow.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.branches) == 2
    assert node.branches[0].label == "option_a"
    assert node.branches[0].expression == "(x == 5)"
    assert node.branches[1].label == "option_b"


def test_apply_patch_delete_branch() -> None:
    from app.graphs.schemas import DeleteBranchOp

    flow = GraphFlowData(nodes=[], edges=[])

    # 1. Create switch node and connect its branch to a dummy target
    flow = mutations.apply_patch(
        flow,
        [
            UpsertLogicalSwitchOp(
                op="upsert_logical_switch",
                node_id="switch_1",
                branches=[{"label": "option_a", "expression": {"type": "literal", "value": True}}],
            ),
            UpsertLogicalAssignerOp(
                op="upsert_logical_assigner",
                node_id="assigner_1",
                assignments=[],
            ),
            ConnectOp(
                op="connect",
                source="switch_1",
                target="assigner_1",
                case="option_a",
            ),
        ],
    )

    assert len(flow.edges) == 1
    assert flow.edges[0].source == "switch_1"
    assert flow.edges[0].source_handle == "switch_1_option_a"

    # 2. Delete the branch
    flow = mutations.apply_patch(
        flow,
        [
            DeleteBranchOp(
                op="delete_branch",
                node_id="switch_1",
                label="option_a",
            )
        ],
    )

    node = flow.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.branches) == 0  # Branch is gone
    assert len(flow.edges) == 0  # Connection edge was automatically removed


def test_connect_raises_validation_error_if_branch_missing() -> None:
    flow = GraphFlowData(nodes=[], edges=[])

    with pytest.raises(ValidationError) as excinfo:
        mutations.apply_patch(
            flow,
            [
                UpsertLogicalSwitchOp(
                    op="upsert_logical_switch",
                    node_id="switch_1",
                    branches=[{"label": "option_a", "expression": {"type": "literal", "value": True}}],
                ),
                UpsertLogicalAssignerOp(
                    op="upsert_logical_assigner",
                    node_id="assigner_1",
                    assignments=[],
                ),
                ConnectOp(
                    op="connect",
                    source="switch_1",
                    target="assigner_1",
                    case="missing_option",
                ),
            ],
        )
    assert "not found on node 'switch_1'" in str(excinfo.value)


