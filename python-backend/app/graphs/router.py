import uuid
from typing import Any

from fastapi import APIRouter, Depends, status

from app.context import UnitOfWork
from app.db import get_uow
from app.graphs import service as graph_service
from app.graphs.schemas import (
    EdgeCreateRequest,
    EdgeReconnectRequest,
    GraphCodeRead,
    GraphCreate,
    GraphFlowRead,
    GraphRead,
    NodeCreateRequest,
    NodeUpdateRequest,
    SlotCreateRequest,
    SlotMoveRequest,
    SlotUpdateRequest,
)

router = APIRouter(prefix="/graphs", tags=["graphs"])


@router.post("/", response_model=uuid.UUID, status_code=status.HTTP_201_CREATED)
async def create_graph(payload: GraphCreate, uow: UnitOfWork = Depends(get_uow)) -> uuid.UUID:
    async with uow:
        graph_id = await graph_service.create_graph(uow, payload.user_id, payload.graph_name)
    return graph_id


@router.get("/user/{user_id}", response_model=list[GraphRead])
async def list_graphs(user_id: uuid.UUID, uow: UnitOfWork = Depends(get_uow)) -> list[GraphRead]:
    graphs = await graph_service.list_graphs_by_user(uow, user_id)
    return [GraphRead.model_validate(g) for g in graphs]


@router.get("/{graph_id}/flow", response_model=GraphFlowRead)
async def get_graph_flow(graph_id: uuid.UUID, uow: UnitOfWork = Depends(get_uow)) -> GraphFlowRead:
    async with uow:
        flow = await graph_service.get_and_reset_graph_flow(uow, graph_id)

    return GraphFlowRead.model_validate(flow)


@router.get("/{graph_id}/code", response_model=GraphCodeRead)
async def get_graph_code_endpoint(graph_id: uuid.UUID, uow: UnitOfWork = Depends(get_uow)) -> GraphCodeRead:
    code_data = await graph_service.get_compiled_code(uow, graph_id)
    return GraphCodeRead.model_validate(code_data)


@router.post("/{graph_id}/run", response_model=dict[str, Any])
async def run_graph(graph_id: uuid.UUID, uow: UnitOfWork = Depends(get_uow)) -> dict[str, Any]:
    async with uow:
        flow_data = await graph_service.run_graph_flow(uow, graph_id)
    return {"variables": flow_data.get("variables", [])}


@router.post("/{graph_id}/history/undo", response_model=GraphFlowRead)
async def undo_graph_flow_endpoint(graph_id: uuid.UUID, uow: UnitOfWork = Depends(get_uow)) -> GraphFlowRead:
    async with uow:
        flow = await graph_service.undo_graph_flow(uow, graph_id)
    return GraphFlowRead.model_validate(flow)


@router.post("/{graph_id}/history/redo", response_model=GraphFlowRead)
async def redo_graph_flow_endpoint(graph_id: uuid.UUID, uow: UnitOfWork = Depends(get_uow)) -> GraphFlowRead:
    async with uow:
        flow = await graph_service.redo_graph_flow(uow, graph_id)
    return GraphFlowRead.model_validate(flow)


# Node REST API
@router.post("/{graph_id}/nodes", response_model=GraphFlowRead)
async def add_node_endpoint(
    graph_id: uuid.UUID, payload: NodeCreateRequest, uow: UnitOfWork = Depends(get_uow)
) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.add_node(
            uow, graph_id, payload.node_type, payload.connector_id, payload.direction
        )
    return GraphFlowRead.model_validate(updated_flow)


@router.delete("/{graph_id}/nodes/{node_id}", response_model=GraphFlowRead)
async def delete_node_endpoint(graph_id: uuid.UUID, node_id: str, uow: UnitOfWork = Depends(get_uow)) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.delete_node(uow, graph_id, node_id)
    return GraphFlowRead.model_validate(updated_flow)


