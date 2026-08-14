from pydantic import ValidationError

from app.graphs.nodes import (
    Branch,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
)
from app.graphs.operations import sort_operations_by_dependency
from app.graphs.operations.pipeline import GraphOperation
from app.graphs.operations.rename_ops import RenameVariableOp
from app.graphs.operations.topology_ops import ConnectNodesOp, connect_nodes
from app.graphs.operations.upsert_ops import UpsertLogicalSwitchOp
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
            "expr_1": ExpressionRecord(id="expr_1", expr="10"),
            "expr_2": ExpressionRecord(id="expr_2", expr="True"),
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
            EdgeRead(source="init", target="check"),
            EdgeRead(source="check", source_handle="check_yes", target="end"),
        ],
    )

    serialized = serialize_flow_to_code(flow)
    assert "score: int = 10" in serialized
    assert "init: LOGICAL_ASSIGNER(score=10) -> check" in serialized
    assert "check: LOGICAL_SWITCH(Yes=True -> end)" in serialized


def test_sort_operations_by_dependency() -> None:
    ops: list[GraphOperation] = [
        ConnectNodesOp(op="connect_nodes", source="a", target="b"),
        UpsertLogicalSwitchOp(op="upsert_logical_switch", node_id="a"),
        RenameVariableOp(op="rename_variable", old_key="x", new_key="y"),
    ]
    sorted_ops = sort_operations_by_dependency(ops)
    assert sorted_ops[0].op == "rename_variable"
    assert sorted_ops[1].op == "upsert_logical_switch"
    assert sorted_ops[2].op == "connect_nodes"


def test_strict_validation_forbids_extra_fields() -> None:
    # Extra/invalid fields on ConnectNodesOp should raise ValidationError
    try:
        ConnectNodesOp(
            op="connect_nodes",
            source="a",
            target="b",
            invalid_extra_field="hello",
        )
        raise AssertionError("Should have raised ValidationError")
    except ValidationError:
        pass


def test_connect_nodes_case_resolution() -> None:
    # Verify that case label in connect_nodes gets resolved to source_handle in flow_data.edges
    flow = GraphFlowData(
        nodes=[
            LogicalSwitchNode(id="switch_node", branches=[Branch(id="switch_node_submit", label="Submit")]),
            LogicalAssignerNode(id="end"),
        ],
        edges=[],
    )

    op = ConnectNodesOp(op="connect_nodes", source="switch_node", target="end", source_handle="Submit")
    flow = connect_nodes(flow, op)

    assert len(flow.edges) == 1
    assert flow.edges[0].source_handle == "switch_node_submit"
