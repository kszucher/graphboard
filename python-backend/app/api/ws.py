from __future__ import annotations

import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.events import broker

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/graphs/{graph_id}")
async def graph_ws(graph_id: uuid.UUID, websocket: WebSocket) -> None:
    await websocket.accept()
    client_id = websocket.query_params.get("client_id")
    await broker.subscribe(graph_id, websocket, client_id)

    # Debug message to prove this handler talks to the browser websocket
    try:
        await websocket.send_json({"event": "ws_hello", "graph_id": str(graph_id)})
    except Exception as e:
        print(f"[graph_ws] failed to send hello message: {e}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await broker.unsubscribe(graph_id, websocket)
    except Exception as e:
        print(f"[graph_ws] unexpected error: {e}")
        await broker.unsubscribe(graph_id, websocket)
        await websocket.close()
