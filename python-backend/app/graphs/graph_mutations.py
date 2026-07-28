import uuid
from typing import Literal


def generate_node_id(node_type: str, existing_nodes: list[dict]) -> str:
    prefix = node_type.lower()
    count = 1
    existing_ids = {n["id"] for n in existing_nodes}
    while f"{prefix}_{count}" in existing_ids:
        count += 1
    return f"{prefix}_{count}"


def add_node(flow_json: dict, node_type: str, connector_id: str | None = None, direction: str | None = None) -> dict:
    nodes = flow_json.setdefault("nodes", [])
    edges = flow_json.setdefault("edges", [])
    node_id = generate_node_id(node_type, nodes)

    slots = []
    if node_type == "SWITCH":
        slots = [
            {"id": f"{node_id}_option_a", "raw_string": "option_a", "selected": False},
            {"id": f"{node_id}_option_b", "raw_string": "option_b", "selected": False},
        ]

    new_node = {
        "id": node_id,
        "node_type": node_type,
        "is_input": True,
        "is_output": node_type in ("STEP", "DEFINER", "LOGICAL_ASSIGNER", "AGENTIC_ASSIGNER"),
        "slots": slots,
        "code": "",
        "selected": False,
    }
    nodes.append(new_node)

    if connector_id and direction:
        is_after = direction == "after"
        # Find old edges connected to the connector
        old_edges = [
            e for e in edges if (e.get("source_id") == connector_id if is_after else e.get("target_id") == connector_id)
        ]

        to_slot_id = node_id
        from_slot_id = slots[0]["id"] if (node_type == "SWITCH" and slots) else node_id

        # Find target/source node
        target_or_source_node = next((n for n in nodes if n["id"] == connector_id), None)
        if not target_or_source_node:
            target_or_source_node = next(
                (n for n in nodes if any(s["id"] == connector_id for s in n.get("slots", []))), None
            )

        new_edge = {
            "id": str(uuid.uuid4()),
            "source_id": connector_id if is_after else from_slot_id,
            "target_id": to_slot_id if is_after else connector_id,
            "source_type": (
                "slot"
                if (is_after and target_or_source_node and target_or_source_node["node_type"] == "SWITCH")
                else "node"
            ),
            "target_type": "node",
        }
        if not is_after and target_or_source_node:
            new_edge["target_type"] = (
                "slot" if any(s["id"] == connector_id for s in target_or_source_node.get("slots", [])) else "node"
            )

        # Update old edges to route through the new node
        updated_old_edges = []
        for old_edge in old_edges:
            upd = old_edge.copy()
            if is_after:
                upd["source_id"] = from_slot_id
                upd["source_type"] = "slot" if node_type == "SWITCH" else "node"
            else:
                upd["target_id"] = to_slot_id
                upd["target_type"] = "node"
            updated_old_edges.append(upd)

        old_edge_ids = {e["id"] for e in old_edges}
        next_edges = [e for e in edges if e["id"] not in old_edge_ids]
        next_edges.append(new_edge)
        next_edges.extend(updated_old_edges)
        flow_json["edges"] = next_edges

    return flow_json


def delete_node(flow_json: dict, node_id: str) -> dict:
    nodes = flow_json.get("nodes", [])
    edges = flow_json.get("edges", [])

    # Find the node to get its slots
    target_node = next((n for n in nodes if n["id"] == node_id), None)
    slot_ids = set()
    if target_node:
        slot_ids = {s["id"] for s in target_node.get("slots", [])}

    # Filter out the node
    flow_json["nodes"] = [n for n in nodes if n["id"] != node_id]

    # Filter out connected edges
    flow_json["edges"] = [
        e
        for e in edges
        if e["source_id"] != node_id
        and e["target_id"] != node_id
        and e["source_id"] not in slot_ids
        and e["target_id"] not in slot_ids
    ]
    return flow_json


def shortcircuit_node(flow_json: dict, node_id: str) -> dict:
    nodes = flow_json.get("nodes", [])
    edges = flow_json.get("edges", [])

    target_node = next((n for n in nodes if n["id"] == node_id), None)
    if not target_node or target_node["node_type"] not in ("STEP", "DEFINER", "LOGICAL_ASSIGNER", "AGENTIC_ASSIGNER"):
        return flow_json  # Can only shortcircuit sequential step-like nodes

    incoming = [e for e in edges if e["target_id"] == node_id]
    outgoing = [e for e in edges if e["source_id"] == node_id]

    # Filter out all edges connected to the node
    next_edges = [e for e in edges if e["source_id"] != node_id and e["target_id"] != node_id]

    if incoming and outgoing:
        # Route first outgoing edge's target to incoming edges
        sorted_outgoing = sorted(outgoing, key=lambda x: str(x["id"]))
        primary_target_id = sorted_outgoing[0]["target_id"]
        primary_target_type = sorted_outgoing[0]["target_type"]

        for inc_edge in incoming:
            re_routed = inc_edge.copy()
            re_routed["target_id"] = primary_target_id
            re_routed["target_type"] = primary_target_type
            next_edges.append(re_routed)

    flow_json["nodes"] = [n for n in nodes if n["id"] != node_id]
    flow_json["edges"] = next_edges
    return flow_json


def rename_node(flow_json: dict, old_id: str, new_id: str) -> dict:
    nodes = flow_json.get("nodes", [])
    edges = flow_json.get("edges", [])

    # Rename node
    for node in nodes:
        if node["id"] == old_id:
            node["id"] = new_id

    # Rename edge references
    for edge in edges:
        if edge["source_id"] == old_id:
            edge["source_id"] = new_id
        if edge["target_id"] == old_id:
            edge["target_id"] = new_id

    return flow_json


