import pytest

from app.core.exceptions import ValidationError
from app.modules.copilot.workflow import translate_plan_node


def test_translate_plan_node_success() -> None:
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
            "tool_calls": [
                {
                    "name": "upsert_variable",
                    "arguments": '{"key": "score", "type": "number", "default_value": 0, "description": null}',
                },
                {"name": "upsert_logical_assigner", "arguments": '{"id": "new_assigner", "assignments": []}'},
                {"name": "connect", "arguments": '{"source": "new_assigner", "target": "end"}'},
                {"name": "connect", "arguments": '{"source": "start", "target": "new_assigner"}'},
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

    # Check that new_assigner was assigned target="end"
    new_assigner_upsert = next(n for n in ops["nodes"]["upsert"] if n["id"] == "new_assigner")
    assert new_assigner_upsert["target"] == "end"


def test_translate_plan_node_switch_connect_and_disconnect() -> None:
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
            "tool_calls": [
                {
                    "name": "upsert_logical_switch",
                    "arguments": '{"id": "switch_node", "branches": {"Yes": null, "No": null}}',
                },
                {"name": "connect", "arguments": '{"source": "start", "target": "switch_node"}'},
                {"name": "connect", "arguments": '{"source": "switch_node", "branch": "Yes", "target": "end"}'},
                {"name": "disconnect", "arguments": '{"source": "switch_node", "branch": "No"}'},
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
    assert switch_upsert["branches"]["No"]["target"] == ""


def test_translate_plan_node_switch_missing_branch_error() -> None:
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
            "tool_calls": [
                {
                    "name": "upsert_logical_switch",
                    "arguments": '{"id": "switch_node", "branches": {"Yes": null}}',
                },
                {"name": "connect", "arguments": '{"source": "start", "target": "switch_node"}'},
                {"name": "connect", "arguments": '{"source": "switch_node", "target": "end"}'},
            ]
        },
        "initial_flow_data": {
            "nodes": [{"id": "end", "node_type": "LOGICAL_ASSIGNER", "assignments": []}],
            "edges": [],
            "state": [],
        },
    }

    with pytest.raises(ValidationError, match="without specifying a branch label"):
        translate_plan_node(state)


def test_translate_plan_node_linear_with_branch_error() -> None:
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
            "tool_calls": [
                {"name": "upsert_logical_assigner", "arguments": '{"id": "assigner", "assignments": []}'},
                {"name": "connect", "arguments": '{"source": "start", "target": "assigner"}'},
                {"name": "connect", "arguments": '{"source": "assigner", "branch": "Yes", "target": "end"}'},
            ]
        },
        "initial_flow_data": {
            "nodes": [{"id": "end", "node_type": "LOGICAL_ASSIGNER", "assignments": []}],
            "edges": [],
            "state": [],
        },
    }

    with pytest.raises(ValidationError, match="Cannot specify branch 'Yes' for linear node"):
        translate_plan_node(state)


def test_translate_plan_node_orphan_error() -> None:
    state = {
        "trace_id": "test_trace",
        "agent_checklist": {
            "tool_calls": [
                {"name": "upsert_logical_assigner", "arguments": '{"id": "orphan_assigner", "assignments": []}'}
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
