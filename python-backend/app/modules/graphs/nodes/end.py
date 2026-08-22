from __future__ import annotations

from typing import Literal

from app.core.constants import NodeType

from .base import BaseNode


class EndNode(BaseNode):
    node_type: Literal[NodeType.END] = NodeType.END
