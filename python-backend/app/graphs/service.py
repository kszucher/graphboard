from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from app.constants import EventName, NodeType
from app.exceptions import ValidationError
from app.graphs import operations as graph_operations
from app.graphs import topology as graph_topology
from app.graphs.compiler import generate_graph_code
from app.graphs.integrity import assert_flow_is_complete
from app.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    ConfirmNode,
    DefinerVariableSchema,
    DefinerVariableUpdates,
    EdgeRead,
    EndNode,
    ExtractNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignmentSchema,
    LogicalAssignmentUpdates,
    LogicalAssignerNode,
    NodeRead,
    RetryNode,
    ReviewNode,
    SlotRead,
    StartNode,
    SwitchNode,
    ValidateNode,
    VariableType,
)

if TYPE_CHECKING:
    from app import models
    from app.context import UnitOfWork


async def create_graph(
    uow: UnitOfWork,
    user_id: uuid.UUID,
    graph_name: str,
) -> uuid.UUID:
    graph = await uow.graphs.create(user_id=user_id, name=graph_name)

    import uuid as py_uuid

    default_nodes: list[NodeRead] = [
        StartNode(id="start"),
        LogicalAssignerNode(
            id="init_game",
            assignments=[
                LogicalAssignmentSchema(
                    id="init_score",
                    target_var_key="score",
                    value_type="number",
                    expression={"kind": "literal", "value": 0},
                ),
                LogicalAssignmentSchema(
                    id="init_more",
                    target_var_key="more_questions",
                    value_type="boolean",
                    expression={"kind": "literal", "value": True},
                ),
            ],
        ),
        SwitchNode(
            id="loop_questions",
            slots=[
                SlotRead(
                    id="loop_questions_yes",
                    raw_string="Yes",
                    expression={"kind": "stateRef", "varKey": "more_questions"},
                ),
                SlotRead(
                    id="loop_questions_no",
                    raw_string="No",
                    expression={"kind": "literal", "value": True},
                ),
            ],
        ),
        AgenticAssignerNode(
            id="gen_question",
            prompt="Generate a fun trivia question for the player.",
            agentic_inputs=[],
            agentic_outputs=["current_question"],
        ),
        InterruptNode(
            id="ask_question",
            payload_vars=["current_question"],
            resume_var="user_answer",
        ),
        ExtractNode(
            id="parse_answer",
            assignments=[
                LogicalAssignmentSchema(
                    id="parse_extract",
                    target_var_key="parsed_answer",
                    value_type="string",
                    expression={"kind": "stateRef", "varKey": "user_answer"},
                )
            ],
        ),
        RetryNode(
            id="parse_retry",
            max_attempts=3,
            valid_expression={
                "kind": "binaryOp",
                "op": "!=",
                "left": {"kind": "stateRef", "varKey": "parsed_answer"},
                "right": {"kind": "literal", "value": ""},
            },
            slots=[
                SlotRead(id="parse_retry_valid", raw_string="valid"),
                SlotRead(id="parse_retry_retry", raw_string="retry"),
                SlotRead(id="parse_retry_exhausted", raw_string="exhausted"),
            ],
        ),
        AgenticSwitchNode(
            id="lifeline_switch",
            prompt="Determine if user wants to submit answer or use a lifeline from user_answer: '{user_answer}'.",
            agentic_inputs=["user_answer"],
            slots=[
                SlotRead(id="lifeline_switch_submit", raw_string="Submit"),
                SlotRead(id="lifeline_switch_lifeline", raw_string="Lifeline"),
            ],
        ),
        AgenticSwitchNode(
            id="choose_lifeline",
            prompt="Determine which lifeline user selected.",
            agentic_inputs=["user_answer"],
            slots=[
                SlotRead(id="choose_lifeline_fifty", raw_string="50-50"),
                SlotRead(id="choose_lifeline_audience", raw_string="Audience"),
                SlotRead(id="choose_lifeline_phone", raw_string="Phone"),
            ],
        ),
        LogicalAssignerNode(id="fifty_fifty", assignments=[]),
        AgenticAssignerNode(
            id="audience_votes",
            prompt="Poll audience for advice.",
            agentic_inputs=["current_question"],
            agentic_outputs=[],
        ),
        AgenticAssignerNode(
            id="phone_advice",
            prompt="Call a friend for advice.",
            agentic_inputs=["current_question"],
            agentic_outputs=[],
        ),
        ConfirmNode(
            id="confirm_answer",
            payload_vars=["parsed_answer"],
            slots=[
                SlotRead(id="confirm_answer_confirmed", raw_string="confirmed"),
                SlotRead(id="confirm_answer_rejected", raw_string="rejected"),
                SlotRead(id="confirm_answer_unclear", raw_string="unclear"),
            ],
        ),
        RetryNode(
            id="confirm_retry",
            max_attempts=2,
            valid_expression=None,
            slots=[
                SlotRead(id="confirm_retry_valid", raw_string="valid"),
                SlotRead(id="confirm_retry_retry", raw_string="retry"),
                SlotRead(id="confirm_retry_exhausted", raw_string="exhausted"),
            ],
        ),
        ValidateNode(
            id="validate_step",
            assignments=[
                LogicalAssignmentSchema(
                    id="validate_check",
                    target_var_key="is_correct",
                    value_type="boolean",
                    expression={
                        "kind": "binaryOp",
                        "op": "==",
                        "left": {"kind": "stateRef", "varKey": "parsed_answer"},
                        "right": {"kind": "literal", "value": "A"},
                    },
                )
            ],
        ),
        SwitchNode(
            id="result_switch",
            slots=[
                SlotRead(
                    id="result_switch_correct",
                    raw_string="correct",
                    expression={"kind": "stateRef", "varKey": "is_correct"},
                ),
                SlotRead(
                    id="result_switch_wrong",
                    raw_string="wrong",
                    expression={"kind": "literal", "value": True},
                ),
            ],
        ),
        LogicalAssignerNode(
            id="increment_score",
            assignments=[
                LogicalAssignmentSchema(
                    id="add_score",
                    target_var_key="score",
                    value_type="number",
                    expression={
                        "kind": "binaryOp",
                        "op": "+",
                        "left": {"kind": "stateRef", "varKey": "score"},
                        "right": {"kind": "literal", "value": 1},
                    },
                )
            ],
        ),
        ReviewNode(id="show_result"),
        EndNode(id="end"),
    ]

    def make_edge(
        edge_id_str: str,
        src_id: str,
        src_type: Literal["node", "slot"],
        tgt_id: str,
        tgt_type: Literal["node", "slot"] = "node",
    ) -> EdgeRead:
        return EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, edge_id_str),
            source_id=src_id,
            source_type=src_type,
            target_id=tgt_id,
            target_type=tgt_type,
        )

    default_edges = [
        make_edge("start->init_game", "start", "node", "init_game"),
        make_edge("init_game->loop_questions", "init_game", "node", "loop_questions"),
        make_edge("loop_questions_yes->gen_question", "loop_questions_yes", "slot", "gen_question"),
        make_edge("loop_questions_no->end", "loop_questions_no", "slot", "end"),
        make_edge("gen_question->ask_question", "gen_question", "node", "ask_question"),
        make_edge("ask_question->parse_answer", "ask_question", "node", "parse_answer"),
        make_edge("parse_answer->parse_retry", "parse_answer", "node", "parse_retry"),
        make_edge("parse_retry_valid->lifeline_switch", "parse_retry_valid", "slot", "lifeline_switch"),
        make_edge("parse_retry_retry->ask_question", "parse_retry_retry", "slot", "ask_question"),
        make_edge("parse_retry_exhausted->end", "parse_retry_exhausted", "slot", "end"),
        make_edge("lifeline_switch_submit->confirm_answer", "lifeline_switch_submit", "slot", "confirm_answer"),
        make_edge("lifeline_switch_lifeline->choose_lifeline", "lifeline_switch_lifeline", "slot", "choose_lifeline"),
        make_edge("choose_lifeline_fifty->fifty_fifty", "choose_lifeline_fifty", "slot", "fifty_fifty"),
        make_edge("choose_lifeline_audience->audience_votes", "choose_lifeline_audience", "slot", "audience_votes"),
        make_edge("choose_lifeline_phone->phone_advice", "choose_lifeline_phone", "slot", "phone_advice"),
        make_edge("fifty_fifty->ask_question", "fifty_fifty", "node", "ask_question"),
        make_edge("audience_votes->ask_question", "audience_votes", "node", "ask_question"),
        make_edge("phone_advice->ask_question", "phone_advice", "node", "ask_question"),
        make_edge("confirm_answer_confirmed->validate_step", "confirm_answer_confirmed", "slot", "validate_step"),
        make_edge("confirm_answer_rejected->ask_question", "confirm_answer_rejected", "slot", "ask_question"),
        make_edge("confirm_answer_unclear->confirm_retry", "confirm_answer_unclear", "slot", "confirm_retry"),
        make_edge("confirm_retry_retry->confirm_answer", "confirm_retry_retry", "slot", "confirm_answer"),
        make_edge("confirm_retry_exhausted->ask_question", "confirm_retry_exhausted", "slot", "ask_question"),
        make_edge("validate_step->result_switch", "validate_step", "node", "result_switch"),
        make_edge("result_switch_correct->increment_score", "result_switch_correct", "slot", "increment_score"),
        make_edge("result_switch_wrong->show_result", "result_switch_wrong", "slot", "show_result"),
        make_edge("increment_score->loop_questions", "increment_score", "node", "loop_questions"),
        make_edge("show_result->end", "show_result", "node", "end"),
    ]

    flow_data = GraphFlowData(
        nodes=default_nodes,
        edges=default_edges,
        state=[
            DefinerVariableSchema(id="v1", key="score", type="number", default_value=0),
            DefinerVariableSchema(id="v2", key="more_questions", type="boolean", default_value=True),
            DefinerVariableSchema(id="v3", key="current_question", type="string", default_value=""),
            DefinerVariableSchema(id="v4", key="user_answer", type="string", default_value=""),
            DefinerVariableSchema(id="v5", key="parsed_answer", type="string", default_value=""),
            DefinerVariableSchema(id="v6", key="is_correct", type="boolean", default_value=False),
        ],
    )
    initial_flow = flow_data.model_dump(mode="json")

    graph.flow_json = initial_flow
    await uow.session.flush()

    await uow.users.set_active_graph(user_id, graph.id)

    uow.emit(
        event=EventName.GRAPH_CREATED,
        graph_id=graph.id,
        payload={"graphId": graph.id},
    )
    return graph.id


