import pytest

from app.core.constants import NodeType
from app.core.exceptions import ValidationError
from app.modules.graphs.operations import (
    AgenticOutputInput,
    AssignmentInput,
    GraphUpdateInput,
    NodeUpsertInput,
    RenameInput,
    VariableUpsertInput,
    apply_graph_update,
)
from app.modules.graphs.schemas import GraphFlowData


def test_pipeline_basic() -> None:
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    # 1. Test variable declaration and logical assignment
    update = GraphUpdateInput(
        variables={
            "upsert": [
                VariableUpsertInput(key="score", type="number", default_value=0),
            ]
        },
        nodes={
            "upsert": [
                NodeUpsertInput(
                    id="init",
                    node_type=NodeType.LOGICAL_ASSIGNER,
                    assignments=[AssignmentInput(target_var_key="score", expression={"set": 0})],
                    target="check",
                )
            ]
        },
        start_target="init",
    )

    flow = apply_graph_update(flow, update)
    assert len(flow.state) == 1
    assert flow.state[0].key == "score"
    assert len(flow.nodes) == 1
    assert flow.nodes[0].id == "init"
    assert len(flow.edges) == 2  # start -> init, init -> check
    assert flow.nodes[0].assignments[0].expression == {"set": 0}

    # 2. Test strict declaration check (assigning to undeclared variable)
    invalid_update = GraphUpdateInput(
        nodes={
            "upsert": [
                NodeUpsertInput(
                    id="check",
                    node_type=NodeType.LOGICAL_ASSIGNER,
                    assignments=[AssignmentInput(target_var_key="guaranteed_win", expression={"score": {"equals": 5}})],
                )
            ]
        }
    )
    with pytest.raises(ValidationError, match="is not defined in the graph state"):
        apply_graph_update(flow, invalid_update)

    # 3. Correctly declare and assign
    valid_update = GraphUpdateInput(
        variables={
            "upsert": [
                VariableUpsertInput(key="guaranteed_win", type="boolean", default_value=False),
            ]
        },
        nodes={
            "upsert": [
                NodeUpsertInput(
                    id="check",
                    node_type=NodeType.LOGICAL_ASSIGNER,
                    assignments=[AssignmentInput(target_var_key="guaranteed_win", expression={"score": {"equals": 5}})],
                )
            ]
        },
    )
    flow = apply_graph_update(flow, valid_update)
    assert len(flow.state) == 2
    assert flow.state[1].key == "guaranteed_win"
    assert flow.nodes[1].assignments[0].expression == {"score": {"equals": 5}}

    # 4. Test delete node (which cleans edges)
    delete_update = GraphUpdateInput(nodes={"delete": ["check"]}, variables={"delete": ["guaranteed_win"]})
    flow = apply_graph_update(flow, delete_update)
    assert len(flow.nodes) == 1
    assert len(flow.state) == 1
    assert len(flow.edges) == 1  # only start -> init remaining (init -> check pruned)


def test_renames_cascading() -> None:
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    # Initialize graph
    setup = GraphUpdateInput(
        variables={
            "upsert": [
                VariableUpsertInput(key="points", type="number", default_value=0),
            ]
        },
        nodes={
            "upsert": [
                NodeUpsertInput(
                    id="score_node",
                    node_type=NodeType.LOGICAL_ASSIGNER,
                    assignments=[AssignmentInput(target_var_key="points", expression={"increment": 1})],
                    target="end",
                )
            ]
        },
        start_target="score_node",
    )
    flow = apply_graph_update(flow, setup)

    # Rename variable points -> score
    rename_var_update = GraphUpdateInput(rename_variables=[RenameInput(old_key="points", new_key="score")])
    flow = apply_graph_update(flow, rename_var_update)
    assert flow.state[0].key == "score"
    assert flow.nodes[0].assignments[0].target_var_key == "score"
    assert flow.nodes[0].assignments[0].expression == {"increment": 1}

    # Rename node score_node -> points_node
    rename_node_update = GraphUpdateInput(rename_nodes=[RenameInput(old_key="score_node", new_key="points_node")])
    flow = apply_graph_update(flow, rename_node_update)
    assert flow.nodes[0].id == "points_node"
    assert any(e.source == "start" and e.target == "points_node" for e in flow.edges)
    assert any(e.source == "points_node" and e.target == "end" for e in flow.edges)


def test_node_type_transmutation() -> None:
    """Test transmuting an existing node from AGENTIC_ASSIGNER to LOGICAL_ASSIGNER in-place."""
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    setup = GraphUpdateInput(
        variables={"upsert": [VariableUpsertInput(key="display_text", type="string", default_value="hello")]},
        nodes={
            "upsert": [
                NodeUpsertInput(
                    id="fifty_fifty",
                    node_type=NodeType.AGENTIC_ASSIGNER,
                    prompt="Eliminate options...",
                    agentic_inputs=["display_text"],
                    agentic_outputs=[AgenticOutputInput(key="display_text", type="string")],
                    target="ask_question",
                )
            ]
        },
        start_target="fifty_fifty",
    )
    flow = apply_graph_update(flow, setup)
    assert flow.nodes[0].node_type == NodeType.AGENTIC_ASSIGNER

    # Transmute to LOGICAL_ASSIGNER
    transmute_update = GraphUpdateInput(
        nodes={
            "upsert": [
                NodeUpsertInput(
                    id="fifty_fifty",
                    node_type=NodeType.LOGICAL_ASSIGNER,
                    assignments=[AssignmentInput(target_var_key="display_text", expression={"var": "display_text"})],
                    target="ask_question",
                )
            ]
        }
    )
    flow = apply_graph_update(flow, transmute_update)
    assert flow.nodes[0].node_type == NodeType.LOGICAL_ASSIGNER
    assert flow.nodes[0].assignments[0].target_var_key == "display_text"
    assert any(e.source == "start" and e.target == "fifty_fifty" for e in flow.edges)
    assert any(e.source == "fifty_fifty" and e.target == "ask_question" for e in flow.edges)