def update_node(flow_json: dict, node_id: str, updates: dict) -> dict:
    nodes = flow_json.get("nodes", [])
    edges = flow_json.get("edges", [])

    new_id = updates.get("new_id")
    if new_id and new_id != node_id:
        flow_json = rename_node(flow_json, node_id, new_id)
        node_id = new_id

    for node in nodes:
        if node["id"] == node_id:
            if "is_input" in updates:
                node["is_input"] = updates["is_input"]
                if not updates["is_input"]:
                    flow_json["edges"] = [
                        e for e in edges if not (e["target_id"] == node_id and e["target_handle"] == node_id)
                    ]
            if "is_output" in updates:
                node["is_output"] = updates["is_output"]
                if not updates["is_output"]:
                    flow_json["edges"] = [
                        e for e in edges if not (e["source_id"] == node_id and e["source_handle"] == node_id)
                    ]
            break
    return flow_json


def create_slot(flow_json: dict, node_id: str, index: int) -> dict:
    nodes = flow_json.get("nodes", [])
    for node in nodes:
        if node["id"] == node_id:
            new_slot = {"id": str(uuid.uuid4()), "raw_string": "", "selected": False}
            node.setdefault("slots", []).insert(index, new_slot)
            break
    return flow_json


def update_slot(flow_json: dict, slot_id: str, raw_string: str) -> dict:
    nodes = flow_json.get("nodes", [])
    for node in nodes:
        for slot in node.get("slots", []):
            if slot["id"] == slot_id:
                slot["raw_string"] = raw_string
                return flow_json
    return flow_json


def delete_slot(flow_json: dict, slot_id: str) -> dict:
    nodes = flow_json.get("nodes", [])
    edges = flow_json.get("edges", [])

    for node in nodes:
        slots = node.get("slots", [])
        if any(s["id"] == slot_id for s in slots):
            node["slots"] = [s for s in slots if s["id"] != slot_id]
            break

    flow_json["edges"] = [e for e in edges if e["source_id"] != slot_id and e["target_id"] != slot_id]
    return flow_json


def move_slot(flow_json: dict, slot_id: str, direction: Literal["up", "down", "top", "bottom"]) -> dict:
    nodes = flow_json.get("nodes", [])
    for node in nodes:
        slots = node.get("slots", [])
        idx = next((i for i, s in enumerate(slots) if s["id"] == slot_id), -1)
        if idx != -1:
            target_idx = -1
            if direction == "up" and idx > 0:
                target_idx = idx - 1
            elif direction == "down" and idx < len(slots) - 1:
                target_idx = idx + 1
            elif direction == "top" and idx > 0:
                target_idx = 0
            elif direction == "bottom" and idx < len(slots) - 1:
                target_idx = len(slots) - 1

            if target_idx != -1 and target_idx != idx:
                slot = slots.pop(idx)
                slots.insert(target_idx, slot)
            break
    return flow_json


def delete_edge(flow_json: dict, edge_id: uuid.UUID) -> dict:
    edges = flow_json.get("edges", [])
    edge_str_id = str(edge_id)
    flow_json["edges"] = [e for e in edges if e["id"] != edge_str_id]
    return flow_json


def create_edge(flow_json: dict, source: str, target: str, source_handle: str, target_handle: str) -> dict:
    edges = flow_json.setdefault("edges", [])
    nodes = flow_json.get("nodes", [])

    source_node = next((n for n in nodes if n["id"] == source), None)
    target_node = next((n for n in nodes if n["id"] == target), None)

    source_type = "slot" if (source_node and source_node["node_type"] == "SWITCH") else "node"
    target_type = "node"

    # Map target type if it's connected to a slot of a node
    if target_node:
        is_target_slot = any(s["id"] == target_handle for s in target_node.get("slots", []))
        if is_target_slot:
            target_type = "slot"

    new_edge = {
        "id": str(uuid.uuid4()),
        "source_id": source_handle if source_type == "slot" else source,
        "target_id": target_handle if target_type == "slot" else target,
        "source_handle": source_handle,
        "target_handle": target_handle,
        "source_type": source_type,
        "target_type": target_type,
    }
    edges.append(new_edge)
    return flow_json


def reconnect_edge(
    flow_json: dict,
    edge_id: uuid.UUID,
    source: str,
    target: str,
    source_handle: str,
    target_handle: str,
) -> dict:
    edges = flow_json.get("edges", [])
    edge_str_id = str(edge_id)
    nodes = flow_json.get("nodes", [])

    edge = next((e for e in edges if e["id"] == edge_str_id), None)
    if not edge:
        return flow_json

    source_node = next((n for n in nodes if n["id"] == source), None)
    target_node = next((n for n in nodes if n["id"] == target), None)

    source_type = "slot" if (source_node and source_node["node_type"] == "SWITCH") else "node"
    target_type = "node"

    if target_node:
        is_target_slot = any(s["id"] == target_handle for s in target_node.get("slots", []))
        if is_target_slot:
            target_type = "slot"

    edge["source_id"] = source_handle if source_type == "slot" else source
    edge["target_id"] = target_handle if target_type == "slot" else target
    edge["source_handle"] = source_handle
    edge["target_handle"] = target_handle
    edge["source_type"] = source_type
    edge["target_type"] = target_type

    return flow_json
