from typing import Any, cast

import pytest
from langchain_core.runnables import RunnableConfig

from app.core.exceptions import ValidationError
from app.modules.copilot import planner_schemas
from app.modules.copilot.state import CopilotState
from app.modules.copilot.translator import translate_plan_node
from app.modules.copilot.workflow import copilot_graph, validation_node
from app.modules.graphs.engine import DirectLangGraphCompiler
from app.modules.graphs.operations import apply_graph_update
from app.modules.graphs.schemas import AgenticSwitchNode, GraphFlowData


def test_translate_plan_node_upsert_node_polymorphic() -> None:
    plan = planner_schemas.ApplyGraphPlan(
        variables=[planner_schemas.UpsertVariable(key="score", type="number", default_value=0)],
        nodes=[
            planner_schemas.UpsertNode(
                id="new_assigner",
                node_type="LOGICAL_ASSIGNER",
                config=planner_schemas.LogicalAssignerConfig(
                    assignments=[
                        planner_schemas.LogicalAssignment(
                            target_var_key="score",
                            expression="10",
                        )
                    ]
                ),
                target="end",
            ),
            planner_schemas.UpsertNode(id="start", target="new_assigner"),
        ],
    )

    state: CopilotState = {
        "trace_id": "test_trace",
        "plan": plan,
        "initial_flow_data": {
            "nodes": [{"id": "end", "node_type": "LOGICAL_SWITCH", "branches": {}}],
            "edges": [],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]
    assert ops is not None
    assert ops.start_target == "new_assigner"
    assert ops.variables is not None
    assert len(ops.variables.upsert) == 1
    assert ops.variables.upsert[0].key == "score"
    assert ops.nodes is not None
    assert len(ops.nodes.upsert) == 1

    new_assigner_upsert = next(n for n in ops.nodes.upsert if n.id == "new_assigner")
    assert new_assigner_upsert.target == "end"
    assert new_assigner_upsert.assignments is not None
    assert new_assigner_upsert.assignments[0].target_var_key == "score"
    assert new_assigner_upsert.assignments[0].expression == "10"


def test_translate_plan_node_upsert_switch_branch_surgical_delta() -> None:
    """Test surgically patching a single branch on an existing switch without overwriting other branches."""
    plan = planner_schemas.ApplyGraphPlan(
        nodes=[
            planner_schemas.UpsertNode(
                id="phone_node",
                node_type="AGENTIC_ASSIGNER",
                config=planner_schemas.AgenticAssignerConfig(
                    prompt="Call phone...",
                    inputs=[],
                    outputs=[],
                ),
                target="end",
            )
        ],
        switch_branches=[
            planner_schemas.UpsertSwitchBranch(
                node_id="choose_lifeline",
                label="Phone",
                target="phone_node",
                condition=None,
            )
        ],
    )

    state: CopilotState = {
        "trace_id": "test_trace",
        "plan": plan,
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
    assert ops is not None
    assert ops.nodes is not None

    choose_upsert = next(n for n in ops.nodes.upsert if n.id == "choose_lifeline")
    assert choose_upsert.branches is not None
    assert choose_upsert.branches["Audience"].target == "audience_votes"
    assert choose_upsert.branches["Phone"].target == "phone_node"
    assert choose_upsert.agentic_input == "user_answer"

    # Ensure operations pass apply_graph_update without error
    initial_flow = GraphFlowData.model_validate(
        {
            **state["initial_flow_data"],
            "state": [{"id": "v1", "key": "user_answer", "type": "string", "default_value": ""}],
        }
    )
    updated_flow = apply_graph_update(initial_flow, ops)
    assert len(updated_flow.nodes) == 4
    choose_node = next(n for n in updated_flow.nodes if n.id == "choose_lifeline")
    assert isinstance(choose_node, AgenticSwitchNode)
    assert len(choose_node.branches) == 2


def test_translate_plan_node_switch_with_conditions() -> None:
    plan = planner_schemas.ApplyGraphPlan(
        nodes=[
            planner_schemas.UpsertNode(
                id="switch_node",
                node_type="LOGICAL_SWITCH",
                config=planner_schemas.LogicalSwitchConfig(
                    branches=[
                        planner_schemas.LogicalBranch(
                            label="Yes",
                            condition="score >= 10",
                            target="end",
                        ),
                        planner_schemas.LogicalBranch(label="No", condition=None, target="end"),
                    ]
                ),
            ),
            planner_schemas.UpsertNode(id="start", target="switch_node"),
        ],
        switch_branches=[
            planner_schemas.UpsertSwitchBranch(node_id="switch_node", label="No", target="end", condition=None)
        ],
    )

    state: CopilotState = {
        "trace_id": "test_trace",
        "plan": plan,
        "initial_flow_data": {
            "nodes": [{"id": "end", "node_type": "LOGICAL_ASSIGNER", "assignments": []}],
            "edges": [],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]
    assert ops is not None
    assert ops.start_target == "switch_node"
    assert ops.nodes is not None
    switch_upsert = next(n for n in ops.nodes.upsert if n.id == "switch_node")
    assert switch_upsert.branches is not None
    assert switch_upsert.branches["Yes"].target == "end"
    assert switch_upsert.branches["Yes"].expression == "score >= 10"
    assert switch_upsert.branches["No"].target == "end"


def test_translate_plan_node_delete_and_rename_entity() -> None:
    plan = planner_schemas.ApplyGraphPlan(
        deletions=[
            planner_schemas.DeleteEntity(kind="variable", id="old_var"),
            planner_schemas.DeleteEntity(kind="node", id="dead_node"),
        ],
        renames=[
            planner_schemas.RenameEntity(kind="variable", old_name="v1", new_name="v2"),
            planner_schemas.RenameEntity(kind="node", old_name="n1", new_name="n2"),
        ],
    )

    state: CopilotState = {
        "trace_id": "test_trace",
        "plan": plan,
        "initial_flow_data": {
            "nodes": [{"id": "start", "node_type": "START"}],
            "edges": [],
            "state": [],
        },
    }

    result = translate_plan_node(state)
    ops = result["operations"]
    assert ops is not None
    assert ops.variables is not None
    assert "old_var" in ops.variables.delete
    assert ops.nodes is not None
    assert "dead_node" in ops.nodes.delete
    assert ops.rename_variables == [{"old_key": "v1", "new_key": "v2"}] or [
        r.model_dump() for r in ops.rename_variables or []
    ] == [{"old_key": "v1", "new_key": "v2"}]
    assert ops.rename_nodes == [{"old_key": "n1", "new_key": "n2"}] or [
        r.model_dump() for r in ops.rename_nodes or []
    ] == [{"old_key": "n1", "new_key": "n2"}]


def test_translate_plan_node_partial_retargeting() -> None:
    """Test partial retargeting of existing node without re-specifying config."""
    plan = planner_schemas.ApplyGraphPlan(nodes=[planner_schemas.UpsertNode(id="assigner_a", target="end")])

    state: CopilotState = {
        "trace_id": "test_trace",
        "plan": plan,
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
    assert ops is not None
    assert ops.nodes is not None
    assigner_upsert = next(n for n in ops.nodes.upsert if n.id == "assigner_a")
    assert assigner_upsert.target == "end"


def test_validation_node_unreachable_node_error() -> None:
    plan = planner_schemas.ApplyGraphPlan(
        nodes=[
            planner_schemas.UpsertNode(
                id="orphan_assigner",
                node_type="LOGICAL_ASSIGNER",
                config=planner_schemas.LogicalAssignerConfig(
                    assignments=[
                        planner_schemas.LogicalAssignment(
                            target_var_key="x",
                            expression="1",
                        )
                    ]
                ),
                target="end",
            )
        ]
    )

    state: CopilotState = {
        "trace_id": "test_trace",
        "plan": plan,
        "initial_flow_data": {
            "nodes": [
                {"id": "start", "node_type": "START"},
                {"id": "end", "node_type": "END"},
            ],
            "edges": [
                {"source": "start", "target": "end"},
            ],
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


def test_translate_plan_node_delete_switch_branch() -> None:
    """Test that delete_entity cleanly removes a branch from switch node branches."""
    plan = planner_schemas.ApplyGraphPlan(
        deletions=[
            planner_schemas.DeleteEntity(
                kind="switch_branch",
                id="FiftyFifty",
                parent_id="lifeline_switch",
            )
        ]
    )

    state: CopilotState = {
        "trace_id": "test_trace",
        "plan": plan,
        "initial_flow_data": {
            "nodes": [
                {
                    "id": "lifeline_switch",
                    "node_type": "LOGICAL_SWITCH",
                    "branches": [
                        {"id": "lifeline_switch_fiftyfifty", "label": "FiftyFifty", "expression": "True"},
                        {"id": "lifeline_switch_default", "label": "Default", "expression": "True"},
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
    assert ops is not None
    assert ops.nodes is not None
    switch_upsert = next(n for n in ops.nodes.upsert if n.id == "lifeline_switch")
    assert switch_upsert.branches is not None
    assert "FiftyFifty" not in switch_upsert.branches
    assert "Default" in switch_upsert.branches


async def test_copilot_workflow_self_correction_retry_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the Copilot StateGraph routes validation errors back through planner for self-correction."""
    call_count = 0

    async def mock_generate_plan(
        client: Any,
        trace_id: str,
        graph_id: str,
        messages: list[dict[str, Any]],
        initial_flow: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> planner_schemas.ApplyGraphPlan:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Turn 1: Invalid orphan node (will fail dry-run validation)
            return planner_schemas.ApplyGraphPlan(
                nodes=[
                    planner_schemas.UpsertNode(
                        id="orphan_step",
                        node_type="LOGICAL_ASSIGNER",
                        config=planner_schemas.LogicalAssignerConfig(
                            assignments=[
                                planner_schemas.LogicalAssignment(
                                    target_var_key="x",
                                    expression="1",
                                )
                            ]
                        ),
                        target="end",
                    )
                ]
            )
        else:
            # Turn 2: Corrected with proper start entrypoint and variable declaration
            return planner_schemas.ApplyGraphPlan(
                variables=[planner_schemas.UpsertVariable(key="x", type="number", default_value=0)],
                nodes=[
                    planner_schemas.UpsertNode(
                        id="first_step",
                        node_type="LOGICAL_ASSIGNER",
                        config=planner_schemas.LogicalAssignerConfig(
                            assignments=[
                                planner_schemas.LogicalAssignment(
                                    target_var_key="x",
                                    expression="1",
                                )
                            ]
                        ),
                        target="end",
                    ),
                    planner_schemas.UpsertNode(id="start", target="first_step"),
                ],
            )

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
        "plan": None,
        "operations": None,
        "validation_error": None,
        "applied": None,
        "retry_count": 0,
        "messages": None,
    }

    config = cast(RunnableConfig, {"configurable": {"thread_id": "test_thread_retry"}})
    final_state = await copilot_graph.ainvoke(cast(Any, initial_state), config)

    assert call_count == 2
    assert final_state.get("applied") is True
    assert final_state.get("validation_error") is None
    assert final_state.get("retry_count") == 1
    assert final_state.get("operations") is not None


async def test_copilot_workflow_planner_node_deserialization_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that if generate_plan raises a ValidationError during tool-call parsing, it routes to retry."""
    call_count = 0

    async def mock_generate_plan(
        client: Any,
        trace_id: str,
        graph_id: str,
        messages: list[dict[str, Any]],
        initial_flow: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> planner_schemas.ApplyGraphPlan:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValidationError("1 validation error for ApplyGraphPlan\nnodes.0.config: field required")
        return planner_schemas.ApplyGraphPlan(
            variables=[planner_schemas.UpsertVariable(key="x", type="number", default_value=0)],
            nodes=[
                planner_schemas.UpsertNode(
                    id="first_step",
                    node_type="LOGICAL_ASSIGNER",
                    config=planner_schemas.LogicalAssignerConfig(
                        assignments=[
                            planner_schemas.LogicalAssignment(
                                target_var_key="x",
                                expression="1",
                            )
                        ]
                    ),
                    target="end",
                ),
                planner_schemas.UpsertNode(id="start", target="first_step"),
            ],
        )

    monkeypatch.setattr("app.modules.copilot.workflow.generate_plan", mock_generate_plan)
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")

    initial_state: CopilotState = {
        "trace_id": "test_retry_deserialization",
        "graph_id": "test_graph_deserialization",
        "user_prompt": "Add a first step",
        "serialized_state": "Flow:\n  start -> end",
        "initial_flow_data": {
            "nodes": [{"id": "start", "node_type": "START"}, {"id": "end", "node_type": "END"}],
            "edges": [],
            "state": [],
        },
        "plan": None,
        "operations": None,
        "validation_error": None,
        "applied": None,
        "retry_count": 0,
        "messages": None,
    }

    config = cast(RunnableConfig, {"configurable": {"thread_id": "test_thread_deserialization"}})
    final_state = await copilot_graph.ainvoke(cast(Any, initial_state), config)

    assert call_count == 2
    assert final_state.get("applied") is True
    assert final_state.get("retry_count") == 1


def test_validation_node_unconnected_switch_slot_error() -> None:
    plan = planner_schemas.ApplyGraphPlan(
        variables=[planner_schemas.UpsertVariable(key="score", type="number", default_value=0)]
    )

    state: CopilotState = {
        "trace_id": "test_trace_slot",
        "plan": plan,
        "initial_flow_data": {
            "nodes": [
                {"id": "start", "node_type": "START"},
                {
                    "id": "switch_1",
                    "node_type": "LOGICAL_SWITCH",
                    "branches": [
                        {"id": "switch_1_opt_a", "label": "opt_a", "expression": "score > 10"},
                        {"id": "switch_1_opt_b", "label": "opt_b", "expression": None},
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


async def test_copilot_workflow_custom_model_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that custom model selection is received by planner_node and passed to generate_plan."""
    captured_model: str | None = None

    async def mock_generate_plan(
        client: Any,
        trace_id: str,
        graph_id: str,
        messages: list[dict[str, Any]],
        initial_flow: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> planner_schemas.ApplyGraphPlan:
        nonlocal captured_model
        captured_model = model
        return planner_schemas.ApplyGraphPlan(
            variables=[planner_schemas.UpsertVariable(key="x", type="number", default_value=0)],
            nodes=[
                planner_schemas.UpsertNode(
                    id="first_step",
                    node_type="LOGICAL_ASSIGNER",
                    config=planner_schemas.LogicalAssignerConfig(
                        assignments=[
                            planner_schemas.LogicalAssignment(
                                target_var_key="x",
                                expression="1",
                            )
                        ]
                    ),
                    target="end",
                ),
                planner_schemas.UpsertNode(id="start", target="first_step"),
            ],
        )

    monkeypatch.setattr("app.modules.copilot.workflow.generate_plan", mock_generate_plan)
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")

    initial_state: CopilotState = {
        "trace_id": "test_model_trace",
        "graph_id": "test_graph_model",
        "model": "gemini-3.5-flash-lite",
        "user_prompt": "Set x to 1",
        "serialized_state": "Flow:\n  start -> end",
        "initial_flow_data": {
            "nodes": [{"id": "start", "node_type": "START"}, {"id": "end", "node_type": "END"}],
            "edges": [],
            "state": [],
        },
        "plan": None,
        "operations": None,
        "validation_error": None,
        "applied": None,
        "retry_count": 0,
        "messages": None,
    }

    config = cast(RunnableConfig, {"configurable": {"thread_id": "test_thread_model"}})
    final_state = await copilot_graph.ainvoke(cast(Any, initial_state), config)

    assert captured_model == "gemini-3.5-flash-lite"
    assert final_state.get("applied") is True
