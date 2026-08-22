from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.events import broker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/graphs/{graph_id}")
async def graph_ws(graph_id: uuid.UUID, websocket: WebSocket) -> None:
    await websocket.accept()
    client_id = websocket.query_params.get("client_id")
    await broker.subscribe(graph_id, websocket, client_id)

    try:
        await websocket.send_json({"event": "ws_hello", "graph_id": str(graph_id)})
    except Exception as e:
        logger.debug("[graph_ws] failed to send hello message: %s", e)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await broker.unsubscribe(graph_id, websocket)
    except Exception as e:
        logger.debug("[graph_ws] socket connection ended: %s", e)
        await broker.unsubscribe(graph_id, websocket)
        try:
            await websocket.close()
        except Exception:
            pass
