from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.schemas import GraphEvent


class GraphEventBroker:
    def __init__(self) -> None:
        self._subscribers: defaultdict[uuid.UUID, dict[WebSocket, str | None]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def subscribe(self, graph_id: uuid.UUID, websocket: WebSocket, client_id: str | None) -> None:
        async with self._lock:
            self._subscribers[graph_id][websocket] = client_id

    async def unsubscribe(self, graph_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._subscribers[graph_id].pop(websocket, None)
            if not self._subscribers[graph_id]:
                self._subscribers.pop(graph_id, None)

    async def broadcast(self, event: GraphEvent) -> None:
        async with self._lock:
            listeners = list(self._subscribers.get(event.graph_id, {}).items())

        if not listeners:
            print(f"[GraphEventBroker] No listeners for graph {event.graph_id}, event={event.event}")
            return

        # Use Pydantic's JSON mode so UUIDs become strings and are JSON-serializable
        payload = event.model_dump(mode="json")
        print(
            f"[GraphEventBroker] Broadcasting {event.event} for graph {event.graph_id} "
            f"to {len(listeners)} listener(s) with payload={payload}"
        )

        async def _send(ws: WebSocket, client_id: str | None) -> None:
            if event.sender_client_id is not None and client_id == event.sender_client_id:
                return
            try:
                print(f"[GraphEventBroker] sending {event.event} to websocket {id(ws)}")
                await ws.send_json(payload)
                print(f"[GraphEventBroker] sent {event.event} to websocket {id(ws)} OK")
            except Exception as e:
                print(f"[GraphEventBroker] ERROR sending {event.event} to websocket {id(ws)}: {e}")
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
                event=event,  # type: ignore
                graph_id=graph_id,
                payload=payload,
                sender_client_id=sender_client_id,
            )
        )


broker = GraphEventBroker()


def get_broker() -> GraphEventBroker:
    return broker
