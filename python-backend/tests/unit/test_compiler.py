import ast

from app.modules.graphs.compiler import DirectLangGraphCompiler, generate_graph_code
from app.modules.graphs.nodes import (
    AgenticAssignerNode,
    Branch,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
)
from app.modules.graphs.schemas import (
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
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
    from app.modules.graphs.schemas import ExpressionRecord

    flow_data = GraphFlowData(
        nodes=[
            LogicalAssignerNode(
                id="assigner_1",
                assignments=[
                    LogicalAssignmentSchema(
                        id="asgn_1",
                        target_var_key="status",
                        expr_id="expr_status",
                    ),
                ],
            ),
        ],
        edges=[
            EdgeRead(source="start", target="assigner_1"),
            EdgeRead(source="assigner_1", target="end"),
        ],
        state=[
            DefinerVariableSchema(id="v1", key="status", type="string", default_value=""),
        ],
        expressions={
            "expr_status": ExpressionRecord(
                id="expr_status",
                expr={"set": "processed"},
            )
        },
    )
    code = await generate_graph_code(flow_data)
    assert "def assigner_1(state: State) -> dict:" in code
    assert '"status": "processed"' in code or "'status': 'processed'" in code
    assert 'workflow.add_node("assigner_1", assigner_1)' in code
    assert 'workflow.add_edge(START, "assigner_1")' in code
    assert 'workflow.add_edge("assigner_1", END)' in code


async def test_generate_graph_code_with_switch_node() -> None:
    from app.modules.graphs.schemas import ExpressionRecord

    flow_data = GraphFlowData(
        nodes=[
            LogicalSwitchNode(
                id="switch_1",
                branches=[
                    Branch(
                        id="switch_1_is_active",
                        label="is_active",
                        expr_id="expr_active",
                    )
                ],
            ),
        ],
        edges=[EdgeRead(source="switch_1", source_handle="switch_1_is_active", target="end")],
        state=[
            DefinerVariableSchema(id="v1", key="status", type="string", default_value="active"),
        ],
        expressions={
            "expr_active": ExpressionRecord(
                id="expr_active",
                expr={"status": {"equals": "active"}},
            )
        },
    )
    code = await generate_graph_code(flow_data)
    assert "def switch_1(state: State) -> str:" in code
    assert "state.get('status') == 'active'" in code or 'state.get("status") == "active"' in code
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
            EdgeRead(source="start", target="agentic_1"),
            EdgeRead(source="agentic_1", target="end"),
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
    from app.modules.graphs.defaults import build_default_trivia_graph_flow_data

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
    assert "class lifeline_switchOption(str, Enum):" in code
    assert "class lifeline_switchChoice(BaseModel):" in code
    assert "def lifeline_switch(state: State) -> str:" in code
    assert (
        "workflow.add_conditional_edges('parse_answer', lifeline_switch," in code
        or 'workflow.add_conditional_edges("parse_answer", lifeline_switch,' in code
    )
