import pytest

from app.exceptions import ValidationError
from app.graphs.integrity import assert_flow_is_complete
from app.graphs.schemas import (
    AgenticAssignerNode,
    DefinerVariableSchema,
    EdgeRead,
    EndNode,
    GraphFlowData,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    NodeRead,
    SlotRead,
    StartNode,
)


@pytest.fixture
def base_flow() -> GraphFlowData:
    nodes: list[NodeRead] = [
        StartNode(id="start"),
        LogicalSwitchNode(
            id="switch_1",
            slots=[
                SlotRead(
                    id="switch_1_option_a",
                    raw_string="option_a",
                    expression="x == 10",
                ),
                SlotRead(
                    id="switch_1_option_b",
                    raw_string="option_b",
                    expression="True",
                ),
            ],
        ),
        LogicalAssignerNode(
            id="assigner_1",
            assignments=[
                LogicalAssignmentSchema(
                    id="asgn_x",
                    target_var_key="x",
                    expression="x + 1",
                )
            ],
        ),
        LogicalAssignerNode(
            id="assigner_2",
            assignments=[
                LogicalAssignmentSchema(
                    id="asgn_y",
                    target_var_key="y",
                    expression="True",
                )
            ],
        ),
        EndNode(id="end"),
    ]

    edges = [
        EdgeRead(source="start", target="switch_1"),
        EdgeRead(source="switch_1", source_handle="switch_1_option_a", target="assigner_1"),
        EdgeRead(source="switch_1", source_handle="switch_1_option_b", target="assigner_2"),
        EdgeRead(source="assigner_1", target="end"),
        EdgeRead(source="assigner_2", target="end"),
    ]

    state = [
        DefinerVariableSchema(id="var_x", key="x", type="number", default_value=0),
        DefinerVariableSchema(id="var_y", key="y", type="boolean", default_value=False),
    ]

    return GraphFlowData(nodes=nodes, edges=edges, state=state)


def test_assert_flow_is_complete_success(base_flow: GraphFlowData) -> None:
    assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unset_expression(base_flow: GraphFlowData) -> None:
    switch_1 = next(n for n in base_flow.nodes if n.id == "switch_1")
    assert isinstance(switch_1, LogicalSwitchNode)
    switch_1.slots[1].expression = None

    with pytest.raises(ValidationError, match="unset condition"):
        assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unconnected_slot(base_flow: GraphFlowData) -> None:
    base_flow.edges = [
        e for e in base_flow.edges if not (e.source == "switch_1" and e.source_handle == "switch_1_option_a")
    ]

    with pytest.raises(ValidationError, match="not connected to any target node"):
        assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_unreachable_node(base_flow: GraphFlowData) -> None:
    base_flow.nodes.append(LogicalAssignerNode(id="unconnected_assigner"))

    with pytest.raises(ValidationError, match="unreachable from the START node"):
        assert_flow_is_complete(base_flow)


def test_assert_flow_is_complete_agentic_assigner(base_flow: GraphFlowData) -> None:
    base_flow.nodes.append(
        AgenticAssignerNode(
            id="agentic_1",
            prompt="Generate text using {x}",
            agentic_inputs=["x"],
            agentic_outputs=["y"],
        )
    )
    base_flow.edges = [e for e in base_flow.edges if e.source != "assigner_2"]
    base_flow.edges.extend(
        [
            EdgeRead(source="assigner_2", target="agentic_1"),
            EdgeRead(source="agentic_1", target="end"),
        ]
    )

    assert_flow_is_complete(base_flow)

    agentic_node = next(n for n in base_flow.nodes if n.id == "agentic_1")
    assert isinstance(agentic_node, AgenticAssignerNode)
    original_prompt = agentic_node.prompt
    agentic_node.prompt = ""
    with pytest.raises(ValidationError, match="has an empty prompt"):
        assert_flow_is_complete(base_flow)
    agentic_node.prompt = original_prompt

    original_outputs = agentic_node.agentic_outputs
    agentic_node.agentic_outputs = []
    with pytest.raises(ValidationError, match="must have at least one output variable"):
        assert_flow_is_complete(base_flow)
    agentic_node.agentic_outputs = original_outputs

    original_inputs = agentic_node.agentic_inputs
    agentic_node.agentic_inputs = ["non_existent"]
    with pytest.raises(ValidationError, match="Invalid input reference"):
        assert_flow_is_complete(base_flow)
    agentic_node.agentic_inputs = original_inputs

    agentic_node.agentic_outputs = ["non_existent"]
    with pytest.raises(ValidationError, match="Invalid output target"):
        assert_flow_is_complete(base_flow)
