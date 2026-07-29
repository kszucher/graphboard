from typing import Any

from app.graphs.compiler import ast_expr_to_py, generate_graph_code, run_ruff_diagnostics
from app.graphs.schemas import GraphFlowData


def test_ast_expr_to_py_empty() -> None:
    assert ast_expr_to_py(None) == "True"
    assert ast_expr_to_py(None, default_fallback="False") == "False"


def test_ast_expr_to_py_literal() -> None:
    ast: dict[str, Any] = {"kind": "literal", "value": "hello"}
    assert ast_expr_to_py(ast) == "'hello'"

    ast_num: dict[str, Any] = {"kind": "literal", "value": 42}
    assert ast_expr_to_py(ast_num) == "42"

    ast_bool: dict[str, Any] = {"kind": "literal", "value": True}
    assert ast_expr_to_py(ast_bool) == "True"


def test_ast_expr_to_py_stateRef() -> None:
    ast: dict[str, Any] = {"kind": "stateRef", "varKey": "user_age"}
    assert ast_expr_to_py(ast) == "state.get('user_age')"


def test_ast_expr_to_py_binaryOp() -> None:
    ast: dict[str, Any] = {
        "kind": "binaryOp",
        "op": "==",
        "left": {"kind": "stateRef", "varKey": "status"},
        "right": {"kind": "literal", "value": "active"},
    }
    assert ast_expr_to_py(ast) == "state.get('status') == 'active'"


def test_ast_expr_to_py_unaryOp() -> None:
    ast: dict[str, Any] = {"kind": "unaryOp", "op": "not", "expr": {"kind": "stateRef", "varKey": "is_valid"}}
    assert ast_expr_to_py(ast) == "not state.get('is_valid')"


async def test_generate_graph_code_empty() -> None:
    payload: dict[str, Any] = {"nodes": [], "edges": [], "operations": {}}
    flow_data = GraphFlowData.model_validate(payload)
    code = await generate_graph_code(flow_data)
    assert "class State(TypedDict):" in code
    assert "workflow = StateGraph(State)" in code
    assert "workflow.compile()" in code


async def test_generate_graph_code_with_variables() -> None:
    payload: dict[str, Any] = {
        "nodes": [],
        "edges": [],
        "operations": {
            "definer": [
                {
                    "id": "def1",
                    "variables": [
                        {"key": "user_id", "type": "number", "default_value": 0},
                        {"key": "username", "type": "string", "default_value": "guest"},
                    ],
                }
            ]
        },
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
                "id": "step_1",
                "node_type": "STEP",
                "slots": [{"target_var_key": "status", "expression": {"kind": "literal", "value": "processed"}}],
            }
        ],
        "edges": [
            {"source_id": "start", "target_id": "step_1"},
            {"source_id": "step_1", "source_type": "node", "target_id": "end"},
        ],
        "operations": {
            "definer": [
                {
                    "id": "def1",
                    "variables": [
                        {"id": "v1", "key": "status", "type": "string", "default_value": ""},
                    ],
                }
            ]
        },
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
            }
        ],
        "edges": [{"source_id": "slot_a", "source_type": "slot", "target_id": "end"}],
        "operations": {
            "definer": [
                {
                    "id": "def1",
                    "variables": [
                        {"id": "v1", "key": "status", "type": "string", "default_value": "active"},
                    ],
                }
            ]
        },
    }
    flow_data = GraphFlowData.model_validate(payload)
    code = await generate_graph_code(flow_data)
    assert "def switch_1(state: State) -> str:" in code
    assert 'if state.get("status") == "active":' in code or 'if (state.get("status") == "active"):' in code
    assert 'return "is_active"' in code
    assert "workflow.add_conditional_edges(" in code


async def test_run_ruff_diagnostics_empty() -> None:
    diagnostics = await run_ruff_diagnostics("")
    assert len(diagnostics) == 0


async def test_run_ruff_diagnostics_syntax_error() -> None:
    code = "def my_func():\n    return 'hello"
    diagnostics = await run_ruff_diagnostics(code)
    # Ruff should detect the unclosed string literal (SyntaxError)
    assert len(diagnostics) > 0
    assert diagnostics[0].severity in ["error", "warning"]