async def list_graphs_by_user(uow: UnitOfWork, user_id: uuid.UUID) -> list:
    return await uow.graphs.list_by_user(user_id)


async def get_compiled_code(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")
    flow_data = GraphFlowData.model_validate(graph.flow_json or {})
    code = await generate_graph_code(flow_data)
    return {"code": code}


async def run_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs.compiler import compile_flow_with_langgraph

    flow_data = GraphFlowData.model_validate(graph.flow_json or {})
    try:
        assert_flow_is_complete(flow_data)
    except ValidationError as e:
        return {
            "variables": [],
            "error": f"Compilation/Execution failed: {e.message}",
        }

    exec_result = await compile_flow_with_langgraph(flow_data)

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return exec_result


async def reset_graph_history(uow: UnitOfWork, graph_id: uuid.UUID) -> None:
    graph = await uow.graphs.get(graph_id)
    if graph:
        flow_data = graph.flow_json or {}
        await uow.graph_history.clear_by_graph(graph_id)
        graph.current_history_sequence = 0
        await uow.graph_history.save_snapshot(graph_id, flow_data, 0)
        await uow.session.flush()


async def get_and_reset_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    flow_data = GraphFlowData.model_validate(graph.flow_json or {})

    existing_snapshot = await uow.graph_history.get_by_sequence(graph_id, 0)
    if not existing_snapshot:
        await reset_graph_history(uow, graph_id)

    return await _prepare_response_flow(uow, graph, flow_data)


async def _prepare_response_flow(uow: UnitOfWork, graph: models.Graph, flow_data: GraphFlowData) -> dict:
    next_snap = await uow.graph_history.get_by_sequence(graph.id, graph.current_history_sequence + 1)

    res = flow_data.model_dump(mode="json")
    res.update(
        {
            "can_undo": graph.current_history_sequence > 0,
            "can_redo": next_snap is not None,
        }
    )
    return res


async def _commit_state_snapshot(uow: UnitOfWork, graph: models.Graph, flow_data: GraphFlowData) -> dict:
    # Clear future history branches
    await uow.graph_history.delete_future_snapshots(graph.id, graph.current_history_sequence)

    # Convert topology to dict for database persistence (no code stored)
    updated_flow_dict = flow_data.model_dump(mode="json")

    # Increment sequence and save snapshot
    next_seq = graph.current_history_sequence + 1
    await uow.graph_history.save_snapshot(graph.id, updated_flow_dict, next_seq)

    # Update graph row
    graph.flow_json = updated_flow_dict
    graph.current_history_sequence = next_seq
    await uow.session.flush()

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return await _prepare_response_flow(uow, graph, flow_data)


async def undo_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    if graph.current_history_sequence <= 0:
        flow_data = GraphFlowData.model_validate(graph.flow_json or {})
        return await _prepare_response_flow(uow, graph, flow_data)

    prev_seq = graph.current_history_sequence - 1
    prev_snapshot = await uow.graph_history.get_by_sequence(graph.id, prev_seq)
    if not prev_snapshot:
        flow_data = GraphFlowData.model_validate(graph.flow_json or {})
        return await _prepare_response_flow(uow, graph, flow_data)

    flow_data = GraphFlowData.model_validate(prev_snapshot.flow_json)
    graph.flow_json = prev_snapshot.flow_json
    graph.current_history_sequence = prev_seq
    await uow.session.flush()

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return await _prepare_response_flow(uow, graph, flow_data)


async def redo_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    next_seq = graph.current_history_sequence + 1
    next_snapshot = await uow.graph_history.get_by_sequence(graph.id, next_seq)
    if not next_snapshot:
        flow_data = GraphFlowData.model_validate(graph.flow_json or {})
        return await _prepare_response_flow(uow, graph, flow_data)

    flow_data = GraphFlowData.model_validate(next_snapshot.flow_json)
    graph.flow_json = next_snapshot.flow_json
    graph.current_history_sequence = next_seq
    await uow.session.flush()

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return await _prepare_response_flow(uow, graph, flow_data)


# Helper orchestrator for mutations
async def _mutate_flow(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    mutate_fn: Callable[[GraphFlowData, *Any], GraphFlowData],
    *args: Any,
    **kwargs: Any,
) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    flow_data = GraphFlowData.model_validate(graph.flow_json or {})
    mutated = mutate_fn(flow_data, *args, **kwargs)
    return await _commit_state_snapshot(uow, graph, mutated)


# Node Mutations Service Layer
async def add_node(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    node_type: NodeType | str,
    connector_id: str | None = None,
    direction: str | None = None,
) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.add_node, node_type, connector_id, direction)


