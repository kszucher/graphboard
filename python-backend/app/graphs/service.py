from __future__ import annotations

import uuid
from collections.abc import Sequence
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
    from app.context import UnitOfWork


async def create_graph(
    uow: UnitOfWork,
    user_id: uuid.UUID,
    graph_name: str,
) -> uuid.UUID:
    graph = await uow.graphs.create(user_id=user_id, graph_name=graph_name)

    from app.graphs.defaults import build_default_trivia_graph_flow_data

    flow_data = build_default_trivia_graph_flow_data()
    initial_flow = flow_data.model_dump(mode="json")

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


async def get_compiled_code(uow: UnitOfWork, graph_id: uuid.UUID, version: int | None = None) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        raise ValidationError(f"Graph {graph_id} not found")

    if version is not None:
        snapshot = await uow.graph_history.get_by_sequence(graph_id, version)
    else:
        snapshot = await uow.graph_history.get_latest_snapshot(graph_id)

    if not snapshot:
        raise ValidationError(f"No version found for Graph {graph_id}")

    flow_data = GraphFlowData.model_validate(snapshot.flow_json or {})
    code = await generate_graph_code(flow_data)
    return {"code": code}


async def run_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID, version: int | None = None) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs.executor import compile_flow_with_langgraph

    if version is not None:
        snapshot = await uow.graph_history.get_by_sequence(graph_id, version)
    else:
        snapshot = await uow.graph_history.get_latest_snapshot(graph_id)

    if not snapshot:
        raise ValidationError(f"No version found for Graph {graph_id}")

    flow_data = GraphFlowData.model_validate(snapshot.flow_json or {})
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
        snapshot = await uow.graph_history.get_latest_snapshot(graph_id)
        flow_data = snapshot.flow_json if snapshot else {}
        await uow.graph_history.clear_by_graph(graph_id)
        await uow.graph_history.save_snapshot(graph_id, flow_data, 0)
        await uow.session.flush()


async def get_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID, version: int | None = None) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        raise ValidationError(f"Graph {graph_id} not found")

    if version is not None:
        snapshot = await uow.graph_history.get_by_sequence(graph_id, version)
    else:
        snapshot = await uow.graph_history.get_latest_snapshot(graph_id)

    if not snapshot:
        from app.graphs.defaults import build_default_trivia_graph_flow_data

        flow_data = build_default_trivia_graph_flow_data()
        initial_flow = flow_data.model_dump(mode="json")
        snapshot = await uow.graph_history.save_snapshot(graph_id, initial_flow, 0)
        await uow.session.flush()

    flow_data = GraphFlowData.model_validate(snapshot.flow_json or {})
    return await _prepare_response_flow(uow, graph_id, flow_data, snapshot.sequence_number)


async def _prepare_response_flow(
    uow: UnitOfWork, graph_id: uuid.UUID, flow_data: GraphFlowData, current_version: int
) -> dict:
    history_entries = await uow.graph_history.list_by_graph(graph_id)
    versions = [
        {
            "sequence_number": h.sequence_number,
            "name": f"v{h.sequence_number + 1}",
            "created_at": h.created_at,
        }
        for h in history_entries
    ]
    res = flow_data.model_dump(mode="json")
    res.update(
        {
            "versions": versions,
            "current_version": current_version,
        }
    )
    return res


async def apply_patch(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    patch: Sequence[GraphOperation],
) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import mutations
    from app.graphs.mutations import sort_operations_by_dependency

    # Mutations are always applied to the latest version
    latest_snapshot = await uow.graph_history.get_latest_snapshot(graph_id)
    if not latest_snapshot:
        raise ValidationError(f"No version found for Graph {graph_id}")

    flow_data = GraphFlowData.model_validate(latest_snapshot.flow_json or {})
    sorted_patch = sort_operations_by_dependency(patch)
    mutated = mutations.apply_patch(flow_data, sorted_patch)

    # Save as next version
    next_seq = latest_snapshot.sequence_number + 1
    updated_flow_dict = mutated.model_dump(mode="json")
    await uow.graph_history.save_snapshot(graph_id, updated_flow_dict, next_seq)
    await uow.session.flush()

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return await _prepare_response_flow(uow, graph_id, mutated, next_seq)
