from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.models import Base

T = TypeVar("T", bound=Base)
CreateSchema = TypeVar("CreateSchema", bound=BaseModel)
UpdateSchema = TypeVar("UpdateSchema", bound=BaseModel)


class BaseRepository(Generic[T, CreateSchema, UpdateSchema]):
    def __init__(self, model: type[T], session: AsyncSession):
        self.model = model
        self.session = session

    async def create(self, data: CreateSchema) -> T:
        obj = self.model(**data.model_dump())
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get(self, obj_id: uuid.UUID) -> T | None:
        result = await self.session.execute(select(self.model).where(self.model.id == obj_id))  # type: ignore[attr-defined]
        return result.scalars().first()

    async def delete(self, obj_id: uuid.UUID) -> None:
        await self.session.execute(delete(self.model).where(self.model.id == obj_id))  # type: ignore[attr-defined]
        await self.session.flush()

    async def update(self, obj_id: uuid.UUID, data: UpdateSchema) -> T | None:
        obj = await self.get(obj_id)
        if not obj:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(obj, key, value)

        await self.session.flush()
        return obj
