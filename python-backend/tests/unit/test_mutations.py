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
    UpsertExpressionOp,
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
    # Creating a switch node with expressions via the store
    patch = [
        UpsertExpressionOp(
            op="upsert_expression",
            id="expr_option_a",
            expr={"type": "binary", "left": {"type": "variable", "name": "x"}, "op": "==", "right": {"type": "literal", "value": 10}},  # type: ignore[arg-type]
        ),
        UpsertExpressionOp(
            op="upsert_expression",
            id="expr_option_b",
            expr={"type": "literal", "value": True},  # type: ignore[arg-type]
        ),
        UpsertLogicalSwitchOp(
            op="upsert_logical_switch",
            node_id="switch_1",
            branches=[
                {"label": "option_a", "expr_id": "expr_option_a"},
                {"label": "option_b", "expr_id": "expr_option_b"},
            ],
        ),
    ]
    updated = mutations.apply_patch(flow, patch)
    assert len(updated.nodes) == 1
    node = updated.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.branches) == 2
    assert node.branches[0].label == "option_a"
    expr = node.branches[0].expression
    assert expr is not None
    assert expr.to_string() == "(x == 10)"


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

    # 2. Add an Assigner Node that references it (via expression store)
    flow = mutations.apply_patch(
        flow,
        [
            UpsertExpressionOp(
                op="upsert_expression",
                id="expr_concat",
                expr={"type": "binary", "left": {"type": "variable", "name": "old_key"}, "op": "+", "right": {"type": "literal", "value": " world"}},  # type: ignore[arg-type]
            ),
            UpsertLogicalAssignerOp(
                op="upsert_logical_assigner",
                node_id="assigner_1",
                assignments=[{"target_var_key": "old_key", "expr_id": "expr_concat"}],
            ),
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
    assert expr is not None
    assert expr.to_string() == "(new_key + ' world')"


def test_apply_patch_delete_var_blocked_if_referenced() -> None:
    flow = GraphFlowData(nodes=[], edges=[])

    # 1. Upsert State Variable
    flow = mutations.apply_patch(
        flow, [UpsertStateVarOp(op="upsert_state_var", key="x", type="number", default_value=10)]
    )

    # 2. Add node referencing variable (via expression store)
    flow = mutations.apply_patch(
        flow,
        [
            UpsertExpressionOp(
                op="upsert_expression",
                id="expr_x_val",
                expr={"type": "literal", "value": 15},  # type: ignore[arg-type]
            ),
            UpsertLogicalAssignerOp(
                op="upsert_logical_assigner",
                node_id="assigner_1",
                assignments=[{"target_var_key": "x", "expr_id": "expr_x_val"}],
            ),
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
            UpsertExpressionOp(
                op="upsert_expression",
                id="expr_true",
                expr={"type": "literal", "value": True},  # type: ignore[arg-type]
            ),
            UpsertLogicalSwitchOp(
                op="upsert_logical_switch",
                node_id="switch_1",
                branches=[{"label": "option_a", "expr_id": "expr_true"}],
            ),
        ],
    )
    node = flow.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.branches) == 1
    assert node.branches[0].label == "option_a"
    assert node.branches[0].expression is not None
    assert node.branches[0].expression.to_string() == "True"

    # 2. Add another branch by upserting a list containing ONLY the new branch (delta projection test)
    flow = mutations.apply_patch(
        flow,
        [
            UpsertExpressionOp(
                op="upsert_expression",
                id="expr_false",
                expr={"type": "literal", "value": False},  # type: ignore[arg-type]
            ),
            UpsertLogicalSwitchOp(
                op="upsert_logical_switch",
                node_id="switch_1",
                branches=[{"label": "option_b", "expr_id": "expr_false"}],
            ),
        ],
    )
    node = flow.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.branches) == 2
    assert node.branches[0].label == "option_a"
    assert node.branches[1].label == "option_b"
    assert node.branches[1].expression is not None
    assert node.branches[1].expression.to_string() == "False"

    # 3. Update option_a's expression with another partial upsert
    flow = mutations.apply_patch(
        flow,
        [
            UpsertExpressionOp(
                op="upsert_expression",
                id="expr_x_eq_5",
                expr={"type": "binary", "left": {"type": "variable", "name": "x"}, "op": "==", "right": {"type": "literal", "value": 5}},  # type: ignore[arg-type]
            ),
            UpsertLogicalSwitchOp(
                op="upsert_logical_switch",
                node_id="switch_1",
                branches=[{"label": "option_a", "expr_id": "expr_x_eq_5"}],
            ),
        ],
    )
    node = flow.nodes[0]
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.branches) == 2
    assert node.branches[0].label == "option_a"
    assert node.branches[0].expression is not None
    assert node.branches[0].expression.to_string() == "(x == 5)"
    assert node.branches[1].label == "option_b"


def test_apply_patch_delete_branch() -> None:
    from app.graphs.schemas import DeleteBranchOp

    flow = GraphFlowData(nodes=[], edges=[])

    # 1. Create switch node and connect its branch to a dummy target
    flow = mutations.apply_patch(
        flow,
        [
            UpsertExpressionOp(
                op="upsert_expression",
                id="expr_true",
                expr={"type": "literal", "value": True},  # type: ignore[arg-type]
            ),
            UpsertLogicalSwitchOp(
                op="upsert_logical_switch",
                node_id="switch_1",
                branches=[{"label": "option_a", "expr_id": "expr_true"}],
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
                UpsertExpressionOp(
                    op="upsert_expression",
                    id="expr_true",
                    expr={"type": "literal", "value": True},  # type: ignore[arg-type]
                ),
                UpsertLogicalSwitchOp(
                    op="upsert_logical_switch",
                    node_id="switch_1",
                    branches=[{"label": "option_a", "expr_id": "expr_true"}],
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


def test_upsert_expression_integrity_check() -> None:
    """Referencing a non-existent expr_id in an assigner op raises ValidationError."""
    flow = GraphFlowData(nodes=[], edges=[])

    with pytest.raises(ValidationError, match="does not exist in the expression store"):
        mutations.apply_patch(
            flow,
            [
                UpsertLogicalAssignerOp(
                    op="upsert_logical_assigner",
                    node_id="assigner_1",
                    assignments=[{"target_var_key": "x", "expr_id": "non_existent_expr"}],
                )
            ],
        )
