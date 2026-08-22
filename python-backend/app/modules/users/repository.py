from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import models
from app.core.base.repository import BaseRepository


class UserRepository(BaseRepository[models.User]):
    def __init__(self, session: AsyncSession):
        super().__init__(models.User, session)

    async def get_first(self) -> models.User | None:
        result = await self.session.execute(select(models.User).limit(1))
        return result.scalar_one_or_none()

    async def create_user(self, name: str) -> models.User:
        user = models.User(name=name)
        self.session.add(user)
        await self.session.flush()
        return user

    async def set_active_graph(self, user_id: uuid.UUID, graph_id: uuid.UUID) -> None:
        await self.session.execute(
            update(models.User).where(models.User.id == user_id).values(selected_graph_id=graph_id)
        )

    async def get_active_graph_id(self, user_id: uuid.UUID) -> uuid.UUID | None:
        user = await self.get(user_id)
        return user.selected_graph_id if user else None
