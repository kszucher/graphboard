from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.events import GraphEventBroker, get_broker

if TYPE_CHECKING:
    from app.core.context import UnitOfWork


def _build_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )


engine: AsyncEngine = _build_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def get_uow(
    session: AsyncSession = Depends(get_session),
    broker: GraphEventBroker = Depends(get_broker),
    x_client_id: str | None = Header(default=None),
) -> AsyncIterator[UnitOfWork]:
    from .context import UnitOfWork

    uow = UnitOfWork(session, broker, x_client_id)
    try:
        yield uow
    except Exception:
        await uow.rollback()
        raise
