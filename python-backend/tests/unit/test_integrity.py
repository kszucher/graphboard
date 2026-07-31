import pytest

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs import operations as graph_operations
from app.graphs.integrity import assert_flow_is_complete
from app.graphs.schemas import (
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
    LogicalAssignmentSchema,
    NodeRead,
    SlotRead,
)


@pytest.fixture
def base_flow() -> GraphFlowData:
    nodes = [
        NodeRead(id="start", node_type=NodeType.START),
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
            slots=[SlotRead(id="step_1_slot", raw_string="success", target_var_key="y")],
        ),
        NodeRead(id="end", node_type=NodeType.END),
    ]

    edges = [
        EdgeRead(source_id="start", target_id="switch_1"),
        EdgeRead(source_id="switch_1_option_a", target_id="assigner_1"),
        EdgeRead(source_id="switch_1_option_b", target_id="step_1"),
        EdgeRead(source_id="assigner_1", target_id="end"),
        EdgeRead(source_id="step_1", target_id="end"),
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
    variables = base_flow.state
    assert variables is not None
    assert variables[0].key == "z"

    # Check that target_var_key changed in LOGICAL_ASSIGNER assignments
    assignments = base_flow.nodes[2].assignments
    assert assignments is not None
    assert assignments[0].target_var_key == "z"

    # Check that expression variable changed in LOGICAL_ASSIGNER expression
    expr = assignments[0].expression
    assert isinstance(expr, dict)
    assert expr.get("left", {}).get("varKey") == "z"

    # Check that expression variable changed in SWITCH slot expression
    slot_expr = base_flow.nodes[1].slots[0].expression
    assert isinstance(slot_expr, dict)
    assert slot_expr.get("left", {}).get("varKey") == "z"


def test_assert_flow_is_complete_success(base_flow: GraphFlowData) -> None:
    # Should not raise any exception
    assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unset_expression(base_flow: GraphFlowData) -> None:
    # Set switch expression to None
    base_flow.nodes[1].slots[0].expression = None

    # We expect ValidationError
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


def test_assert_flow_is_complete_agentic_assigner(base_flow: GraphFlowData) -> None:
    # Add a valid reachable agentic assigner node
    base_flow.nodes.append(
        NodeRead(
            id="agentic_1",
            node_type=NodeType.AGENTIC_ASSIGNER,
            prompt="Generate text using {x}",
            agentic_inputs=["x"],
            agentic_outputs=["y"],
        )
    )
    # Reroute step_1 to agentic_1 instead of end, and agentic_1 to end
    base_flow.edges = [e for e in base_flow.edges if e.source_id != "step_1"]
    base_flow.edges.extend(
        [
            EdgeRead(source_id="step_1", target_id="agentic_1"),
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
