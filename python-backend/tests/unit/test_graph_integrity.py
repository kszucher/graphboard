from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.modules.graphs.engine.compiler import DirectLangGraphCompiler
from app.modules.graphs.operations.integrity import assert_flow_is_complete, is_type_compatible
from app.modules.graphs.schemas import (
    Branch,
    DefinerVariableSchema,
    EdgeRead,
    EndNode,
    GraphFlowData,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    StartNode,
)


@pytest.fixture
def valid_flow() -> GraphFlowData:
    return GraphFlowData(
        nodes=[
            StartNode(id="start"),
            LogicalAssignerNode(
                id="assigner_1",
                assignments=[
                    LogicalAssignmentSchema(
                        id="asgn_1",
                        target_var_key="score",
                        expression={"increment": 1},
                    )
                ],
            ),
            EndNode(id="end"),
        ],
        edges=[
            EdgeRead(source="start", target="assigner_1"),
            EdgeRead(source="assigner_1", target="end"),
        ],
        state=[
            DefinerVariableSchema(id="v_score", key="score", type="number", default_value=0),
        ],
    )


def test_valid_flow_passes_integrity(valid_flow: GraphFlowData) -> None:
    assert_flow_is_complete(valid_flow)
    compiler = DirectLangGraphCompiler(valid_flow)
    code = compiler.compile()
    assert "workflow.add_edge('assigner_1', END)" in code


def test_dangling_edge_target_rejected(valid_flow: GraphFlowData) -> None:
    # Retarget assigner_1 to a non-existent node (e.g. check_milestone)
    valid_flow.edges = [
        EdgeRead(source="start", target="assigner_1"),
        EdgeRead(source="assigner_1", target="check_milestone"),
    ]

    with pytest.raises(ValidationError, match="Edge target 'check_milestone' does not exist"):
        assert_flow_is_complete(valid_flow)

    with pytest.raises(ValidationError, match="target node 'check_milestone' does not exist"):
        DirectLangGraphCompiler(valid_flow).compile()


def test_dangling_edge_source_rejected(valid_flow: GraphFlowData) -> None:
    valid_flow.edges.append(EdgeRead(source="phantom_node", target="end"))

    with pytest.raises(ValidationError, match="Edge source 'phantom_node' does not exist"):
        assert_flow_is_complete(valid_flow)


def test_orphan_variable_rejected(valid_flow: GraphFlowData) -> None:
    # Add a variable that no node reads or writes
    valid_flow.state.append(
        DefinerVariableSchema(id="v_unused", key="unused_flag", type="boolean", default_value=False)
    )

    with pytest.raises(
        ValidationError, match="State variable\\(s\\) unused_flag are defined in state but never referenced"
    ):
        assert_flow_is_complete(valid_flow)


def test_incompatible_default_value_rejected(valid_flow: GraphFlowData) -> None:
    # Number variable with string default value
    valid_flow.state[0].default_value = "invalid_number_string"

    with pytest.raises(ValidationError, match="incompatible default value"):
        assert_flow_is_complete(valid_flow)


def test_duplicate_variable_keys_rejected(valid_flow: GraphFlowData) -> None:
    valid_flow.state.append(DefinerVariableSchema(id="v_score_dup", key="score", type="number", default_value=0))

    with pytest.raises(ValidationError, match="Duplicate state variable keys"):
        assert_flow_is_complete(valid_flow)


def test_duplicate_node_ids_rejected(valid_flow: GraphFlowData) -> None:
    valid_flow.nodes.append(
        LogicalAssignerNode(
            id="assigner_1",
            assignments=[LogicalAssignmentSchema(id="a_dup", target_var_key="score", expression=10)],
        )
    )

    with pytest.raises(ValidationError, match="Duplicate node IDs"):
        assert_flow_is_complete(valid_flow)


def test_linear_node_multiple_outgoing_edges_rejected(valid_flow: GraphFlowData) -> None:
    valid_flow.edges.append(EdgeRead(source="assigner_1", target="end"))

    with pytest.raises(ValidationError, match="must have exactly 1 outgoing target, found 2"):
        assert_flow_is_complete(valid_flow)


def test_switch_unrouted_branch_rejected() -> None:
    flow = GraphFlowData(
        nodes=[
            StartNode(id="start"),
            LogicalSwitchNode(
                id="switch_1",
                branches=[
                    Branch(id="switch_1_opt_a", label="opt_a", expression={"score": {"gt": 10}}),
                    Branch(id="switch_1_opt_b", label="opt_b", expression=None),
                ],
            ),
            EndNode(id="end"),
        ],
        edges=[
            EdgeRead(source="start", target="switch_1"),
            EdgeRead(source="switch_1", source_handle="switch_1_opt_a", target="end"),
            # opt_b missing edge
        ],
        state=[
            DefinerVariableSchema(id="v_score", key="score", type="number", default_value=0),
        ],
    )

    with pytest.raises(ValidationError, match="not connected to any target node"):
        assert_flow_is_complete(flow)


def test_type_compatibility_checker() -> None:
    assert is_type_compatible("number", 42)
    assert is_type_compatible("number", 3.14)
    assert not is_type_compatible("number", "42")
    assert not is_type_compatible("number", True)

    assert is_type_compatible("string", "hello")
    assert not is_type_compatible("string", 123)

    assert is_type_compatible("boolean", True)
    assert not is_type_compatible("boolean", 1)

    assert is_type_compatible("array", [1, 2, 3])
    assert not is_type_compatible("array", {"a": 1})

    assert is_type_compatible("object", {"key": "value"})
    assert not is_type_compatible("object", [1, 2, 3])
