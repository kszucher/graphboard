from __future__ import annotations

import uuid
from typing import Any, Literal

from app.constants import NodeType
from app.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    EdgeRead,
    EndNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    NodeRead,
    SlotRead,
    StartNode,
)

SENTINEL_NODE_TYPES = {NodeType.START, NodeType.END}
SEQUENTIAL_STEP_TYPES = {
    NodeType.LOGICAL_ASSIGNER,
    NodeType.AGENTIC_ASSIGNER,
    NodeType.INTERRUPT,
}

_UNSET: Any = object()


def generate_node_id(node_type: NodeType | str, existing_nodes: list[NodeRead]) -> str:
    val = node_type.value if isinstance(node_type, NodeType) else node_type
    prefix = val.lower()
    count = 1
    existing_ids = {n.id for n in existing_nodes}
    while f"{prefix}_{count}" in existing_ids:
        count += 1
    return f"{prefix}_{count}"


def add_node(
    flow_data: GraphFlowData,
    node_type: NodeType | str,
    connector_id: str | None = None,
    direction: str | None = None,
) -> GraphFlowData:
    node_type = NodeType(node_type)
    nodes = flow_data.nodes
    edges = flow_data.edges
    node_id = generate_node_id(node_type, nodes)

    slots: list[SlotRead] = []
    if node_type in (NodeType.LOGICAL_SWITCH, NodeType.AGENTIC_SWITCH):
        slots = [
            SlotRead(id=f"{node_id}_option_a", raw_string="option_a"),
            SlotRead(id=f"{node_id}_option_b", raw_string="option_b"),
        ]

    new_node: NodeRead
    if node_type == NodeType.START:
        new_node = StartNode(id=node_id)
    elif node_type == NodeType.END:
        new_node = EndNode(id=node_id)
    elif node_type == NodeType.LOGICAL_ASSIGNER:
        new_node = LogicalAssignerNode(id=node_id, assignments=[])
    elif node_type == NodeType.AGENTIC_ASSIGNER:
        new_node = AgenticAssignerNode(id=node_id, prompt="", agentic_inputs=[], agentic_outputs=[])
    elif node_type == NodeType.LOGICAL_SWITCH:
        new_node = LogicalSwitchNode(id=node_id, slots=slots)
    elif node_type == NodeType.INTERRUPT:
        new_node = InterruptNode(id=node_id, payload_vars=[], resume_var="")
    elif node_type == NodeType.AGENTIC_SWITCH:
        new_node = AgenticSwitchNode(id=node_id, slots=slots, agentic_input="")
    else:
        raise ValueError(f"Unsupported node_type: {node_type}")

    nodes.append(new_node)

    if connector_id and direction:
        is_after = direction == "after"

        old_edges = []
        for e in edges:
            if is_after:
                if e.source_id == connector_id:
                    old_edges.append(e)
            else:
                if e.target_id == connector_id:
                    old_edges.append(e)

        to_slot_id = node_id
        from_slot_id = (
            slots[0].id if (node_type in (NodeType.LOGICAL_SWITCH, NodeType.AGENTIC_SWITCH) and slots) else node_id
        )

        target_or_source_node = next((n for n in nodes if n.id == connector_id), None)
        if not target_or_source_node:
            target_or_source_node = next(
                (
                    n
                    for n in nodes
                    if hasattr(n, "slots") and any(s.id == connector_id for s in getattr(n, "slots", []))
                ),
                None,
            )

        source_type: Literal["node", "slot"] = "node"
        if (
            is_after
            and target_or_source_node
            and target_or_source_node.node_type in (NodeType.LOGICAL_SWITCH, NodeType.AGENTIC_SWITCH)
        ):
            source_type = "slot"

        target_type: Literal["node", "slot"] = "node"
        if not is_after and target_or_source_node and hasattr(target_or_source_node, "slots"):
            if any(s.id == connector_id for s in getattr(target_or_source_node, "slots", [])):
                target_type = "slot"

        new_edge = EdgeRead(
            id=uuid.uuid4(),
            source_id=connector_id if is_after else from_slot_id,
            target_id=to_slot_id if is_after else connector_id,
            source_type=source_type,
            target_type=target_type,
        )

        updated_old_edges = []
        for old_edge in old_edges:
            upd = old_edge.model_copy()
            if is_after:
                upd.source_id = from_slot_id
                upd.source_type = "slot" if node_type in (NodeType.LOGICAL_SWITCH, NodeType.AGENTIC_SWITCH) else "node"
            else:
                upd.target_id = to_slot_id
                upd.target_type = "node"
            updated_old_edges.append(upd)

        old_edge_ids = {e.id for e in old_edges}
        next_edges = [e for e in edges if e.id not in old_edge_ids]
        next_edges.append(new_edge)
        next_edges.extend(updated_old_edges)
        flow_data.edges = next_edges

    return flow_data


