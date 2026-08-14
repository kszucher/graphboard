import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.events import GraphEventBroker
from app.core.base.models import Base, Graph, GraphHistory, User
from app.core.context import UnitOfWork


@pytest.fixture(scope="session")
def db_engine() -> AsyncEngine:
    # Use StaticPool to share the in-memory SQLite DB connection across the session
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


@pytest.fixture(scope="function")
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    # Setup schema
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(db_engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    # Tear down schema
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mock_broker() -> AsyncMock:
    return AsyncMock(spec=GraphEventBroker)


@pytest.fixture
async def real_uow(db_session: AsyncSession, mock_broker: AsyncMock) -> UnitOfWork:
    return UnitOfWork(session=db_session, broker=mock_broker)


@pytest.fixture
async def dummy_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        color_mode="DARK",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def dummy_graph(db_session: AsyncSession, dummy_user: User) -> Graph:
    graph = Graph(
        id=uuid.uuid4(),
        name="Test Graph",
        user_id=dummy_user.id,
    )
    db_session.add(graph)
    snapshot = GraphHistory(
        id=uuid.uuid4(),
        graph_id=graph.id,
        flow_json={"nodes": [], "edges": [], "state": []},
        sequence_number=0,
    )
    db_session.add(snapshot)
    await db_session.flush()
    return graph
