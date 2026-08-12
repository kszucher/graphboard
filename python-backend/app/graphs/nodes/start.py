from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.constants import NodeType

from .base import BaseNode


class StartConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.START] = NodeType.START


class StartNode(BaseNode, StartConfig):
    pass
