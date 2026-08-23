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


def test_pipeline_switch_nodes() -> None:
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    # 1. Setup state variables
    setup = GraphUpdateInput(
        variables={
            "upsert": [
                VariableUpsertInput(key="score", type="number", default_value=0),
                VariableUpsertInput(key="user_choice", type="string", default_value=""),
            ]
        },
        nodes={
            "upsert": [
                NodeUpsertInput(
                    id="logic_switch",
                    node_type=NodeType.LOGICAL_SWITCH,
                    branches={
                        "High": {"expression": {"score": {"gte": 100}}, "target": "end"},
                        "Low": {"expression": None, "target": "end"},
                    },
                ),
                NodeUpsertInput(
                    id="agent_switch",
                    node_type=NodeType.AGENTIC_SWITCH,
                    agentic_input="user_choice",
                    branches={
                        "A": {"target": "end"},
                        "B": {"target": "end"},
                    },
                ),
            ]
        },
        start_target="logic_switch",
    )
    flow = apply_graph_update(flow, setup)

    assert len(flow.nodes) == 2
    logic_node = next(n for n in flow.nodes if n.id == "logic_switch")
    assert len(logic_node.branches) == 2
    agent_node = next(n for n in flow.nodes if n.id == "agent_switch")
    assert len(agent_node.branches) == 2
    assert agent_node.agentic_input == "user_choice"

    # 2. Validation error on undeclared variable in LogicalSwitch branch
    with pytest.raises(ValidationError, match="is not defined in the graph state"):
        apply_graph_update(
            flow,
            GraphUpdateInput(
                nodes={
                    "upsert": [
                        NodeUpsertInput(
                            id="invalid_logic_switch",
                            node_type=NodeType.LOGICAL_SWITCH,
                            branches={"Branch1": {"expression": {"unregistered_var": {"gt": 0}}, "target": "end"}},
                        )
                    ]
                }
            ),
        )

    # 3. Validation error on undeclared agentic_input in AgenticSwitch
    with pytest.raises(ValidationError, match="is not defined in graph state"):
        apply_graph_update(
            flow,
            GraphUpdateInput(
                nodes={
                    "upsert": [
                        NodeUpsertInput(
                            id="invalid_agent_switch",
                            node_type=NodeType.AGENTIC_SWITCH,
                            agentic_input="unregistered_var",
                            branches={"Branch1": {"target": "end"}},
                        )
                    ]
                }
            ),
        )


def test_pipeline_rag_and_interrupt_nodes() -> None:
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    # 1. Setup state variables
    setup = GraphUpdateInput(
        variables={
            "upsert": [
                VariableUpsertInput(key="query_text", type="string", default_value="search"),
                VariableUpsertInput(key="doc_context", type="string", default_value=""),
                VariableUpsertInput(key="human_response", type="string", default_value=""),
            ]
        },
        nodes={
            "upsert": [
                NodeUpsertInput(
                    id="retriever",
                    node_type=NodeType.RAG_RETRIEVER,
                    query_var="query_text",
                    context_output_var="doc_context",
                    knowledge_base="kb_docs",
                    top_k=3,
                    target="human_interrupt",
                ),
                NodeUpsertInput(
                    id="human_interrupt",
                    node_type=NodeType.INTERRUPT,
                    resume_var="human_response",
                    payload_vars=["doc_context"],
                    target="end",
                ),
            ]
        },
        start_target="retriever",
    )
    flow = apply_graph_update(flow, setup)

    retriever_node = next(n for n in flow.nodes if n.id == "retriever")
    assert retriever_node.query_var == "query_text"
    assert retriever_node.context_output_var == "doc_context"
    assert retriever_node.knowledge_base == "kb_docs"
    assert retriever_node.top_k == 3

    interrupt_node = next(n for n in flow.nodes if n.id == "human_interrupt")
    assert interrupt_node.resume_var == "human_response"
    assert interrupt_node.payload_vars == ["doc_context"]

    # 2. Validation error on undeclared RAG query_var
    with pytest.raises(ValidationError, match="is not defined in graph state"):
        apply_graph_update(
            flow,
            GraphUpdateInput(
                nodes={
                    "upsert": [
                        NodeUpsertInput(
                            id="bad_rag",
                            node_type=NodeType.RAG_RETRIEVER,
                            query_var="unregistered_query",
                            context_output_var="doc_context",
                        )
                    ]
                }
            ),
        )

    # 3. Validation error on undeclared Interrupt payload_var
    with pytest.raises(ValidationError, match="is not defined in graph state"):
        apply_graph_update(
            flow,
            GraphUpdateInput(
                nodes={
                    "upsert": [
                        NodeUpsertInput(
                            id="bad_interrupt",
                            node_type=NodeType.INTERRUPT,
                            payload_vars=["unregistered_payload"],
                            resume_var="human_response",
                        )
                    ]
                }
            ),
        )


