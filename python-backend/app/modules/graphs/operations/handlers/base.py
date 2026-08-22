from __future__ import annotations

from typing import Protocol

from app.modules.graphs.nodes import BaseNode
from app.modules.graphs.operations.schemas import NodeUpsertInput
from app.modules.graphs.schemas import GraphFlowData


class BaseNodeHandler(Protocol):
    """Protocol for node-specific mutation and validation handlers."""

    def apply(
        self,
        node: BaseNode,
        u_node: NodeUpsertInput,
        flow_data: GraphFlowData,
        valid_keys: set[str],
    ) -> None:
        """Applies node configuration, registers expressions, and validates state referential integrity."""
        ...
