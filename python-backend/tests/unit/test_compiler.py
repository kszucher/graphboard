from app.graphs.compiler import generate_graph_code
from app.graphs.schemas import (
    AgenticAssignerNode,
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    SlotRead,
    SwitchNode,
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
            SwitchNode(
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
    assert "class agentic_1Output(BaseModel):" in code
    assert "question: str" in code
    assert "def agentic_1(state: State) -> dict:" in code
    assert "client = Groq()" in code
    assert (
        'prompt_text = "Generate a question about {category}."' in code
        or "prompt_text = 'Generate a question about {category}.'" in code
    )
    assert "prompt_text = prompt_text.replace(" in code
    assert '"{category}", str(state.get("category"))' in code or "'{category}', str(state.get('category'))" in code
    assert "from pydantic import BaseModel, Field" in code
    assert "from groq import Groq" in code


async def test_default_example_graph_ast_compilation() -> None:
    import ast

    from app.graphs.compiler import PureAstLangGraphCompiler
    from app.graphs.defaults import build_default_trivia_graph_flow_data
    from app.graphs.resolver import SemanticResolver

    flow_data = build_default_trivia_graph_flow_data()
    canonical = SemanticResolver().resolve(flow_data)
    code = PureAstLangGraphCompiler(canonical).compile()

    # 1. Check valid AST syntax
    tree = ast.parse(code)
    assert tree is not None

    print("\n--- GENERATED CODE ---\n", code)

    # 2. Check key architectural graph definitions in generated Python string
    assert (
        "workflow.add_edge('ask_question', 'parse_answer')" in code
        or 'workflow.add_edge("ask_question", "parse_answer")' in code
    )
    assert (
        "workflow.add_conditional_edges('parse_answer', parse_retry," in code
        or 'workflow.add_conditional_edges("parse_answer", parse_retry,' in code
    )
    assert "def reset_parse_retry(state: State) -> dict:" in code
    assert "'valid': 'reset_parse_retry'" in code or '"valid": "reset_parse_retry"' in code
    assert (
        "workflow.add_node('reset_parse_retry', reset_parse_retry)" in code
        or 'workflow.add_node("reset_parse_retry", reset_parse_retry)' in code
    )
    assert "def reset_confirm_retry(state: State) -> dict:" in code
    assert (
        "workflow.add_node('lifeline_switch', lifeline_switch)" in code
        or 'workflow.add_node("lifeline_switch", lifeline_switch)' in code
    )
    assert (
        "workflow.add_conditional_edges('lifeline_switch', __lifeline_switch_route," in code
        or 'workflow.add_conditional_edges("lifeline_switch", __lifeline_switch_route,' in code
    )
    assert "def confirm_retry(state: State) -> str:" in code
    assert (
        "workflow.add_conditional_edges('confirm_answer', __confirm_answer_route," in code
        or 'workflow.add_conditional_edges("confirm_answer", __confirm_answer_route,' in code
    )
    assert (
        "workflow.add_conditional_edges('confirm_retry', confirm_retry," in code
        or 'workflow.add_conditional_edges("confirm_retry", confirm_retry,' in code
    )
    assert (
        "state.get('__retry_confirm_retry_count', 0) < 2" in code
        or 'state.get("__retry_confirm_retry_count", 0) < 2' in code
        or "__retry_confirm_retry_count" in code
    )
    assert (
        "__confirm_answer_decision: str" in code
        or "'__confirm_answer_decision': str" in code
        or "__confirm_answer_decision" in code
    )
    assert (
        "__sys_choice_lifeline_switch: str" in code
        or "'__sys_choice_lifeline_switch': str" in code
        or "__sys_choice_lifeline_switch" in code
    )
    assert (
        "__sys_choice_choose_lifeline: str" in code
        or "'__sys_choice_choose_lifeline': str" in code
        or "__sys_choice_choose_lifeline" in code
    )
