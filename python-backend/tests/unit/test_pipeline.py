from app.graphs.operations.pipeline import GraphOperation, apply_patch, sort_operations_by_dependency
from app.graphs.operations.rename_ops import RenameVariableOp
from app.graphs.operations.topology_ops import ConnectNodesOp, DeleteNodeOp
from app.graphs.operations.upsert_ops import AssignmentSchema, UpsertLogicalAssignerOp
from app.graphs.schemas import GraphFlowData


def test_pipeline_basic() -> None:
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    # 1. Test operation sorting
    patch: list[GraphOperation] = [
        ConnectNodesOp(op="connect_nodes", source="init", target="check"),
        UpsertLogicalAssignerOp(
            op="upsert_logical_assigner",
            node_id="init",
            assignments=[AssignmentSchema(target_var_key="score", expression="0")],
        ),
        DeleteNodeOp(op="delete_node", node_id="old_node"),
        RenameVariableOp(op="rename_variable", old_key="points", new_key="score"),
    ]

    sorted_patch = sort_operations_by_dependency(patch)
    assert sorted_patch[0].op == "rename_variable"
    assert sorted_patch[1].op == "delete_node"
    assert sorted_patch[2].op == "upsert_logical_assigner"
    assert sorted_patch[3].op == "connect_nodes"

    # 2. Test apply_patch with implicit variable declaration & type inference
    # Initialize score = 0 (creates score as number)
    flow = apply_patch(
        flow,
        [
            UpsertLogicalAssignerOp(
                op="upsert_logical_assigner",
                node_id="init",
                assignments=[AssignmentSchema(target_var_key="score", expression="0")],
            )
        ],
    )
    assert len(flow.state) == 1
    assert flow.state[0].key == "score"
    assert flow.state[0].type == "number"

    # Set guaranteed_win = score == 5 (creates guaranteed_win as boolean, referencing score)
    flow = apply_patch(
        flow,
        [
            UpsertLogicalAssignerOp(
                op="upsert_logical_assigner",
                node_id="check",
                assignments=[AssignmentSchema(target_var_key="guaranteed_win", expression="col('score').eq(5)")],
            )
        ],
    )
    assert len(flow.state) == 2
    assert flow.state[1].key == "guaranteed_win"
    assert flow.state[1].type == "boolean"
    assert "expr_check_guaranteed_win" in flow.expressions

    # 3. Test automatic dead-variable and expression pruning
    # Deleting the check node should prune guaranteed_win and its expression because they are no longer referenced.
    flow = apply_patch(flow, [DeleteNodeOp(op="delete_node", node_id="check")])
    assert len(flow.state) == 1
    assert flow.state[0].key == "score"
    assert "expr_check_guaranteed_win" not in flow.expressions
