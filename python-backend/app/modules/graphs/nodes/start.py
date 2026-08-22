from __future__ import annotations

from typing import Literal

from app.core.constants import NodeType

from .base import BaseNode


class StartNode(BaseNode):
    node_type: Literal[NodeType.START] = NodeType.START