async def delete_node(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.delete_node, node_id)


async def shortcircuit_node(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.shortcircuit_node, node_id)


async def update_node(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    node_id: str,
    new_id: str | None = None,
    prompt: str | None = None,
    agentic_inputs: list[str] | None = None,
    agentic_outputs: list[str] | None = None,
    payload_vars: list[str] | None = None,
    resume_var: str | None = None,
    max_attempts: int | None = None,
    valid_expression: dict[str, Any] | None = None,
) -> dict:
    kwargs: dict[str, Any] = {}
    if new_id is not None:
        kwargs["new_id"] = new_id
    if prompt is not None:
        kwargs["prompt"] = prompt
    if agentic_inputs is not None:
        kwargs["agentic_inputs"] = agentic_inputs
    if agentic_outputs is not None:
        kwargs["agentic_outputs"] = agentic_outputs
    if payload_vars is not None:
        kwargs["payload_vars"] = payload_vars
    if resume_var is not None:
        kwargs["resume_var"] = resume_var
    if max_attempts is not None:
        kwargs["max_attempts"] = max_attempts
    if valid_expression is not None:
        kwargs["valid_expression"] = valid_expression

    return await _mutate_flow(
        uow,
        graph_id,
        graph_topology.update_node,
        node_id,
        **kwargs,
    )


