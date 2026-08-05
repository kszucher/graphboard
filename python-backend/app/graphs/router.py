import uuid
from typing import Any

from fastapi import APIRouter, Depends, status

from app.context import UnitOfWork
from app.db import get_uow
from app.graphs import service as graph_service
from app.graphs.schemas import (
    GraphCodeRead,
    GraphCreate,
    GraphFlowRead,
    GraphRead,
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
