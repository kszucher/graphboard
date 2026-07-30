from typing import Any

from app.graphs.compiler import generate_graph_code
from app.graphs.schemas import GraphFlowData


async def test_generate_graph_code_empty() -> None:
    payload: dict[str, Any] = {"nodes": [], "edges": []}
    flow_data = GraphFlowData.model_validate(payload)
    code = await generate_graph_code(flow_data)
    assert "class State(TypedDict):" in code
    assert "workflow = StateGraph(State)" in code
    assert "app = workflow.compile()" in code


async def test_generate_graph_code_with_variables() -> None:
    payload: dict[str, Any] = {
        "nodes": [
            {
                "id": "def1",
                "node_type": "DEFINER",
                "variables": [
                    {"key": "user_id", "type": "number", "default_value": 0},
                    {"key": "username", "type": "string", "default_value": "guest"},
                ],
            }
        ],
        "edges": [],
    }
    flow_data = GraphFlowData.model_validate(payload)
    code = await generate_graph_code(flow_data)
    assert "user_id: int" in code
    assert "username: str" in code
    assert '"user_id": 0' in code
    assert '"username": "guest"' in code


async def test_generate_graph_code_with_step_node() -> None:
    payload: dict[str, Any] = {
        "nodes": [
            {
                "id": "def1",
                "node_type": "DEFINER",
                "variables": [
                    {"id": "v1", "key": "status", "type": "string", "default_value": ""},
                ],
            },
            {
                "id": "step_1",
                "node_type": "STEP",
                "slots": [{"target_var_key": "status", "expression": {"kind": "literal", "value": "processed"}}],
            },
        ],
        "edges": [
            {"source_id": "start", "target_id": "step_1"},
            {"source_id": "step_1", "source_type": "node", "target_id": "end"},
        ],
    }
    flow_data = GraphFlowData.model_validate(payload)
    code = await generate_graph_code(flow_data)
    assert "def step_1(state: State) -> dict:" in code
    assert '"status": "processed"' in code
    assert 'workflow.add_node("step_1", step_1)' in code
    assert 'workflow.add_edge(START, "step_1")' in code
    assert 'workflow.add_edge("step_1", END)' in code


async def test_generate_graph_code_with_switch_node() -> None:
    payload: dict[str, Any] = {
        "nodes": [
            {
                "id": "def1",
                "node_type": "DEFINER",
                "variables": [
                    {"id": "v1", "key": "status", "type": "string", "default_value": "active"},
                ],
            },
            {
                "id": "switch_1",
                "node_type": "SWITCH",
                "slots": [
                    {
                        "id": "slot_a",
                        "raw_string": "is_active",
                        "expression": {
                            "kind": "binaryOp",
                            "op": "==",
                            "left": {"kind": "stateRef", "varKey": "status"},
                            "right": {"kind": "literal", "value": "active"},
                        },
                    }
                ],
            },
        ],
        "edges": [{"source_id": "slot_a", "source_type": "slot", "target_id": "end"}],
    }
    flow_data = GraphFlowData.model_validate(payload)
    code = await generate_graph_code(flow_data)
    assert "def switch_1(state: State) -> str:" in code
    assert 'if state.get("status") == "active":' in code
    assert 'return "is_active"' in code
    assert "workflow.add_conditional_edges(" in code


