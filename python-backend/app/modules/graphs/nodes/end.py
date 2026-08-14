from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.constants import NodeType

from .base import BaseNode


class EndConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.END] = NodeType.END


class EndNode(BaseNode, EndConfig):
    pass