@router.post("/{graph_id}/nodes/{node_id}/shortcircuit", response_model=GraphFlowRead)
async def shortcircuit_node_endpoint(
    graph_id: uuid.UUID, node_id: str, uow: UnitOfWork = Depends(get_uow)
) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.shortcircuit_node(uow, graph_id, node_id)
    return GraphFlowRead.model_validate(updated_flow)


@router.patch("/{graph_id}/nodes/{node_id}", response_model=GraphFlowRead)
async def update_node_endpoint(
    graph_id: uuid.UUID, node_id: str, payload: NodeUpdateRequest, uow: UnitOfWork = Depends(get_uow)
) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.update_node(
            uow,
            graph_id,
            node_id,
            new_id=payload.new_id,
            prompt=payload.prompt,
            agentic_inputs=payload.agentic_inputs,
            agentic_input=payload.agentic_input,
            agentic_outputs=payload.agentic_outputs,
            payload_vars=payload.payload_vars,
            resume_var=payload.resume_var,
        )
    return GraphFlowRead.model_validate(updated_flow)


# Slots REST API
@router.post("/{graph_id}/nodes/{node_id}/slots", response_model=GraphFlowRead)
async def create_slot_endpoint(
    graph_id: uuid.UUID, node_id: str, payload: SlotCreateRequest, uow: UnitOfWork = Depends(get_uow)
) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.create_slot(uow, graph_id, node_id, payload.index)
    return GraphFlowRead.model_validate(updated_flow)


@router.patch("/{graph_id}/slots/{slot_id}", response_model=GraphFlowRead)
async def update_slot_endpoint(
    graph_id: uuid.UUID, slot_id: str, payload: SlotUpdateRequest, uow: UnitOfWork = Depends(get_uow)
) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.update_slot(uow, graph_id, slot_id, payload.raw_string, payload.expression)
    return GraphFlowRead.model_validate(updated_flow)


@router.delete("/{graph_id}/slots/{slot_id}", response_model=GraphFlowRead)
async def delete_slot_endpoint(graph_id: uuid.UUID, slot_id: str, uow: UnitOfWork = Depends(get_uow)) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.delete_slot(uow, graph_id, slot_id)
    return GraphFlowRead.model_validate(updated_flow)


@router.post("/{graph_id}/slots/{slot_id}/move", response_model=GraphFlowRead)
async def move_slot_endpoint(
    graph_id: uuid.UUID, slot_id: str, payload: SlotMoveRequest, uow: UnitOfWork = Depends(get_uow)
) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.move_slot(uow, graph_id, slot_id, payload.direction)
    return GraphFlowRead.model_validate(updated_flow)


# Edges REST API
@router.delete("/{graph_id}/edges/{edge_id}", response_model=GraphFlowRead)
async def delete_edge_endpoint(
    graph_id: uuid.UUID, edge_id: uuid.UUID, uow: UnitOfWork = Depends(get_uow)
) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.delete_edge(uow, graph_id, edge_id)
    return GraphFlowRead.model_validate(updated_flow)


@router.post("/{graph_id}/edges", response_model=GraphFlowRead)
async def create_edge_endpoint(
    graph_id: uuid.UUID, payload: EdgeCreateRequest, uow: UnitOfWork = Depends(get_uow)
) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.create_edge(
            uow, graph_id, payload.source, payload.target, payload.source_handle, payload.target_handle
        )
    return GraphFlowRead.model_validate(updated_flow)


@router.patch("/{graph_id}/edges/{edge_id}/reconnect", response_model=GraphFlowRead)
async def reconnect_edge_endpoint(
    graph_id: uuid.UUID,
    edge_id: uuid.UUID,
    payload: EdgeReconnectRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> GraphFlowRead:
    async with uow:
        updated_flow = await graph_service.reconnect_edge(
            uow,
            graph_id,
            edge_id,
            payload.source,
            payload.target,
            payload.source_handle,
            payload.target_handle,
        )
    return GraphFlowRead.model_validate(updated_flow)
