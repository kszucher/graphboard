from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.constants import EventName, NodeType
from app.exceptions import ValidationError
from app.graphs import operations as graph_operations
from app.graphs import topology as graph_topology
from app.graphs.compiler import generate_graph_code
from app.graphs.integrity import assert_flow_is_complete
from app.graphs.schemas import (
    DefinerVariableUpdates,
    GraphFlowData,
    LogicalAssignmentUpdates,
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

    from app.graphs.defaults import build_default_trivia_graph_flow_data

    flow_data = build_default_trivia_graph_flow_data()
    initial_flow = flow_data.model_dump(mode="json")

    graph.flow_json = initial_flow
    graph.current_history_sequence = 0
    await uow.graph_history.save_snapshot(graph.id, initial_flow, 0)
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
        await uow.graph_history.save_snapshot(graph_id, graph.flow_json or {}, 0)
        await uow.session.flush()

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
