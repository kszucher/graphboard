import pytest

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs import operations as graph_operations
from app.graphs.integrity import assert_flow_is_complete
from app.graphs.schemas import (
    AgenticAssignerNode,
    DefinerVariableSchema,
    EdgeRead,
    EndNode,
    GraphFlowData,
    LogicalAssignmentSchema,
    LogicalAssignerNode,
    SlotRead,
    StartNode,
    SwitchNode,
)


@pytest.fixture
def base_flow() -> GraphFlowData:
    nodes = [
        StartNode(id="start"),
        SwitchNode(
            id="switch_1",
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
        LogicalAssignerNode(
            id="assigner_1",
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
        LogicalAssignerNode(
            id="assigner_2",
            assignments=[
                LogicalAssignmentSchema(
                    id="asgn_y",
                    target_var_key="y",
                    value_type="boolean",
                    value=True,
                )
            ],
        ),
        EndNode(id="end"),
    ]

    edges = [
        EdgeRead(source_id="start", target_id="switch_1"),
        EdgeRead(source_id="switch_1_option_a", target_id="assigner_1"),
        EdgeRead(source_id="switch_1_option_b", target_id="assigner_2"),
        EdgeRead(source_id="assigner_1", target_id="end"),
        EdgeRead(source_id="assigner_2", target_id="end"),
    ]

    state = [
        DefinerVariableSchema(id="var_x", key="x", type="number", default_value=0),
        DefinerVariableSchema(id="var_y", key="y", type="boolean", default_value=False),
    ]

    return GraphFlowData(nodes=nodes, edges=edges, state=state)


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


def test_validation_variable_existence_on_switch_expression_update(base_flow: GraphFlowData) -> None:
    # Invalid stateRef variable key in expression
    with pytest.raises(ValidationError, match="references undefined variables"):
        graph_operations.update_switch_expression(
            flow_data=base_flow,
            slot_id="switch_1_option_a",
            expression={"kind": "stateRef", "varKey": "missing_var"},
        )


def test_blocked_variable_delete_when_referenced(base_flow: GraphFlowData) -> None:
    # 1. Blocked because 'x' is referenced in assigner_1 expression and switch_1 expression
    with pytest.raises(ValidationError, match="Cannot delete variable 'x'"):
        graph_operations.delete_definer_variable(base_flow, var_id="var_x")

    # 2. Blocked because 'y' is target in assigner_2
    with pytest.raises(ValidationError, match="Cannot delete variable 'y'"):
        graph_operations.delete_definer_variable(base_flow, var_id="var_y")


def test_cascading_rename(base_flow: GraphFlowData) -> None:
    # Rename 'x' to 'x_new'
    graph_operations.update_definer_variable(base_flow, var_id="var_x", updates={"key": "x_new"})

    # Verify assignment target updated
    assigner_1 = next(n for n in base_flow.nodes if n.id == "assigner_1")
    assert isinstance(assigner_1, LogicalAssignerNode)
    assert assigner_1.assignments[0].target_var_key == "x_new"

    # Verify expression in switch_1 updated
    switch_1 = next(n for n in base_flow.nodes if n.id == "switch_1")
    assert isinstance(switch_1, SwitchNode)
    expr = switch_1.slots[0].expression
    assert expr is not None
    assert expr["left"]["varKey"] == "x_new"


def test_assert_flow_is_complete_success(base_flow: GraphFlowData) -> None:
    # Standard complete flow should pass without error
    assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unset_expression(base_flow: GraphFlowData) -> None:
    # Set expression on slot to None
    switch_1 = next(n for n in base_flow.nodes if n.id == "switch_1")
    assert isinstance(switch_1, SwitchNode)
    switch_1.slots[1].expression = None

    with pytest.raises(ValidationError, match="unset condition"):
        assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unconnected_slot(base_flow: GraphFlowData) -> None:
    # Remove outgoing edge from switch_1_option_a
    base_flow.edges = [e for e in base_flow.edges if e.source_id != "switch_1_option_a"]

    with pytest.raises(ValidationError, match="not connected to any target node"):
        assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unreachable_node(base_flow: GraphFlowData) -> None:
    # Add an unconnected assigner node
    base_flow.nodes.append(LogicalAssignerNode(id="unconnected_assigner"))

    with pytest.raises(ValidationError, match="unreachable from the START node"):
        assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_agentic_assigner(base_flow: GraphFlowData) -> None:
    # Add a valid reachable agentic assigner node
    base_flow.nodes.append(
        AgenticAssignerNode(
            id="agentic_1",
            prompt="Generate text using {x}",
            agentic_inputs=["x"],
            agentic_outputs=["y"],
        )
    )
    # Reroute assigner_2 to agentic_1 instead of end, and agentic_1 to end
    base_flow.edges = [e for e in base_flow.edges if e.source_id != "assigner_2"]
    base_flow.edges.extend(
        [
            EdgeRead(source_id="assigner_2", target_id="agentic_1"),
            EdgeRead(source_id="agentic_1", target_id="end"),
        ]
    )

    # Should pass completeness check
    assert_flow_is_complete(base_flow)

    # 1. Test missing prompt
    agentic_node = next(n for n in base_flow.nodes if n.id == "agentic_1")
    original_prompt = agentic_node.prompt
    agentic_node.prompt = ""
    with pytest.raises(ValidationError, match="has an empty prompt"):
        assert_flow_is_complete(base_flow)
    agentic_node.prompt = original_prompt

    # 2. Test missing output variables
    original_outputs = agentic_node.agentic_outputs
    agentic_node.agentic_outputs = []
    with pytest.raises(ValidationError, match="must have at least one output variable"):
        assert_flow_is_complete(base_flow)
    agentic_node.agentic_outputs = original_outputs

    # 3. Test invalid input variable reference
    original_inputs = agentic_node.agentic_inputs
    agentic_node.agentic_inputs = ["non_existent"]
    with pytest.raises(ValidationError, match="Invalid input reference"):
        assert_flow_is_complete(base_flow)
    agentic_node.agentic_inputs = original_inputs

    # 4. Test invalid output variable reference
    agentic_node.agentic_outputs = ["non_existent"]
    with pytest.raises(ValidationError, match="Invalid output target"):
        assert_flow_is_complete(base_flow)
