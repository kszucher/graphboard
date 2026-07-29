from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import EventName
from app.events import GraphEventBroker

if TYPE_CHECKING:
    from app.graphs.repository import GraphHistoryRepository, GraphRepository
    from app.users.repository import UserRepository


class UnitOfWork:
    def __init__(self, session: AsyncSession, broker: GraphEventBroker, sender_client_id: str | None = None):
        self.session = session
        self.broker = broker
        self.sender_client_id = sender_client_id
        self._events: list[dict[str, Any]] = []

        # Lazy-loaded repositories
        self._graphs: GraphRepository | None = None
        self._users: UserRepository | None = None
        self._graph_history: GraphHistoryRepository | None = None

    @property
    def graphs(self) -> GraphRepository:
        if self._graphs is None:
            from app.graphs.repository import GraphRepository

            self._graphs = GraphRepository(self.session)
        return self._graphs

    @property
    def graph_history(self) -> GraphHistoryRepository:
        if self._graph_history is None:
            from app.graphs.repository import GraphHistoryRepository

            self._graph_history = GraphHistoryRepository(self.session)
        return self._graph_history

    @property
    def users(self) -> UserRepository:
        if self._users is None:
            from app.users.repository import UserRepository

            self._users = UserRepository(self.session)
        return self._users

    def emit(self, event: EventName, graph_id: uuid.UUID, payload: dict[str, Any]) -> None:
        """Buffer an event to be broadcasted after commit."""
        self._events.append(
            {"event": event, "graph_id": graph_id, "payload": payload, "sender_client_id": self.sender_client_id}
        )

    async def commit(self) -> None:
        """Commit the transaction and broadcast accumulated events."""
        await self.session.commit()
        for event_data in self._events:
            await self.broker.emit(**event_data)
        self._events.clear()

    async def rollback(self) -> None:
        """Rollback the transaction and clear events."""
        await self.session.rollback()
        self._events.clear()
