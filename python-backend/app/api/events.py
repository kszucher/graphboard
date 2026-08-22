from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.api.schemas import GraphEvent

logger = logging.getLogger(__name__)


class GraphEventBroker:
    def __init__(self) -> None:
        self._subscribers: defaultdict[uuid.UUID, dict[WebSocket, str | None]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def subscribe(self, graph_id: uuid.UUID, websocket: WebSocket, client_id: str | None) -> None:
        async with self._lock:
            self._subscribers[graph_id][websocket] = client_id
        logger.debug("Subscribed client %s to graph %s", client_id, graph_id)

    async def unsubscribe(self, graph_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._subscribers[graph_id].pop(websocket, None)
            if not self._subscribers[graph_id]:
                self._subscribers.pop(graph_id, None)
        logger.debug("Unsubscribed websocket from graph %s", graph_id)

    async def broadcast(self, event: GraphEvent) -> None:
        async with self._lock:
            listeners = list(self._subscribers.get(event.graph_id, {}).items())

        if not listeners:
            logger.debug("No listeners for graph %s, event=%s", event.graph_id, event.event)
            return

        payload = event.model_dump(mode="json")
        logger.debug(
            "Broadcasting %s for graph %s to %d listener(s)",
            event.event,
            event.graph_id,
            len(listeners),
        )

        async def _send(ws: WebSocket, client_id: str | None) -> None:
            if event.sender_client_id is not None and client_id == event.sender_client_id:
                return
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.warning("Failed sending %s to websocket: %s", event.event, e)
                await self.unsubscribe(event.graph_id, ws)

        await asyncio.gather(*[_send(ws, client_id) for ws, client_id in listeners])

    async def emit(
        self,
        event: str,
        graph_id: uuid.UUID,
        payload: dict[str, Any],
        sender_client_id: str | None = None,
    ) -> None:
        """Convenience method to broadcast an event without manual GraphEvent instantiation."""
        await self.broadcast(
            GraphEvent(
                event=event,  # type: ignore[arg-type]
                graph_id=graph_id,
                payload=payload,
                sender_client_id=sender_client_id,
            )
        )


broker = GraphEventBroker()


def get_broker() -> GraphEventBroker:
    return broker