# Slot Mutations Service Layer
async def create_slot(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str, index: int) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.create_slot, node_id, index)


async def update_slot(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    slot_id: str,
    raw_string: str | None = None,
    expression: dict[str, Any] | None = None,
) -> dict:
    if expression is not None:
        return await _mutate_flow(
            uow,
            graph_id,
            graph_operations.update_switch_expression,
            slot_id,
            raw_string=raw_string,
            expression=expression,
        )
    return await _mutate_flow(uow, graph_id, graph_topology.update_slot, slot_id, raw_string, expression)


async def delete_slot(uow: UnitOfWork, graph_id: uuid.UUID, slot_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.delete_slot, slot_id)


async def move_slot(uow: UnitOfWork, graph_id: uuid.UUID, slot_id: str, direction: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.move_slot, slot_id, direction)


# Edge Mutations Service Layer
async def delete_edge(uow: UnitOfWork, graph_id: uuid.UUID, edge_id: uuid.UUID) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.delete_edge, edge_id)


async def create_edge(
    uow: UnitOfWork, graph_id: uuid.UUID, source: str, target: str, source_handle: str, target_handle: str
) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.create_edge, source, target, source_handle, target_handle)


async def reconnect_edge(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    edge_id: uuid.UUID,
    source: str,
    target: str,
    source_handle: str,
    target_handle: str,
) -> dict:
    return await _mutate_flow(
        uow,
        graph_id,
        graph_topology.reconnect_edge,
        edge_id,
        source,
        target,
        source_handle,
        target_handle,
    )


