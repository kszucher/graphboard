from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel

from app.constants import EventName


# Shared event model
class GraphEvent(BaseModel):
    event: EventName
    graph_id: uuid.UUID
    payload: dict[str, Any]
    sender_client_id: str | None = None