def test_cascading_renames_all_node_types() -> None:
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    setup = GraphUpdateInput(
        variables={
            "upsert": [
                VariableUpsertInput(key="q_var", type="string", default_value=""),
                VariableUpsertInput(key="out_var", type="string", default_value=""),
                VariableUpsertInput(key="choice_var", type="string", default_value=""),
            ]
        },
        nodes={
            "upsert": [
                NodeUpsertInput(
                    id="agent_assigner",
                    node_type=NodeType.AGENTIC_ASSIGNER,
                    prompt="Prompt {q_var}",
                    agentic_inputs=["q_var"],
                    agentic_outputs=[AgenticOutputInput(key="out_var", type="string")],
                    target="rag_node",
                ),
                NodeUpsertInput(
                    id="rag_node",
                    node_type=NodeType.RAG_RETRIEVER,
                    query_var="q_var",
                    context_output_var="out_var",
                    target="interrupt_node",
                ),
                NodeUpsertInput(
                    id="interrupt_node",
                    node_type=NodeType.INTERRUPT,
                    payload_vars=["q_var"],
                    resume_var="choice_var",
                    target="agent_switch",
                ),
                NodeUpsertInput(
                    id="agent_switch",
                    node_type=NodeType.AGENTIC_SWITCH,
                    agentic_input="choice_var",
                    branches={"Next": {"target": "end"}},
                ),
            ]
        },
        start_target="agent_assigner",
    )
    flow = apply_graph_update(flow, setup)

    # Rename q_var -> query_renamed
    flow = apply_graph_update(
        flow, GraphUpdateInput(rename_variables=[RenameInput(old_key="q_var", new_key="query_renamed")])
    )
    # Rename out_var -> context_renamed
    flow = apply_graph_update(
        flow, GraphUpdateInput(rename_variables=[RenameInput(old_key="out_var", new_key="context_renamed")])
    )
    # Rename choice_var -> answer_renamed
    flow = apply_graph_update(
        flow, GraphUpdateInput(rename_variables=[RenameInput(old_key="choice_var", new_key="answer_renamed")])
    )

    agent_assigner = next(n for n in flow.nodes if n.id == "agent_assigner")
    assert agent_assigner.agentic_inputs == ["query_renamed"]
    assert agent_assigner.agentic_outputs == ["context_renamed"]

    rag_node = next(n for n in flow.nodes if n.id == "rag_node")
    assert rag_node.query_var == "query_renamed"
    assert rag_node.context_output_var == "context_renamed"

    interrupt_node = next(n for n in flow.nodes if n.id == "interrupt_node")
    assert interrupt_node.payload_vars == ["query_renamed"]
    assert interrupt_node.resume_var == "answer_renamed"

    agent_switch = next(n for n in flow.nodes if n.id == "agent_switch")
    assert agent_switch.agentic_input == "answer_renamed"


def test_rename_and_delete_error_cases() -> None:
    flow = GraphFlowData(nodes=[], edges=[], state=[])
    setup = GraphUpdateInput(
        variables={"upsert": [VariableUpsertInput(key="v1", type="string", default_value="")]},
        nodes={"upsert": [NodeUpsertInput(id="n1", node_type=NodeType.LOGICAL_ASSIGNER, assignments=[], target="end")]},
        start_target="n1",
    )
    flow = apply_graph_update(flow, setup)

    # 1. Rename non-existent variable
    with pytest.raises(ValidationError, match="not found in graph state"):
        apply_graph_update(flow, GraphUpdateInput(rename_variables=[RenameInput(old_key="non_existent", new_key="v2")]))

    # 2. Rename variable to existing key
    apply_graph_update(
        flow, GraphUpdateInput(variables={"upsert": [VariableUpsertInput(key="v2", type="string", default_value="")]})
    )
    with pytest.raises(ValidationError, match="already exists"):
        apply_graph_update(flow, GraphUpdateInput(rename_variables=[RenameInput(old_key="v1", new_key="v2")]))

    # 3. Rename non-existent node
    with pytest.raises(ValidationError, match="not found"):
        apply_graph_update(
            flow, GraphUpdateInput(rename_nodes=[RenameInput(old_key="non_existent_node", new_key="n2")])
        )

    # 4. Rename node to existing node ID
    apply_graph_update(
        flow,
        GraphUpdateInput(
            nodes={
                "upsert": [NodeUpsertInput(id="n2", node_type=NodeType.LOGICAL_ASSIGNER, assignments=[], target="end")]
            }
        ),
    )
    with pytest.raises(ValidationError, match="already exists"):
        apply_graph_update(flow, GraphUpdateInput(rename_nodes=[RenameInput(old_key="n1", new_key="n2")]))

    # 5. Delete non-existent node / variable
    with pytest.raises(ValidationError, match="not found in state"):
        apply_graph_update(flow, GraphUpdateInput(variables={"delete": ["fake_var"]}))

    with pytest.raises(ValidationError, match="not found"):
        apply_graph_update(flow, GraphUpdateInput(nodes={"delete": ["fake_node"]}))
