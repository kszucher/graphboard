from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.core.context import UnitOfWork
from app.core.db import get_uow
from app.modules.users import service as user_service
from app.modules.users.schemas import ActiveGraphResponse, SetActiveGraph, UserCreate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/get-or-create", response_model=uuid.UUID)
async def get_or_create_user(uow: UnitOfWork = Depends(get_uow)) -> uuid.UUID:
    async with uow:
        user_id = await user_service.get_or_create_user(uow)
    return user_id


@router.post("/", response_model=uuid.UUID, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, uow: UnitOfWork = Depends(get_uow)) -> uuid.UUID:
    async with uow:
        user_id = await user_service.create_user(uow, payload.user_name)
    return user_id


@router.get("/{user_id}/active-graph", response_model=ActiveGraphResponse)
async def get_active_graph_id(user_id: uuid.UUID, uow: UnitOfWork = Depends(get_uow)) -> ActiveGraphResponse:
    graph_id = await user_service.get_active_graph_id(uow, user_id)

    if graph_id is None:
        return ActiveGraphResponse(graph_id=None)
    return ActiveGraphResponse(graph_id=graph_id)


@router.post("/set-active-graph", status_code=status.HTTP_204_NO_CONTENT)
async def set_active_graph(payload: SetActiveGraph, uow: UnitOfWork = Depends(get_uow)) -> None:
    async with uow:
        await user_service.set_active_graph(uow, payload.user_id, payload.graph_id)
