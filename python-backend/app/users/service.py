from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.context import UnitOfWork


async def get_or_create_user(uow: UnitOfWork) -> uuid.UUID:
    user = await uow.users.get_first()
    if user:
        return user.id
    created = await uow.users.create(name="User")
    await uow.session.flush()
    return created.id


async def create_user(uow: UnitOfWork, user_name: str) -> uuid.UUID:
    user = await uow.users.create(name=user_name)
    await uow.session.flush()
    return user.id


async def get_active_graph_id(uow: UnitOfWork, user_id: uuid.UUID) -> uuid.UUID | None:
    graph_id = await uow.users.get_active_graph_id(user_id)
    if graph_id:
        from app.graphs.service import reset_graph_history

        await reset_graph_history(uow, graph_id)
    return graph_id


async def set_active_graph(uow: UnitOfWork, user_id: uuid.UUID, graph_id: uuid.UUID) -> None:
    await uow.users.set_active_graph(user_id, graph_id)
    from app.graphs.service import reset_graph_history

    await reset_graph_history(uow, graph_id)
