import pytest

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs import operations as graph_operations
from app.graphs.schemas import (
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
    LogicalAssignmentSchema,
    NodeRead,
    SlotRead,
)
from app.graphs.validation import assert_flow_is_complete


@pytest.fixture
def base_flow() -> GraphFlowData:
    nodes = [
        NodeRead(id="start", node_type=NodeType.START),
        NodeRead(
            id="definer",
            node_type=NodeType.DEFINER,
            variables=[
                DefinerVariableSchema(id="var_x", key="x", type="number", default_value=0),
                DefinerVariableSchema(id="var_y", key="y", type="boolean", default_value=False),
            ],
        ),
        NodeRead(
            id="switch_1",
            node_type=NodeType.SWITCH,
            slots=[
                SlotRead(
                    id="switch_1_option_a",
                    raw_string="option_a",
                    expression={
                        "kind": "binaryOp",
                        "op": "==",
                        "left": {"kind": "stateRef", "varKey": "x"},
                        "right": {"kind": "literal", "value": 10},
                    },
                ),
                SlotRead(
                    id="switch_1_option_b",
                    raw_string="option_b",
                    expression={"kind": "literal", "value": True},
                ),
            ],
        ),
        NodeRead(
            id="assigner_1",
            node_type=NodeType.LOGICAL_ASSIGNER,
            assignments=[
                LogicalAssignmentSchema(
                    id="asgn_x",
                    target_var_key="x",
                    value_type="number",
                    expression={
                        "kind": "binaryOp",
                        "op": "+",
                        "left": {"kind": "stateRef", "varKey": "x"},
                        "right": {"kind": "literal", "value": 1},
                    },
                )
            ],
        ),
        NodeRead(
            id="step_1",
            node_type=NodeType.STEP,
            slots=[
                SlotRead(id="step_1_slot", raw_string="success", target_var_key="y")
            ]
        ),
        NodeRead(id="end", node_type=NodeType.END),
    ]

    edges = [
        EdgeRead(source_id="start", target_id="definer"),
        EdgeRead(source_id="definer", target_id="switch_1"),
        EdgeRead(source_id="switch_1_option_a", target_id="assigner_1"),
        EdgeRead(source_id="switch_1_option_b", target_id="step_1"),
        EdgeRead(source_id="assigner_1", target_id="end"),
        EdgeRead(source_id="step_1", target_id="end"),
    ]

    return GraphFlowData(nodes=nodes, edges=edges)


def test_validation_variable_existence_on_assignment_creation(base_flow: GraphFlowData) -> None:
    # 1. Invalid target variable key
    with pytest.raises(ValidationError, match="not defined in state schema"):
        graph_operations.create_logical_assignment(
            flow_data=base_flow,
            node_id="assigner_1",
            target_var_key="non_existent",
            value_type="number",
            value=10,
        )

    # 2. Invalid stateRef variable key in expression
    with pytest.raises(ValidationError, match="expression references undefined variables"):
        graph_operations.create_logical_assignment(
            flow_data=base_flow,
            node_id="assigner_1",
            target_var_key="x",
            expression={
                "kind": "stateRef",
                "varKey": "non_existent",
            },
        )


def test_validation_variable_existence_on_switch_expression_update(base_flow: GraphFlowData) -> None:
    # Invalid stateRef variable key in switch expression update
    with pytest.raises(ValidationError, match="references undefined variables"):
        graph_operations.update_switch_expression(
            flow_data=base_flow,
            slot_id="switch_1_option_a",
            expression={
                "kind": "binaryOp",
                "op": ">",
                "left": {"kind": "stateRef", "varKey": "z"},
                "right": {"kind": "literal", "value": 5},
            },
        )


def test_blocked_variable_delete_when_referenced(base_flow: GraphFlowData) -> None:
    # 1. Variable 'x' is referenced in assigner_1 (target and expression) and switch_1 (expression)
    with pytest.raises(ValidationError, match="referenced"):
        graph_operations.delete_definer_variable(base_flow, "var_x")

    # 2. Variable 'y' is referenced in step_1 slots
    with pytest.raises(ValidationError, match="referenced"):
        graph_operations.delete_definer_variable(base_flow, "var_y")


def test_cascading_rename(base_flow: GraphFlowData) -> None:
    # Rename 'x' to 'z'
    graph_operations.update_definer_variable(base_flow, "var_x", {"key": "z"})

    # Check that variables changed
    assert base_flow.nodes[1].variables[0].key == "z"

    # Check that target_var_key changed in LOGICAL_ASSIGNER assignments
    assert base_flow.nodes[3].assignments[0].target_var_key == "z"

    # Check that expression variable changed in LOGICAL_ASSIGNER expression
    assert base_flow.nodes[3].assignments[0].expression["left"]["varKey"] == "z"

    # Check that expression variable changed in SWITCH slot expression
    assert base_flow.nodes[2].slots[0].expression["left"]["varKey"] == "z"


def test_assert_flow_is_complete_success(base_flow: GraphFlowData) -> None:
    # Should not raise any exception
    assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unset_expression(base_flow: GraphFlowData) -> None:
    # Set switch expression to None
    base_flow.nodes[2].slots[0].expression = None

    with pytest.raises(ValidationError, match="unset condition"):
        assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unconnected_slot(base_flow: GraphFlowData) -> None:
    # Remove edge connected to switch_1_option_a
    base_flow.edges = [e for e in base_flow.edges if e.source_id != "switch_1_option_a"]

    with pytest.raises(ValidationError, match="not connected to any target node"):
        assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unreachable_node(base_flow: GraphFlowData) -> None:
    # Add an unconnected step node
    base_flow.nodes.append(NodeRead(id="unconnected_step", node_type=NodeType.STEP))

    with pytest.raises(ValidationError, match="unreachable from the START node"):
        assert_flow_is_complete(base_flow)
