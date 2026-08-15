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
                {"name": "upsert_linear_edge", "arguments": '{"source": "new_assigner", "target": "end"}'},
                {"name": "set_start_target", "arguments": '{"target": "new_assigner"}'},
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
