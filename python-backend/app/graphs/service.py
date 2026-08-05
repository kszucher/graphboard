from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.constants import EventName
from app.exceptions import ValidationError
from app.graphs.compiler import generate_graph_code
from app.graphs.integrity import assert_flow_is_complete
from app.graphs.schemas import (
    GraphFlowData,
    GraphOperation,
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


async def apply_patch(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    patch: list[GraphOperation],
) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import mutations

    flow_data = GraphFlowData.model_validate(graph.flow_json or {})
    mutated = mutations.apply_patch(flow_data, patch)
    return await _commit_state_snapshot(uow, graph, mutated)