def delete_node(flow_data: GraphFlowData, node_id: str) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges

    target_node = next((n for n in nodes if n.id == node_id), None)
    if not target_node:
        return flow_data

    # Sentinel protection: START and END nodes cannot be deleted
    if target_node.node_type in SENTINEL_NODE_TYPES:
        return flow_data

    slot_ids = (
        {s.id for s in target_node.slots} if isinstance(target_node, (LogicalSwitchNode, AgenticSwitchNode)) else set()
    )

    flow_data.nodes = [n for n in nodes if n.id != node_id]
    flow_data.edges = [
        e
        for e in edges
        if e.source_id != node_id
        and e.target_id != node_id
        and e.source_id not in slot_ids
        and e.target_id not in slot_ids
    ]
    return flow_data


def shortcircuit_node(flow_data: GraphFlowData, node_id: str) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges

    target_node = next((n for n in nodes if n.id == node_id), None)
    if not target_node or target_node.node_type not in SEQUENTIAL_STEP_TYPES:
        return flow_data

    incoming = [e for e in edges if e.target_id == node_id]
    outgoing = [e for e in edges if e.source_id == node_id]

    next_edges = [e for e in edges if e.source_id != node_id and e.target_id != node_id]

    if incoming and outgoing:
        for inc in incoming:
            for out in outgoing:
                next_edges.append(
                    EdgeRead(
                        id=uuid.uuid4(),
                        source_id=inc.source_id,
                        target_id=out.target_id,
                        source_type=inc.source_type,
                        target_type=out.target_type,
                    )
                )

    flow_data.nodes = [n for n in nodes if n.id != node_id]
    flow_data.edges = next_edges
    return flow_data


def update_node(
    flow_data: GraphFlowData,
    node_id: str,
    new_id: str | None = None,
    prompt: str | None = None,
    agentic_inputs: list[str] | None = None,
    agentic_input: str | None = None,
    agentic_outputs: list[str] | None = None,
    payload_vars: list[str] | None = None,
    resume_var: str | None = None,
) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges

    target_node = next((n for n in nodes if n.id == node_id), None)
    if not target_node:
        return flow_data

    if new_id and new_id != node_id:
        target_node.id = new_id
        if hasattr(target_node, "slots"):
            for slot in getattr(target_node, "slots", []):
                if slot.id.startswith(f"{node_id}_"):
                    slot.id = slot.id.replace(f"{node_id}_", f"{new_id}_", 1)

        for edge in edges:
            if edge.source_id == node_id:
                edge.source_id = new_id
            elif edge.source_id.startswith(f"{node_id}_"):
                edge.source_id = edge.source_id.replace(f"{node_id}_", f"{new_id}_", 1)

            if edge.target_id == node_id:
                edge.target_id = new_id
            elif edge.target_id.startswith(f"{node_id}_"):
                edge.target_id = edge.target_id.replace(f"{node_id}_", f"{new_id}_", 1)

    if isinstance(target_node, AgenticAssignerNode):
        if prompt is not _UNSET and prompt is not None:
            target_node.prompt = prompt
        if agentic_inputs is not _UNSET and agentic_inputs is not None:
            target_node.agentic_inputs = agentic_inputs
        if agentic_outputs is not _UNSET and agentic_outputs is not None:
            target_node.agentic_outputs = agentic_outputs
    if isinstance(target_node, AgenticSwitchNode):
        if agentic_input is not _UNSET and agentic_input is not None:
            target_node.agentic_input = agentic_input
    if isinstance(target_node, InterruptNode):
        if payload_vars is not _UNSET and payload_vars is not None:
            target_node.payload_vars = payload_vars
        if resume_var is not _UNSET and resume_var is not None:
            target_node.resume_var = resume_var

    return flow_data


def create_slot(flow_data: GraphFlowData, node_id: str, index: int) -> GraphFlowData:
    nodes = flow_data.nodes
    target_node = next((n for n in nodes if n.id == node_id), None)
    if not target_node or not isinstance(target_node, (LogicalSwitchNode, AgenticSwitchNode)):
        return flow_data

    slots = target_node.slots
    slot_count = len(slots) + 1
    new_slot_id = f"{node_id}_option_{slot_count}"
    new_slot = SlotRead(
        id=new_slot_id,
        raw_string=f"option_{slot_count}",
    )

    insert_idx = max(0, min(index, len(slots)))
    slots.insert(insert_idx, new_slot)
    return flow_data


