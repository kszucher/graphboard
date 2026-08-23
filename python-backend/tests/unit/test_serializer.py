from app.modules.graphs.engine.serializer import serialize_flow_to_code
from app.modules.graphs.schemas import (
    AgenticAssignerNode,
    AgenticBranch,
    AgenticSwitchNode,
    Branch,
    DefinerVariableSchema,
    EdgeRead,
    EndNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    RagRetrieverNode,
    StartNode,
)
from app.modules.graphs.templates import build_default_trivia_graph_flow_data


def test_serialize_flow_to_code_all_nodes() -> None:
    flow = GraphFlowData(
        nodes=[
            StartNode(id="start"),
            LogicalAssignerNode(
                id="assigner_1",
                assignments=[
                    LogicalAssignmentSchema(id="a1", target_var_key="score", expression="score + 10"),
                ],
            ),
            AgenticAssignerNode(
                id="agentic_1",
                prompt='Generate question about "{topic}"',
                agentic_inputs=["topic"],
                agentic_outputs=["question"],
            ),
            RagRetrieverNode(
                id="retriever_1",
                query_var="query",
                context_output_var="context",
                knowledge_base="kb_trivia",
                top_k=5,
            ),
            InterruptNode(
                id="interrupt_1",
                resume_var="user_answer",
                payload_vars=["question", "context"],
            ),
            LogicalSwitchNode(
                id="switch_1",
                branches=[
                    Branch(id="switch_1_high", label="High", expression="score >= 100"),
                    Branch(id="switch_1_default", label="Default", expression=None),
                ],
            ),
            AgenticSwitchNode(
                id="agentic_switch_1",
                agentic_input="user_answer",
                branches=[
                    AgenticBranch(id="agentic_switch_1_opt_a", label="Option A"),
                    AgenticBranch(id="agentic_switch_1_opt_b", label="Option B"),
                ],
            ),
            EndNode(id="end"),
        ],
        edges=[
            EdgeRead(source="start", target="assigner_1"),
            EdgeRead(source="assigner_1", target="agentic_1"),
            EdgeRead(source="agentic_1", target="retriever_1"),
            EdgeRead(source="retriever_1", target="interrupt_1"),
            EdgeRead(source="interrupt_1", target="switch_1"),
            EdgeRead(source="switch_1", source_handle="switch_1_high", target="agentic_switch_1"),
            EdgeRead(source="switch_1", source_handle="switch_1_default", target="end"),
            EdgeRead(source="agentic_switch_1", source_handle="agentic_switch_1_opt_a", target="end"),
            EdgeRead(source="agentic_switch_1", source_handle="agentic_switch_1_opt_b", target="end"),
        ],
        state=[
            DefinerVariableSchema(id="v1", key="score", type="number", default_value=0),
            DefinerVariableSchema(
                id="v2", key="topic", type="string", default_value="geography", description="Quiz topic"
            ),
            DefinerVariableSchema(id="v3", key="question", type="string", default_value=""),
            DefinerVariableSchema(id="v4", key="query", type="string", default_value=""),
            DefinerVariableSchema(id="v5", key="context", type="string", default_value=""),
            DefinerVariableSchema(id="v6", key="user_answer", type="string", default_value=""),
        ],
    )

    yaml_code = serialize_flow_to_code(flow)

    # Check State section
    assert "State:" in yaml_code
    assert '- { key: "score", type: "number", default: 0 }' in yaml_code
    assert '- { key: "topic", type: "string", default: "geography", description: "Quiz topic" }' in yaml_code

    # Check Flow section
    assert "Flow:" in yaml_code
    assert "  start -> assigner_1" in yaml_code

    # Check nodes
    assert '  assigner_1 [LOGICAL_ASSIGNER], target: "agentic_1":' in yaml_code
    assert '      - { target_var_key: "score", expression: "score + 10" }' in yaml_code

    assert '  agentic_1 [AGENTIC_ASSIGNER], target: "retriever_1":' in yaml_code
    assert '    prompt: "Generate question about \\"{topic}\\""' in yaml_code
    assert '    inputs: ["topic"]' in yaml_code
    assert '    outputs: [{"key": "question", "type": "string"}]' in yaml_code

    assert '  retriever_1 [RAG_RETRIEVER], target: "interrupt_1":' in yaml_code
    assert '    query_var: "query", context_output_var: "context", knowledge_base: "kb_trivia", top_k: 5' in yaml_code

    assert '  interrupt_1 [INTERRUPT], target: "switch_1":' in yaml_code
    assert '    resume_var: "user_answer", payload_vars: ["question", "context"]' in yaml_code

    assert "  switch_1 [LOGICAL_SWITCH]:" in yaml_code
    assert '    - branch "High": "score >= 100" -> agentic_switch_1' in yaml_code
    assert '    - branch "Default": (default) -> end' in yaml_code

    assert "  agentic_switch_1 [AGENTIC_SWITCH]:" in yaml_code
    assert '    agentic_input: "user_answer"' in yaml_code
    assert '    - case "Option A" -> end' in yaml_code
    assert '    - case "Option B" -> end' in yaml_code


def test_serialize_flow_to_code_default_trivia() -> None:
    flow = build_default_trivia_graph_flow_data()
    yaml_code = serialize_flow_to_code(flow)

    assert "State:" in yaml_code
    assert "Flow:" in yaml_code
    assert "  start -> loop_questions" in yaml_code
    assert "lifeline_switch [AGENTIC_SWITCH]:" in yaml_code
    assert 'case "Submit"' in yaml_code
    assert 'case "Lifeline"' in yaml_code
    assert "choose_lifeline [AGENTIC_SWITCH]:" in yaml_code
    assert 'case "Audience"' in yaml_code
    assert 'case "Phone"' in yaml_code
