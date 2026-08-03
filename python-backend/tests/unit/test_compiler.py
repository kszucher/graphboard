import ast

from app.graphs.compiler import DirectLangGraphCompiler, generate_graph_code
from app.graphs.schemas import (
    AgenticAssignerNode,
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    SlotRead,
)


async def test_generate_graph_code_empty() -> None:
    flow_data = GraphFlowData(nodes=[], edges=[], state=[])
    code = await generate_graph_code(flow_data)
    assert "class State(TypedDict):" in code
    assert "workflow = StateGraph(State)" in code
    assert "app = workflow.compile()" in code


async def test_generate_graph_code_with_variables() -> None:
    flow_data = GraphFlowData(
        nodes=[],
        edges=[],
        state=[
            DefinerVariableSchema(key="user_id", type="number", default_value=0),
            DefinerVariableSchema(key="username", type="string", default_value="guest"),
        ],
    )
    code = await generate_graph_code(flow_data)
    assert "user_id: int" in code
    assert "username: str" in code
    assert '"user_id": 0' in code
    assert '"username": "guest"' in code


async def test_generate_graph_code_with_logical_assigner() -> None:
    flow_data = GraphFlowData(
        nodes=[
            LogicalAssignerNode(
                id="assigner_1",
                assignments=[
                    LogicalAssignmentSchema(
                        id="asgn_1",
                        target_var_key="status",
                        expression={"kind": "literal", "value": "processed"},
                    ),
                ],
            ),
        ],
        edges=[
            EdgeRead(source_id="start", target_id="assigner_1"),
            EdgeRead(source_id="assigner_1", source_type="node", target_id="end"),
        ],
        state=[
            DefinerVariableSchema(id="v1", key="status", type="string", default_value=""),
        ],
    )
    code = await generate_graph_code(flow_data)
    assert "def assigner_1(state: State) -> dict:" in code
    assert '"status": "processed"' in code
    assert 'workflow.add_node("assigner_1", assigner_1)' in code
    assert 'workflow.add_edge(START, "assigner_1")' in code
    assert 'workflow.add_edge("assigner_1", END)' in code


async def test_generate_graph_code_with_switch_node() -> None:
    flow_data = GraphFlowData(
        nodes=[
            LogicalSwitchNode(
                id="switch_1",
                slots=[
                    SlotRead(
                        id="slot_a",
                        raw_string="is_active",
                        expression={
                            "kind": "binaryOp",
                            "op": "==",
                            "left": {"kind": "stateRef", "varKey": "status"},
                            "right": {"kind": "literal", "value": "active"},
                        },
                    )
                ],
            ),
        ],
        edges=[EdgeRead(source_id="slot_a", source_type="slot", target_id="end")],
        state=[
            DefinerVariableSchema(id="v1", key="status", type="string", default_value="active"),
        ],
    )
    code = await generate_graph_code(flow_data)
    assert "def switch_1(state: State) -> str:" in code
    assert 'if state.get("status") == "active":' in code
    assert 'return "is_active"' in code
    assert "workflow.add_conditional_edges(" in code


async def test_generate_graph_code_with_agentic_assigner() -> None:
    flow_data = GraphFlowData(
        nodes=[
            AgenticAssignerNode(
                id="agentic_1",
                prompt="Generate a question about {category}.",
                agentic_inputs=["category"],
                agentic_outputs=["question"],
            ),
        ],
        edges=[
            EdgeRead(source_id="start", target_id="agentic_1"),
            EdgeRead(source_id="agentic_1", source_type="node", target_id="end"),
        ],
        state=[
            DefinerVariableSchema(id="v1", key="category", type="string", default_value="math"),
            DefinerVariableSchema(id="v2", key="question", type="string", default_value=""),
        ],
    )
    code = await generate_graph_code(flow_data)
    assert "class agentic_1Output(BaseModel):" in code
    assert "question: str" in code
    assert "def agentic_1(state: State) -> dict:" in code
    assert 'workflow.add_node("agentic_1", agentic_1)' in code
    assert 'workflow.add_edge(START, "agentic_1")' in code
    assert 'workflow.add_edge("agentic_1", END)' in code
    assert "client = Groq()" in code


async def test_default_example_graph_ast_compilation() -> None:
    from app.graphs.defaults import build_default_trivia_graph_flow_data

    flow_data = build_default_trivia_graph_flow_data()
    code = DirectLangGraphCompiler(flow_data).compile()

    # 1. Check valid AST syntax
    tree = ast.parse(code)
    assert tree is not None

    # 2. Check key architectural graph definitions in generated Python string
    assert (
        "workflow.add_edge('ask_question', 'parse_answer')" in code
        or 'workflow.add_edge("ask_question", "parse_answer")' in code
    )
    assert (
        "workflow.add_edge('gen_question', 'ask_question')" in code
        or 'workflow.add_edge("gen_question", "ask_question")' in code
    )
    assert (
        "workflow.add_node('lifeline_switch', lifeline_switch)" in code
        or 'workflow.add_node("lifeline_switch", lifeline_switch)' in code
    )
    assert (
        "workflow.add_conditional_edges('lifeline_switch', __lifeline_switch_route," in code
        or 'workflow.add_conditional_edges("lifeline_switch", __lifeline_switch_route,' in code
    )
