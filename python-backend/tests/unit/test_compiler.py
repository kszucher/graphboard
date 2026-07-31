from app.constants import NodeType
from app.graphs.compiler import generate_graph_code
from app.graphs.schemas import (
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
    NodeRead,
    SlotRead,
)


async def test_generate_graph_code_empty() -> None:
    flow_data = GraphFlowData(nodes=[], edges=[])
    code = await generate_graph_code(flow_data)
    assert "class State(TypedDict):" in code
    assert "workflow = StateGraph(State)" in code
    assert "app = workflow.compile()" in code


async def test_generate_graph_code_with_variables() -> None:
    flow_data = GraphFlowData(
        nodes=[
            NodeRead(
                id="def1",
                node_type=NodeType.DEFINER,
                variables=[
                    DefinerVariableSchema(key="user_id", type="number", default_value=0),
                    DefinerVariableSchema(key="username", type="string", default_value="guest"),
                ],
            )
        ],
        edges=[],
    )
    code = await generate_graph_code(flow_data)
    assert "user_id: int" in code
    assert "username: str" in code
    assert '"user_id": 0' in code
    assert '"username": "guest"' in code


async def test_generate_graph_code_with_step_node() -> None:
    flow_data = GraphFlowData(
        nodes=[
            NodeRead(
                id="def1",
                node_type=NodeType.DEFINER,
                variables=[
                    DefinerVariableSchema(id="v1", key="status", type="string", default_value=""),
                ],
            ),
            NodeRead(
                id="step_1",
                node_type=NodeType.STEP,
                slots=[
                    SlotRead(target_var_key="status", expression={"kind": "literal", "value": "processed"}),
                ],
            ),
        ],
        edges=[
            EdgeRead(source_id="start", target_id="step_1"),
            EdgeRead(source_id="step_1", source_type="node", target_id="end"),
        ],
    )
    code = await generate_graph_code(flow_data)
    assert "def step_1(state: State) -> dict:" in code
    assert '"status": "processed"' in code
    assert 'workflow.add_node("step_1", step_1)' in code
    assert 'workflow.add_edge(START, "step_1")' in code
    assert 'workflow.add_edge("step_1", END)' in code


async def test_generate_graph_code_with_switch_node() -> None:
    flow_data = GraphFlowData(
        nodes=[
            NodeRead(
                id="def1",
                node_type=NodeType.DEFINER,
                variables=[
                    DefinerVariableSchema(id="v1", key="status", type="string", default_value="active"),
                ],
            ),
            NodeRead(
                id="switch_1",
                node_type=NodeType.SWITCH,
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
    )
    code = await generate_graph_code(flow_data)
    assert "def switch_1(state: State) -> str:" in code
    assert 'if state.get("status") == "active":' in code
    assert 'return "is_active"' in code
    assert "workflow.add_conditional_edges(" in code


async def test_generate_graph_code_with_agentic_assigner() -> None:
    flow_data = GraphFlowData(
        nodes=[
            NodeRead(
                id="def1",
                node_type=NodeType.DEFINER,
                variables=[
                    DefinerVariableSchema(id="v1", key="category", type="string", default_value="math"),
                    DefinerVariableSchema(id="v2", key="question", type="string", default_value=""),
                ],
            ),
            NodeRead(
                id="agentic_1",
                node_type=NodeType.AGENTIC_ASSIGNER,
                prompt="Generate a question about {category}.",
                agentic_inputs=["category"],
                agentic_outputs=["question"],
            ),
        ],
        edges=[
            EdgeRead(source_id="start", target_id="agentic_1"),
            EdgeRead(source_id="agentic_1", source_type="node", target_id="end"),
        ],
    )
    code = await generate_graph_code(flow_data)
    assert "class agentic_1Output(BaseModel):" in code
    assert "question: str" in code
    assert "def agentic_1(state: State) -> dict:" in code
    assert "client = Groq()" in code
    assert 'prompt_text = "Generate a question about {category}."' in code or "prompt_text = 'Generate a question about {category}.'" in code
    assert "prompt_text = prompt_text.replace(" in code
    assert '"{category}", str(state.get("category"))' in code or "'{category}', str(state.get('category'))" in code
    assert "from pydantic import BaseModel, Field" in code
    assert "from groq import Groq" in code
