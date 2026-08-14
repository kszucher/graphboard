import uuid

import pytest
from sqlalchemy import select

from app.core.context import UnitOfWork
from app.core.base.models import Graph, GraphHistory, User
from app.modules.users import service as users_service


@pytest.mark.asyncio
async def test_get_or_create_user_existing(
    real_uow: UnitOfWork,
    dummy_user: User,
) -> None:
    # Call service with the real UoW
    user_id = await users_service.get_or_create_user(real_uow)

    # Assertions
    assert user_id == dummy_user.id

    # Check that no new user was created
    result = await real_uow.session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 1


@pytest.mark.asyncio
async def test_get_or_create_user_new(
    real_uow: UnitOfWork,
) -> None:
    # Call service when no users exist
    user_id = await users_service.get_or_create_user(real_uow)

    # Assertions
    assert isinstance(user_id, uuid.UUID)

    # Check that a user was created
    result = await real_uow.session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.name == "User"


@pytest.mark.asyncio
async def test_create_user(
    real_uow: UnitOfWork,
) -> None:
    # Call service to create a user named Alice
    user_id = await users_service.create_user(real_uow, "Alice")

    # Assertions
    assert isinstance(user_id, uuid.UUID)

    # Check database
    result = await real_uow.session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.name == "Alice"


@pytest.mark.asyncio
async def test_set_active_graph(
    real_uow: UnitOfWork,
    dummy_user: User,
    dummy_graph: Graph,
) -> None:
    # Call service to set active graph
    await users_service.set_active_graph(real_uow, dummy_user.id, dummy_graph.id)

    # Assertions
    # Check user has active graph set
    await real_uow.session.refresh(dummy_user)
    assert dummy_user.selected_graph_id == dummy_graph.id

    # Check history snapshot exists in DB
    result = await real_uow.session.execute(select(GraphHistory).where(GraphHistory.graph_id == dummy_graph.id))
    history = result.scalars().all()
    assert len(history) == 1
    assert history[0].sequence_number == 0


@pytest.mark.asyncio
async def test_get_active_graph_id(
    real_uow: UnitOfWork,
    dummy_user: User,
    dummy_graph: Graph,
) -> None:
    # Setup: Associate the graph to user first and commit
    dummy_user.selected_graph_id = dummy_graph.id
    real_uow.session.add(dummy_user)
    await real_uow.session.commit()

    # Call service
    graph_id = await users_service.get_active_graph_id(real_uow, dummy_user.id)

    # Assertions
    assert graph_id == dummy_graph.id
