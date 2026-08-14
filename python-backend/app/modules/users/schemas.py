from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    user_name: str = Field(min_length=1, max_length=255)


class SetActiveGraph(BaseModel):
    user_id: uuid.UUID
    graph_id: uuid.UUID


class ActiveGraphResponse(BaseModel):
    graph_id: uuid.UUID | None
