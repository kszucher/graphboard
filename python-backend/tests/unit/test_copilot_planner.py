import pytest

from app.modules.copilot.state import CopilotState
from app.modules.copilot.translator import translate_plan_node


def test_translate_plan_node_upsert_node_polymorphic() -> None:
    state: CopilotState = {
        "trace_id": "test_trace",
        "tool_calls": [
            {
                "name": "upsert_variable",
                "arguments": '{"key": "score", "type": "number", "default_value": 0, "description": null}',
            },
            {
                "name": "upsert_node",
                "arguments": (
                    '{"id": "new_assigner", "node_type": "LOGICAL_ASSIGNER", '
                    '"config": {"assignments": [{"target_var_key": "score", "assignment": {"value": 10}}]}, '
                    '"target": "end"}'
                ),
            },
            {"name": "upsert_node", "arguments": '{"id": "start", "target": "new_assigner"}'},
        ],
        "initial_flow_data": {
            "nodes": [{"id": "end", "node_type": "LOGICAL_SWITCH", "branches": {}}],
            "edges": [],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]
    assert ops["start_target"] == "new_assigner"
    assert len(ops["variables"]["upsert"]) == 1
    assert ops["variables"]["upsert"][0]["key"] == "score"
    assert len(ops["nodes"]["upsert"]) == 1

    new_assigner_upsert = next(n for n in ops["nodes"]["upsert"] if n["id"] == "new_assigner")
    assert new_assigner_upsert["target"] == "end"
    assert new_assigner_upsert["assignments"][0]["target_var_key"] == "score"
    assert new_assigner_upsert["assignments"][0]["expression"] == 10


def test_translate_plan_node_upsert_switch_branch_surgical_delta() -> None:
    """Test surgically patching a single branch on an existing switch without overwriting other branches."""
    state: CopilotState = {
        "trace_id": "test_trace",
        "tool_calls": [
            {
                "name": "upsert_node",
                "arguments": (
                    '{"id": "phone_node", "node_type": "AGENTIC_ASSIGNER", '
                    '"config": {"prompt": "Call phone...", "agentic_inputs": [], "agentic_outputs": []}, '
                    '"target": "end"}'
                ),
            },
            {
                "name": "upsert_switch_branch",
                "arguments": '{"node_id": "choose_lifeline", "label": "Phone", "target": "phone_node", "condition": null}',
            },
        ],
        "initial_flow_data": {
            "nodes": [
                {
                    "id": "choose_lifeline",
                    "node_type": "AGENTIC_SWITCH",
                    "agentic_input": "user_answer",
                    "branches": [{"id": "br_aud", "label": "Audience"}],
                },
                {"id": "audience_votes", "node_type": "LOGICAL_ASSIGNER", "assignments": []},
                {"id": "end", "node_type": "LOGICAL_ASSIGNER", "assignments": []},
            ],
            "edges": [
                {"source": "start", "target": "choose_lifeline"},
                {"source": "choose_lifeline", "source_handle": "br_aud", "target": "audience_votes"},
            ],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]

    # choose_lifeline was updated with Phone branch, preserving Audience branch and agentic_input
    choose_upsert = next(n for n in ops["nodes"]["upsert"] if n["id"] == "choose_lifeline")
    assert choose_upsert["branches"]["Audience"]["target"] == "audience_votes"
    assert choose_upsert["branches"]["Phone"]["target"] == "phone_node"
    assert choose_upsert["agentic_input"] == "user_answer"

    # Ensure operations pass apply_graph_update without error
    from app.modules.graphs.operations import GraphUpdateInput, apply_graph_update
    from app.modules.graphs.schemas import AgenticSwitchNode, GraphFlowData

    initial_flow = GraphFlowData.model_validate(
        {
            **state["initial_flow_data"],
            "state": [{"id": "v1", "key": "user_answer", "type": "string", "default_value": ""}],
        }
    )
    updated_flow = apply_graph_update(initial_flow, GraphUpdateInput(**ops))
    assert len(updated_flow.nodes) == 4
    choose_node = next(n for n in updated_flow.nodes if n.id == "choose_lifeline")
    assert isinstance(choose_node, AgenticSwitchNode)
    assert len(choose_node.branches) == 2


def test_translate_plan_node_switch_with_closed_conditions() -> None:
    state: CopilotState = {
        "trace_id": "test_trace",
        "tool_calls": [
            {
                "name": "upsert_node",
                "arguments": (
                    '{"id": "switch_node", "node_type": "LOGICAL_SWITCH", "config": {"branches": ['
                    '{"label": "Yes", "condition": {"logic": "ALL", "conditions": [{"var": "score", "op": "gte", "literal_value": 10}]}, "target": "end"},'
                    '{"label": "No", "condition": null, "target": "end"}'
                    "]}}"
                ),
            },
            {"name": "upsert_node", "arguments": '{"id": "start", "target": "switch_node"}'},
            {
                "name": "upsert_switch_branch",
                "arguments": '{"node_id": "switch_node", "label": "No", "target": "end", "condition": null}',
            },
        ],
        "initial_flow_data": {
            "nodes": [{"id": "end", "node_type": "LOGICAL_ASSIGNER", "assignments": []}],
            "edges": [],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]
    assert ops["start_target"] == "switch_node"
    switch_upsert = next(n for n in ops["nodes"]["upsert"] if n["id"] == "switch_node")
    assert switch_upsert["branches"]["Yes"]["target"] == "end"
    assert switch_upsert["branches"]["Yes"]["expression"] == {"score": {"gte": 10}}
    assert switch_upsert["branches"]["No"]["target"] == "end"


def test_translate_plan_node_delete_and_rename_entity() -> None:
    state: CopilotState = {
        "trace_id": "test_trace",
        "tool_calls": [
            {"name": "delete_entity", "arguments": '{"kind": "variable", "id": "old_var"}'},
            {"name": "delete_entity", "arguments": '{"kind": "node", "id": "dead_node"}'},
            {"name": "rename_entity", "arguments": '{"kind": "variable", "old_name": "v1", "new_name": "v2"}'},
            {"name": "rename_entity", "arguments": '{"kind": "node", "old_name": "n1", "new_name": "n2"}'},
        ],
        "initial_flow_data": {
            "nodes": [{"id": "start", "node_type": "START"}],
            "edges": [],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]
    assert "old_var" in ops["variables"]["delete"]
    assert "dead_node" in ops["nodes"]["delete"]
    assert ops["rename_variables"] == [{"old_key": "v1", "new_key": "v2"}]
    assert ops["rename_nodes"] == [{"old_key": "n1", "new_key": "n2"}]


def test_translate_plan_node_partial_retargeting() -> None:
    """Test partial retargeting of existing node without re-specifying config."""
    state: CopilotState = {
        "trace_id": "test_trace",
        "tool_calls": [
            {
                "name": "upsert_node",
                "arguments": '{"id": "assigner_a", "target": "end"}',
            },
        ],
        "initial_flow_data": {
            "nodes": [
                {
                    "id": "assigner_a",
                    "node_type": "LOGICAL_ASSIGNER",
                    "assignments": [],
                },
                {"id": "end", "node_type": "END"},
            ],
            "edges": [{"source": "start", "target": "assigner_a"}],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]
    assigner_upsert = next(n for n in ops["nodes"]["upsert"] if n["id"] == "assigner_a")
    assert assigner_upsert["target"] == "end"


def test_validation_node_unreachable_node_error() -> None:
    from app.modules.copilot.workflow import validation_node

    state: CopilotState = {
        "trace_id": "test_trace",
        "tool_calls": [
            {
                "name": "upsert_node",
                "arguments": (
                    '{"id": "orphan_assigner", "node_type": "LOGICAL_ASSIGNER", '
                    '"config": {"assignments": [{"target_var_key": "x", "assignment": {"value": 1}}]}, '
                    '"target": "end"}'
                ),
            }
        ],
        "initial_flow_data": {
            "nodes": [
                {"id": "start", "node_type": "START"},
                {"id": "end", "node_type": "END"},
            ],
            "edges": [],
            "state": [{"id": "v_x", "key": "x", "type": "number", "default_value": 0}],
        },
    }

    translated = translate_plan_node(state)
    assert translated["operations"] is not None

    validation_state: CopilotState = {
        **state,
        "operations": translated["operations"],
        "retry_count": 0,
    }
    result = validation_node(validation_state)
    assert result["applied"] is False
    assert "unreachable from the START node" in str(result["validation_error"])
    assert "[UNREACHABLE_NODE]" in result["messages"][-1]["content"]


def test_translate_plan_node_orthogonal_collection_expressions() -> None:
    """Test translating a node with orthogonal collection expressions like sample and format."""
    state: CopilotState = {
        "trace_id": "test_trace",
        "tool_calls": [
            {
                "name": "upsert_variable",
                "arguments": '{"key": "options", "type": "array", "default_value": ["A", "B", "C", "D"]}',
            },
            {
                "name": "upsert_variable",
                "arguments": '{"key": "active_options", "type": "array", "default_value": []}',
            },
            {
                "name": "upsert_node",
                "arguments": (
                    '{"id": "fifty_fifty_node", "node_type": "LOGICAL_ASSIGNER", '
                    '"config": {"assignments": ['
                    '{"target_var_key": "active_options", "assignment": {"op": "sample", "list": {"var": "options"}, "count": 2}}'
                    "]}, "
                    '"target": "end"}'
                ),
            },
            {
                "name": "upsert_node",
                "arguments": '{"id": "start", "target": "fifty_fifty_node"}',
            },
        ],
        "initial_flow_data": {
            "nodes": [
                {"id": "start", "node_type": "START"},
                {"id": "end", "node_type": "END"},
            ],
            "edges": [],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]

    assert len(ops["variables"]["upsert"]) == 2
    assert len(ops["nodes"]["upsert"]) == 1

    node_upsert = ops["nodes"]["upsert"][0]
    assert node_upsert["id"] == "fifty_fifty_node"
    assert node_upsert["assignments"][0]["target_var_key"] == "active_options"
    assert node_upsert["assignments"][0]["expression"]["op"] == "sample"

    # Verify flow update and compiler generation
    from app.modules.graphs.engine import DirectLangGraphCompiler
    from app.modules.graphs.operations import GraphUpdateInput, apply_graph_update
    from app.modules.graphs.schemas import GraphFlowData

    initial_flow = GraphFlowData.model_validate(state["initial_flow_data"])
    updated_flow = apply_graph_update(initial_flow, GraphUpdateInput(**ops))
    compiler = DirectLangGraphCompiler(updated_flow)
    compiled_code = compiler.compile()
    assert "random.sample" in compiled_code


def test_translate_plan_node_delete_switch_branch() -> None:
    """Test that delete_entity cleanly removes a branch from switch node branches."""
    state: CopilotState = {
        "trace_id": "test_trace",
        "tool_calls": [
            {
                "name": "delete_entity",
                "arguments": '{"kind": "switch_branch", "id": "FiftyFifty", "parent_id": "lifeline_switch"}',
            }
        ],
        "initial_flow_data": {
            "nodes": [
                {
                    "id": "lifeline_switch",
                    "node_type": "LOGICAL_SWITCH",
                    "branches": [
                        {"id": "lifeline_switch_fiftyfifty", "label": "FiftyFifty", "expression": True},
                        {"id": "lifeline_switch_default", "label": "Default", "expression": True},
                    ],
                }
            ],
            "edges": [
                {"source": "lifeline_switch", "source_handle": "lifeline_switch_fiftyfifty", "target": "end"},
                {"source": "lifeline_switch", "source_handle": "lifeline_switch_default", "target": "end"},
            ],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]
    switch_upsert = next(n for n in ops["nodes"]["upsert"] if n["id"] == "lifeline_switch")
    assert "FiftyFifty" not in switch_upsert["branches"]
    assert "Default" in switch_upsert["branches"]


def test_format_condition_yaml_canonical_and_not() -> None:
    from app.modules.graphs.engine.serializer import format_condition_yaml

    # NOT condition
    not_expr = {"NOT": {"score": {"equals": 0}}}
    assert (
        format_condition_yaml(not_expr)
        == '{ logic: "NOT", conditions: [{ var: "score", op: "equals", literal_value: 0 }] }'
    )

    # Canonical operators
    ne_expr = {"score": {"not_equals": 5}}
    assert format_condition_yaml(ne_expr) == '{ var: "score", op: "not_equals", literal_value: 5 }'

    in_expr = {"choice": {"in": ["A", "B"]}}
    assert format_condition_yaml(in_expr) == '{ var: "choice", op: "in", literal_value: ["A", "B"] }'


async def test_copilot_workflow_self_correction_retry_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the Copilot StateGraph routes validation errors back through planner for self-correction."""
    from typing import Any, cast

    from langchain_core.runnables import RunnableConfig

    from app.modules.copilot.state import CopilotState
    from app.modules.copilot.workflow import copilot_graph

    call_count = 0

    # Mock generate_plan to fail on first turn (orphan node) and correct on second turn
    async def mock_generate_plan(
        client: Any,
        trace_id: str,
        graph_id: str,
        messages: list[dict[str, Any]],
        initial_flow: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Turn 1: Invalid orphan node (will fail dry-run validation)
            return [
                {
                    "name": "upsert_node",
                    "arguments": (
                        '{"id": "orphan_step", "node_type": "LOGICAL_ASSIGNER", '
                        '"config": {"assignments": [{"target_var_key": "x", "assignment": {"value": 1}}]}, '
                        '"target": "end"}'
                    ),
                }
            ]
        else:
            # Turn 2: Corrected with proper start entrypoint
            return [
                {
                    "name": "upsert_variable",
                    "arguments": '{"key": "x", "type": "number", "default_value": 0, "description": null}',
                },
                {
                    "name": "upsert_node",
                    "arguments": (
                        '{"id": "first_step", "node_type": "LOGICAL_ASSIGNER", '
                        '"config": {"assignments": [{"target_var_key": "x", "assignment": {"value": 1}}]}, '
                        '"target": "end"}'
                    ),
                },
                {"name": "upsert_node", "arguments": '{"id": "start", "target": "first_step"}'},
            ]

    monkeypatch.setattr("app.modules.copilot.workflow.generate_plan", mock_generate_plan)
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")

    initial_state: CopilotState = {
        "trace_id": "test_retry_trace",
        "graph_id": "test_graph_retry",
        "user_prompt": "Add a first step initializing x to 1",
        "serialized_state": "Flow:\n  start -> end",
        "initial_flow_data": {
            "nodes": [{"id": "start", "node_type": "START"}, {"id": "end", "node_type": "END"}],
            "edges": [],
            "state": [],
        },
        "tool_calls": None,
        "operations": None,
        "validation_error": None,
        "applied": None,
        "retry_count": 0,
        "messages": None,
    }

    config = cast(RunnableConfig, {"configurable": {"thread_id": "test_thread_retry"}})
    final_state = await copilot_graph.ainvoke(cast(Any, initial_state), config)

    # Verify that planner was called twice and second attempt succeeded
    assert call_count == 2
    assert final_state.get("applied") is True
    assert final_state.get("validation_error") is None
    assert final_state.get("retry_count") == 1
    assert final_state.get("operations") is not None


def test_validation_node_unconnected_switch_slot_error() -> None:
    from app.modules.copilot.workflow import validation_node

    state: CopilotState = {
        "trace_id": "test_trace_slot",
        "tool_calls": [
            {
                "name": "upsert_variable",
                "arguments": '{"key": "score", "type": "number", "default_value": 0, "description": null}',
            },
        ],
        "initial_flow_data": {
            "nodes": [
                {"id": "start", "node_type": "START"},
                {
                    "id": "switch_1",
                    "node_type": "LOGICAL_SWITCH",
                    "branches": [
                        {"id": "switch_1_opt_a", "label": "opt_a", "expression": True},
                        {"id": "switch_1_opt_b", "label": "opt_b", "expression": True},
                    ],
                },
                {"id": "end", "node_type": "END"},
            ],
            "edges": [
                {"source": "start", "target": "switch_1"},
                {"source": "switch_1", "source_handle": "switch_1_opt_a", "target": "end"},
                # Note: switch_1_opt_b is missing an outgoing edge
            ],
            "state": [],
        },
    }

    translated = translate_plan_node(state)
    assert translated["operations"] is not None

    validation_state: CopilotState = {
        **state,
        "operations": translated["operations"],
        "retry_count": 0,
    }
    result = validation_node(validation_state)
    assert result["applied"] is False
    assert "not connected to any target node" in str(result["validation_error"])
    assert "[UNCONNECTED_SLOT]" in result["messages"][-1]["content"]
