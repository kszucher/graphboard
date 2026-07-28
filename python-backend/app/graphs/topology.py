import uuid

SENTINEL_NODE_TYPES = {"START", "END", "DEFINER"}
SEQUENTIAL_STEP_TYPES = {"STEP", "LOGICAL_ASSIGNER", "AGENTIC_ASSIGNER"}


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
    ops = flow_json.setdefault("operations", {"definer": [], "agentic": [], "logical": [], "switch": []})
    node_id = generate_node_id(node_type, nodes)

    slots = []
    ref_id = None
    if node_type == "SWITCH":
        slots = [
            {"id": f"{node_id}_option_a", "raw_string": "option_a", "selected": False},
            {"id": f"{node_id}_option_b", "raw_string": "option_b", "selected": False},
        ]
    elif node_type == "DEFINER":
        ref_id = f"op_{node_id}"
        ops.setdefault("definer", []).append({"id": ref_id, "variables": []})

    new_node = {
        "id": node_id,
        "node_type": node_type,
        "ref_id": ref_id,
        "is_input": True,
        "is_output": node_type in ("STEP", "DEFINER", "LOGICAL_ASSIGNER", "AGENTIC_ASSIGNER"),
        "slots": slots,
        "code": "",
        "selected": False,
    }
    nodes.append(new_node)

    if connector_id and direction:
        is_after = direction == "after"
        old_edges = [
            e for e in edges if (e.get("source_id") == connector_id if is_after else e.get("target_id") == connector_id)
        ]

        to_slot_id = node_id
        from_slot_id = slots[0]["id"] if (node_type == "SWITCH" and slots) else node_id

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
    ops = flow_json.get("operations", {})

    target_node = next((n for n in nodes if n["id"] == node_id), None)
    if not target_node:
        return flow_json

    # Sentinel protection: START, END, DEFINER nodes cannot be deleted
    if target_node.get("node_type") in SENTINEL_NODE_TYPES:
        return flow_json

    ref_id = target_node.get("ref_id")
    if ref_id and ops:
        for op_type in ("definer", "agentic", "logical", "switch"):
            if op_type in ops:
                ops[op_type] = [o for o in ops[op_type] if o.get("id") != ref_id]

    slot_ids = {s["id"] for s in target_node.get("slots", [])}

    flow_json["nodes"] = [n for n in nodes if n["id"] != node_id]
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
    if not target_node or target_node["node_type"] not in SEQUENTIAL_STEP_TYPES:
        return flow_json  # START, END, DEFINER, SWITCH nodes cannot be shortcircuited

    incoming = [e for e in edges if e["target_id"] == node_id]
    outgoing = [e for e in edges if e["source_id"] == node_id]

    next_edges = [e for e in edges if e["source_id"] != node_id and e["target_id"] != node_id]

    if incoming and outgoing:
        for inc in incoming:
            for out in outgoing:
                next_edges.append(
                    {
                        "id": str(uuid.uuid4()),
                        "source_id": inc["source_id"],
                        "target_id": out["target_id"],
                        "source_handle": inc.get("source_handle", inc["source_id"]),
                        "target_handle": out.get("target_handle", out["target_id"]),
                        "source_type": inc.get("source_type", "node"),
                        "target_type": out.get("target_type", "node"),
                    }
                )

    flow_json["nodes"] = [n for n in nodes if n["id"] != node_id]
    flow_json["edges"] = next_edges
    return flow_json


def update_node(
    flow_json: dict,
    node_id: str,
    new_id: str | None = None,
    is_input: bool | None = None,
    is_output: bool | None = None,
    ref_id: str | None = None,
) -> dict:
    nodes = flow_json.get("nodes", [])
    edges = flow_json.get("edges", [])

    target_node = next((n for n in nodes if n["id"] == node_id), None)
    if not target_node:
        return flow_json

    if new_id and new_id != node_id:
        target_node["id"] = new_id
        for slot in target_node.get("slots", []):
            if slot["id"].startswith(f"{node_id}_"):
                slot["id"] = slot["id"].replace(f"{node_id}_", f"{new_id}_", 1)

        for edge in edges:
            if edge["source_id"] == node_id:
                edge["source_id"] = new_id
            elif edge["source_id"].startswith(f"{node_id}_"):
                edge["source_id"] = edge["source_id"].replace(f"{node_id}_", f"{new_id}_", 1)

            if edge["target_id"] == node_id:
                edge["target_id"] = new_id
            elif edge["target_id"].startswith(f"{node_id}_"):
                edge["target_id"] = edge["target_id"].replace(f"{node_id}_", f"{new_id}_", 1)

            if edge.get("source_handle") == node_id:
                edge["source_handle"] = new_id
            elif edge.get("source_handle", "").startswith(f"{node_id}_"):
                edge["source_handle"] = edge["source_handle"].replace(f"{node_id}_", f"{new_id}_", 1)

            if edge.get("target_handle") == node_id:
                edge["target_handle"] = new_id
            elif edge.get("target_handle", "").startswith(f"{node_id}_"):
                edge["target_handle"] = edge["target_handle"].replace(f"{node_id}_", f"{new_id}_", 1)

    if is_input is not None:
        target_node["is_input"] = is_input
    if is_output is not None:
        target_node["is_output"] = is_output
    if ref_id is not None:
        target_node["ref_id"] = ref_id

    return flow_json


def create_slot(flow_json: dict, node_id: str, index: int) -> dict:
    nodes = flow_json.get("nodes", [])
    target_node = next((n for n in nodes if n["id"] == node_id), None)
    if not target_node:
        return flow_json

    slots = target_node.setdefault("slots", [])
    slot_count = len(slots) + 1
    new_slot_id = f"{node_id}_option_{slot_count}"
    new_slot = {
        "id": new_slot_id,
        "raw_string": f"option_{slot_count}",
        "selected": False,
    }

    insert_idx = max(0, min(index, len(slots)))
    slots.insert(insert_idx, new_slot)
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


def move_slot(flow_json: dict, slot_id: str, direction: str) -> dict:
    nodes = flow_json.get("nodes", [])
    for node in nodes:
        slots = node.get("slots", [])
        idx = next((i for i, s in enumerate(slots) if s["id"] == slot_id), -1)
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