def update_slot(
    flow_data: GraphFlowData,
    slot_id: str,
    raw_string: str | None = None,
    expression: dict[str, Any] | None = _UNSET,
) -> GraphFlowData:
    nodes = flow_data.nodes
    for node in nodes:
        if hasattr(node, "slots"):
            for slot in getattr(node, "slots", []):
                if slot.id == slot_id:
                    if raw_string is not None:
                        slot.raw_string = raw_string
                    if expression is not _UNSET:
                        slot.expression = expression
                    return flow_data
    return flow_data


def delete_slot(flow_data: GraphFlowData, slot_id: str) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges

    for node in nodes:
        if isinstance(node, (LogicalSwitchNode, AgenticSwitchNode)):
            slots = node.slots
            if any(s.id == slot_id for s in slots):
                node.slots = [s for s in slots if s.id != slot_id]
                break

    flow_data.edges = [e for e in edges if e.source_id != slot_id and e.target_id != slot_id]
    return flow_data


def move_slot(flow_data: GraphFlowData, slot_id: str, direction: str) -> GraphFlowData:
    nodes = flow_data.nodes
    for node in nodes:
        if hasattr(node, "slots"):
            slots = getattr(node, "slots", [])
            idx = next((i for i, s in enumerate(slots) if s.id == slot_id), -1)
            if idx != -1:
                target_idx = idx
                if direction == "up":
                    target_idx = max(0, idx - 1)
                elif direction == "down":
                    target_idx = min(len(slots) - 1, idx + 1)
                elif direction == "top":
                    target_idx = 0
                elif direction == "bottom":
                    target_idx = len(slots) - 1

                if target_idx != idx:
                    slot = slots.pop(idx)
                    slots.insert(target_idx, slot)
                break
    return flow_data


def delete_edge(flow_data: GraphFlowData, edge_id: uuid.UUID) -> GraphFlowData:
    edges = flow_data.edges
    flow_data.edges = [e for e in edges if e.id != edge_id]
    return flow_data


def create_edge(
    flow_data: GraphFlowData,
    source: str,
    target: str,
    source_handle: str,
    target_handle: str,
) -> GraphFlowData:
    edges = flow_data.edges
    nodes = flow_data.nodes

    source_node = next((n for n in nodes if n.id == source), None)
    target_node = next((n for n in nodes if n.id == target), None)

    source_type: Literal["node", "slot"] = (
        "slot"
        if (source_node and source_node.node_type in (NodeType.LOGICAL_SWITCH, NodeType.AGENTIC_SWITCH))
        else "node"
    )
    target_type: Literal["node", "slot"] = "node"

    if isinstance(target_node, (LogicalSwitchNode, AgenticSwitchNode)):
        is_target_slot = any(s.id == target_handle for s in target_node.slots)
        if is_target_slot:
            target_type = "slot"

    new_edge = EdgeRead(
        id=uuid.uuid4(),
        source_id=source_handle if source_type == "slot" else source,
        target_id=target_handle if target_type == "slot" else target,
        source_type=source_type,
        target_type=target_type,
    )
    edges.append(new_edge)
    return flow_data


def reconnect_edge(
    flow_data: GraphFlowData,
    edge_id: uuid.UUID,
    source: str,
    target: str,
    source_handle: str,
    target_handle: str,
) -> GraphFlowData:
    edges = flow_data.edges
    nodes = flow_data.nodes

    edge = next((e for e in edges if e.id == edge_id), None)
    if not edge:
        return flow_data

    source_node = next((n for n in nodes if n.id == source), None)
    target_node = next((n for n in nodes if n.id == target), None)

    source_type: Literal["node", "slot"] = (
        "slot"
        if (source_node and source_node.node_type in (NodeType.LOGICAL_SWITCH, NodeType.AGENTIC_SWITCH))
        else "node"
    )
    target_type: Literal["node", "slot"] = "node"

    if isinstance(target_node, (LogicalSwitchNode, AgenticSwitchNode)):
        is_target_slot = any(s.id == target_handle for s in target_node.slots)
        if is_target_slot:
            target_type = "slot"

    edge.source_id = source_handle if source_type == "slot" else source
    edge.target_id = target_handle if target_type == "slot" else target
    edge.source_type = source_type
    edge.target_type = target_type

    return flow_data
