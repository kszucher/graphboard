from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.users import service as user_service
from app.users.schemas import ActiveGraphResponse, SetActiveGraph, UserCreate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/get-or-create", response_model=uuid.UUID)
async def get_or_create_user(session: AsyncSession = Depends(get_session)) -> uuid.UUID:
    return await user_service.get_or_create_user(session)


@router.post("/", response_model=uuid.UUID, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)) -> uuid.UUID:
    return await user_service.create_user(session, payload.user_name)


@router.get("/{user_id}/active-graph", response_model=ActiveGraphResponse)
async def get_active_graph_id(user_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> ActiveGraphResponse:
    graph_id = await user_service.get_active_graph_id(session, user_id)
    if graph_id is None:
        return ActiveGraphResponse(graph_id=None)
    return ActiveGraphResponse(graph_id=graph_id)


@router.post("/set-active-graph", status_code=status.HTTP_204_NO_CONTENT)
async def set_active_graph(payload: SetActiveGraph, session: AsyncSession = Depends(get_session)) -> None:
    await user_service.set_active_graph(session, payload.user_id, payload.graph_id)
