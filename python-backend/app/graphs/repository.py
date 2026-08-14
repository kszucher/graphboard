from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import models
from app.graphs.schemas import GraphCreate
from app.core.base.repository import BaseRepository


class GraphRepository(BaseRepository[models.Graph, GraphCreate, GraphCreate]):
    def __init__(self, session: AsyncSession):
        super().__init__(models.Graph, session)

    async def create_graph(self, user_id: uuid.UUID, graph_name: str) -> models.Graph:
        graph = models.Graph(user_id=user_id, name=graph_name)
        self.session.add(graph)
        await self.session.flush()
        return graph

    async def list_by_user(self, user_id: uuid.UUID) -> list[models.Graph]:
        result = await self.session.execute(
            select(models.Graph).where(models.Graph.user_id == user_id).order_by(models.Graph.id.desc())
        )
        return list(result.scalars().all())


class GraphHistoryCreate(BaseModel):
    graph_id: uuid.UUID
    flow_json: dict
    sequence_number: int


class GraphHistoryRepository(BaseRepository[models.GraphHistory, GraphHistoryCreate, GraphHistoryCreate]):
    def __init__(self, session: AsyncSession):
        super().__init__(models.GraphHistory, session)

    async def clear_by_graph(self, graph_id: uuid.UUID) -> None:
        await self.session.execute(delete(models.GraphHistory).where(models.GraphHistory.graph_id == graph_id))
        await self.session.flush()

    async def list_by_graph(self, graph_id: uuid.UUID) -> list[models.GraphHistory]:
        result = await self.session.execute(
            select(models.GraphHistory)
            .where(models.GraphHistory.graph_id == graph_id)
            .order_by(models.GraphHistory.sequence_number.asc())
        )
        return list(result.scalars().all())

    async def get_latest_snapshot(self, graph_id: uuid.UUID) -> models.GraphHistory | None:
        result = await self.session.execute(
            select(models.GraphHistory)
            .where(models.GraphHistory.graph_id == graph_id)
            .order_by(models.GraphHistory.sequence_number.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_by_sequence(self, graph_id: uuid.UUID, sequence_number: int) -> models.GraphHistory | None:
        result = await self.session.execute(
            select(models.GraphHistory).where(
                models.GraphHistory.graph_id == graph_id, models.GraphHistory.sequence_number == sequence_number
            )
        )
        return result.scalars().first()

    async def save_snapshot(self, graph_id: uuid.UUID, flow_json: dict, sequence_number: int) -> models.GraphHistory:
        snapshot = models.GraphHistory(graph_id=graph_id, flow_json=flow_json, sequence_number=sequence_number)
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot
