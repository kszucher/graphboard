import pytest

from app.core.exceptions import ValidationError
from app.modules.copilot.workflow import translate_plan_node


def test_translate_plan_node_upsert_node_polymorphic() -> None:
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
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
            ]
        },
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
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
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
            ]
        },
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
    from app.modules.graphs.schemas import GraphFlowData

    initial_flow = GraphFlowData.model_validate(
        {
            **state["initial_flow_data"],
            "state": [{"id": "v1", "key": "user_answer", "type": "string", "default_value": ""}],
        }
    )
    updated_flow = apply_graph_update(initial_flow, GraphUpdateInput(**ops))
    assert len(updated_flow.nodes) == 4
    choose_node = next(n for n in updated_flow.nodes if n.id == "choose_lifeline")
    assert len(choose_node.branches) == 2


def test_translate_plan_node_switch_with_closed_conditions() -> None:
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
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
            ]
        },
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
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
            "tool_calls": [
                {"name": "delete_entity", "arguments": '{"kind": "variable", "id": "old_var"}'},
                {"name": "delete_entity", "arguments": '{"kind": "node", "id": "dead_node"}'},
                {"name": "rename_entity", "arguments": '{"kind": "variable", "old_name": "v1", "new_name": "v2"}'},
                {"name": "rename_entity", "arguments": '{"kind": "node", "old_name": "n1", "new_name": "n2"}'},
            ]
        },
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
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
            "tool_calls": [
                {
                    "name": "upsert_node",
                    "arguments": '{"id": "assigner_a", "target": "end"}',
                },
            ]
        },
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


def test_translate_plan_node_orphan_error() -> None:
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
            "tool_calls": [
                {
                    "name": "upsert_node",
                    "arguments": (
                        '{"id": "orphan_assigner", "node_type": "LOGICAL_ASSIGNER", '
                        '"config": {"assignments": [{"target_var_key": "x", "assignment": {"value": 1}}]}, '
                        '"target": "end"}'
                    ),
                }
            ]
        },
        "initial_flow_data": {
            "nodes": [{"id": "end", "node_type": "LOGICAL_SWITCH", "branches": {}}],
            "edges": [],
            "state": [],
        },
    }

    with pytest.raises(ValidationError, match="Orphan node detected"):
        translate_plan_node(state)


def test_translate_plan_node_orthogonal_collection_expressions() -> None:
    """Test translating a node with orthogonal collection expressions like sample and format."""
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
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
            ]
        },
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
    from app.modules.graphs.compiler import DirectLangGraphCompiler
    from app.modules.graphs.operations import GraphUpdateInput, apply_graph_update
    from app.modules.graphs.schemas import GraphFlowData

    initial_flow = GraphFlowData.model_validate(state["initial_flow_data"])
    updated_flow = apply_graph_update(initial_flow, GraphUpdateInput(**ops))
    compiler = DirectLangGraphCompiler(updated_flow)
    compiled_code = compiler.compile()
    assert "random.sample" in compiled_code