# Definer Operations Service Layer
async def create_definer_variable(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    key: str,
    var_type: VariableType = "string",
    default_value: Any = None,
    description: str | None = None,
) -> dict:
    return await _mutate_flow(
        uow,
        graph_id,
        graph_operations.create_definer_variable,
        key,
        var_type,
        default_value,
        description,
    )


async def update_definer_variable(
    uow: UnitOfWork, graph_id: uuid.UUID, var_id: str, updates: DefinerVariableUpdates
) -> dict:
    return await _mutate_flow(uow, graph_id, graph_operations.update_definer_variable, var_id, updates)


async def delete_definer_variable(uow: UnitOfWork, graph_id: uuid.UUID, var_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_operations.delete_definer_variable, var_id)


# Logical Assigner Operations Service Layer
async def create_logical_assignment(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    node_id: str,
    target_var_key: str,
    value_type: VariableType = "string",
    value: Any = None,
    expression: dict[str, Any] | None = None,
) -> dict:
    return await _mutate_flow(
        uow,
        graph_id,
        graph_operations.create_logical_assignment,
        node_id,
        target_var_key,
        value_type,
        value,
        expression,
    )


async def update_logical_assignment(
    uow: UnitOfWork, graph_id: uuid.UUID, assignment_id: str, updates: LogicalAssignmentUpdates
) -> dict:
    return await _mutate_flow(uow, graph_id, graph_operations.update_logical_assignment, assignment_id, updates)


async def delete_logical_assignment(uow: UnitOfWork, graph_id: uuid.UUID, assignment_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_operations.delete_logical_assignment, assignment_id)
