from __future__ import annotations

import uuid
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from app.constants import NodeType
from app.core.exceptions import ValidationError
from app.graphs.schemas import EdgeRead, GraphFlowData

SENTINEL_NODE_TYPES = {NodeType.START, NodeType.END}


def _resolve_handle(flow_data: GraphFlowData, node_id: str, handle: str | None) -> str | None:
    if not handle:
        return None
    node = next((n for n in flow_data.nodes if n.id == node_id), None)
    if node and hasattr(node, "branches"):
        if handle.startswith(f"{node_id}_"):
            return handle
        from app.graphs.nodes import _make_slot_id

        for b in getattr(node, "branches", []):
            if b.label == handle or b.id == handle:
                return cast(str, b.id)
        return _make_slot_id(node_id, handle)
    return handle


class DeleteNodeOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["delete_node"] = "delete_node"
    node_id: str


def delete_node(flow_data: GraphFlowData, op: DeleteNodeOp) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges
    node_id = op.node_id

    target_node = next((n for n in nodes if n.id == node_id), None)
    if not target_node:
        return flow_data

    if target_node.node_type in SENTINEL_NODE_TYPES:
        raise ValidationError(f"Sentinel node of type '{target_node.node_type}' cannot be deleted.")

    flow_data.nodes = [n for n in nodes if n.id != node_id]
    flow_data.edges = [e for e in edges if e.source != node_id and e.target != node_id]
    return flow_data


class ConnectNodesOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["connect_nodes"] = "connect_nodes"
    source: str = Field(description="The ID of the source node.")
    target: str = Field(description="The ID of the target node.")
    source_handle: str | None = Field(
        default=None,
        description="The branch label / case option name if connecting from a switch node. REQUIRED if the source node is a switch (LOGICAL_SWITCH or AGENTIC_SWITCH).",
    )
    target_handle: str | None = Field(default=None, description="The target handle option name. Usually None.")


def connect_nodes(flow_data: GraphFlowData, op: ConnectNodesOp) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges

    source_node = next((n for n in nodes if n.id == op.source), None)
    target_node = next((n for n in nodes if n.id == op.target), None)

    if not source_node:
        raise ValidationError(f"Source Node '{op.source}' not found.")
    if not target_node:
        raise ValidationError(f"Target Node '{op.target}' not found.")

    resolved_source_handle = _resolve_handle(flow_data, op.source, op.source_handle)
    resolved_target_handle = _resolve_handle(flow_data, op.target, op.target_handle)

    if hasattr(source_node, "branches"):
        if not resolved_source_handle:
            raise ValidationError(f"Source node '{op.source}' requires a case label or source_handle to connect.")
        if not any(b.id == resolved_source_handle for b in getattr(source_node, "branches", [])):
            raise ValidationError(f"Source handle/case '{op.source_handle}' not found on node '{op.source}'.")

    # De-duplicate: remove any matching connection from same output handle
    if resolved_source_handle:
        flow_data.edges = [
            e for e in edges if not (e.source == op.source and e.source_handle == resolved_source_handle)
        ]
    else:
        flow_data.edges = [e for e in edges if not (e.source == op.source and e.source_handle is None)]

    new_edge = EdgeRead(
        id=uuid.uuid4(),
        source=op.source,
        source_handle=resolved_source_handle,
        target=op.target,
        target_handle=resolved_target_handle,
    )
    flow_data.edges.append(new_edge)
    return flow_data


class DisconnectNodesOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["disconnect_nodes"] = "disconnect_nodes"
    source: str = Field(description="The ID of the source node.")
    target: str = Field(description="The ID of the target node.")
    source_handle: str | None = Field(
        default=None,
        description="The branch label / case option name if disconnecting from a switch node. REQUIRED if the source node is a switch (LOGICAL_SWITCH or AGENTIC_SWITCH).",
    )
    target_handle: str | None = Field(default=None, description="The target handle option name. Usually None.")


def disconnect_nodes(flow_data: GraphFlowData, op: DisconnectNodesOp) -> GraphFlowData:
    resolved_source_handle = _resolve_handle(flow_data, op.source, op.source_handle)
    resolved_target_handle = _resolve_handle(flow_data, op.target, op.target_handle)

    flow_data.edges = [
        e
        for e in flow_data.edges
        if not (
            e.source == op.source
            and e.source_handle == resolved_source_handle
            and e.target == op.target
            and e.target_handle == resolved_target_handle
        )
    ]
    return flow_data
