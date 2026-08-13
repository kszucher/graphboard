from __future__ import annotations

import uuid
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs.nodes import NODE_CLASS_MAP, AgenticSwitchNode, LogicalSwitchNode, NodeRead
from app.graphs.schemas import EdgeRead, GraphFlowData

SENTINEL_NODE_TYPES = {NodeType.START, NodeType.END}


def _resolve_case_handle_fields(
    source: str, case: str | None, source_handle: str | None
) -> tuple[str | None, str | None]:
    case_val = case
    if not case_val and source_handle and not source_handle.startswith(f"{source}_"):
        case_val = source_handle
    if case_val:
        from app.graphs.nodes import _make_slot_id

        return _make_slot_id(source, case_val), case_val
    return source_handle, case


class CreateNodeOp(BaseModel):
    """Create an empty node shell of the specified type."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["create_node"] = "create_node"
    node_id: str
    node_type: NodeType


class DeleteNodeOp(BaseModel):
    """Delete a node and all of its incoming/outgoing connections."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["delete_node"] = "delete_node"
    node_id: str


class ConnectOp(BaseModel):
    """Draw a connection edge from a source node/branch to a target node. The branch (case label) must already exist on the switch node prior to connecting."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["connect"] = "connect"
    source: str
    source_handle: SkipJsonSchema[str | None] = None
    target: str
    target_handle: SkipJsonSchema[str | None] = None
    case: str | None = None

    @model_validator(mode="after")
    def resolve_case_handle(self) -> ConnectOp:
        self.source_handle, self.case = _resolve_case_handle_fields(self.source, self.case, self.source_handle)
        return self


class DisconnectOp(BaseModel):
    """Remove a connection edge between a source node/handle and target node/handle."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["disconnect"] = "disconnect"
    source: str
    source_handle: SkipJsonSchema[str | None] = None
    target: str
    target_handle: SkipJsonSchema[str | None] = None
    case: str | None = None

    @model_validator(mode="after")
    def resolve_case_handle(self) -> DisconnectOp:
        self.source_handle, self.case = _resolve_case_handle_fields(self.source, self.case, self.source_handle)
        return self


class AddSwitchBranchOp(BaseModel):
    """Add a new empty branch to a switch node."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["add_switch_branch"] = "add_switch_branch"
    node_id: str
    label: str


class RemoveSwitchBranchOp(BaseModel):
    """Remove a branch from a switch node and clean up its outgoing connections."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["remove_switch_branch"] = "remove_switch_branch"
    node_id: str
    label: str


def create_node(flow_data: GraphFlowData, op: CreateNodeOp) -> GraphFlowData:
    nodes = flow_data.nodes
    if any(n.id == op.node_id for n in nodes):
        raise ValidationError(f"Node '{op.node_id}' already exists.")

    node_cls = NODE_CLASS_MAP.get(op.node_type)
    if not node_cls:
        raise ValidationError(f"Unsupported node type: {op.node_type}")

    new_node = node_cls.model_validate({"id": op.node_id, "node_type": op.node_type})
    nodes.append(cast(NodeRead, new_node))
    return flow_data


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


def connect(flow_data: GraphFlowData, op: ConnectOp) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges

    source_node = next((n for n in nodes if n.id == op.source), None)
    target_node = next((n for n in nodes if n.id == op.target), None)

    if not source_node:
        raise ValidationError(f"Source Node '{op.source}' not found.")
    if not target_node:
        raise ValidationError(f"Target Node '{op.target}' not found.")

    if hasattr(source_node, "branches"):
        if not op.source_handle:
            raise ValidationError(f"Source node '{op.source}' requires a case label or source_handle to connect.")
        if not any(b.id == op.source_handle for b in getattr(source_node, "branches", [])):
            raise ValidationError(
                f"Source handle/case '{op.case or op.source_handle}' not found on node '{op.source}'."
            )

    if op.source_handle:
        flow_data.edges = [e for e in edges if not (e.source == op.source and e.source_handle == op.source_handle)]
    else:
        flow_data.edges = [e for e in edges if not (e.source == op.source and e.source_handle is None)]

    new_edge = EdgeRead(
        id=uuid.uuid4(),
        source=op.source,
        source_handle=op.source_handle,
        target=op.target,
        target_handle=op.target_handle,
    )
    flow_data.edges.append(new_edge)
    return flow_data


def disconnect(flow_data: GraphFlowData, op: DisconnectOp) -> GraphFlowData:
    flow_data.edges = [
        e
        for e in flow_data.edges
        if not (
            e.source == op.source
            and e.source_handle == op.source_handle
            and e.target == op.target
            and e.target_handle == op.target_handle
        )
    ]
    return flow_data


def add_switch_branch(flow_data: GraphFlowData, op: AddSwitchBranchOp) -> GraphFlowData:
    target_node = next((n for n in flow_data.nodes if n.id == op.node_id), None)
    if not target_node:
        raise ValidationError(f"Node '{op.node_id}' not found.")

    if not target_node.supports_branches:
        raise ValidationError(f"Node '{op.node_id}' does not support branches.")

    if any(b.label == op.label for b in getattr(target_node, "branches", [])):
        raise ValidationError(f"Branch '{op.label}' already exists on node '{op.node_id}'.")

    from app.graphs.nodes import AgenticBranch, Branch

    if isinstance(target_node, LogicalSwitchNode):
        target_node.branches.append(Branch(label=op.label))
    elif isinstance(target_node, AgenticSwitchNode):
        target_node.branches.append(AgenticBranch(label=op.label))
    return flow_data


def remove_switch_branch(flow_data: GraphFlowData, op: RemoveSwitchBranchOp) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges
    node_id = op.node_id
    label = op.label

    target_node = next((n for n in nodes if n.id == node_id), None)
    if not target_node:
        raise ValidationError(f"Node '{node_id}' not found.")

    if not target_node.supports_branches:
        raise ValidationError(f"Node '{node_id}' of type '{target_node.node_type}' does not support branches.")

    if isinstance(target_node, LogicalSwitchNode):
        target_node.branches = [b for b in target_node.branches if b.label != label]
    elif isinstance(target_node, AgenticSwitchNode):
        target_node.branches = [b for b in target_node.branches if b.label != label]

    from app.graphs.nodes import _make_slot_id

    branch_handle_id = _make_slot_id(node_id, label)
    flow_data.edges = [e for e in edges if not (e.source == node_id and e.source_handle == branch_handle_id)]
    return flow_data
