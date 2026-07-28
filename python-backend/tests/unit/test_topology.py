import uuid

from app.graphs import topology


def test_generate_node_id():
    existing = [{"id": "step_1"}, {"id": "step_2"}, {"id": "switch_1"}]
    assert topology.generate_node_id("STEP", existing) == "step_3"
    assert topology.generate_node_id("SWITCH", existing) == "switch_2"
    assert topology.generate_node_id("NEW_TYPE", existing) == "new_type_1"


def test_add_node_basic():
    flow = {"nodes": [], "edges": [], "operations": {}}
    updated = topology.add_node(flow, "STEP")
    assert len(updated["nodes"]) == 1
    node = updated["nodes"][0]
    assert node["id"] == "step_1"
    assert node["node_type"] == "STEP"
    assert node["is_output"] is True


def test_add_node_switch():
    flow = {"nodes": [], "edges": [], "operations": {}}
    updated = topology.add_node(flow, "SWITCH")
    node = updated["nodes"][0]
    assert node["node_type"] == "SWITCH"
    assert node["is_output"] is False
    assert len(node["slots"]) == 2
    assert node["slots"][0]["id"] == "switch_1_option_a"


def test_add_node_operations():
    flow = {"nodes": [], "edges": [], "operations": {}}
    updated = topology.add_node(flow, "DEFINER")
    assert len(updated["operations"]["definer"]) == 1
    assert updated["operations"]["definer"][0]["id"] == "op_definer_1"

    updated = topology.add_node(updated, "LOGICAL_ASSIGNER")
    assert len(updated["operations"]["logical"]) == 1
    assert updated["operations"]["logical"][0]["id"] == "op_logical_assigner_1"


def test_add_node_with_connector_after():
    flow = {
        "nodes": [
            {"id": "step_1", "node_type": "STEP", "slots": []},
            {"id": "step_2", "node_type": "STEP", "slots": []},
        ],
        "edges": [
            {"id": "edge_1", "source_id": "step_1", "target_id": "step_2", "source_type": "node", "target_type": "node"}
        ],
        "operations": {},
    }
    # Add step_3 after step_1
    updated = topology.add_node(flow, "STEP", connector_id="step_1", direction="after")

    # Needs to split edge: step_1 -> step_3 -> step_2
    assert len(updated["nodes"]) == 3
    new_node_id = "step_3"
    assert any(n["id"] == new_node_id for n in updated["nodes"])

    edges = updated["edges"]
    # We should have two edges now
    assert len(edges) == 2

    # One edge from step_1 to step_3
    edge_1_to_3 = next((e for e in edges if e["source_id"] == "step_1" and e["target_id"] == "step_3"), None)
    assert edge_1_to_3 is not None

    # One edge from step_3 to step_2
    edge_3_to_2 = next((e for e in edges if e["source_id"] == "step_3" and e["target_id"] == "step_2"), None)
    assert edge_3_to_2 is not None


def test_delete_node_protection():
    flow = {
        "nodes": [
            {"id": "start", "node_type": "START", "slots": []},
            {"id": "step_1", "node_type": "STEP", "slots": []},
        ],
        "edges": [],
        "operations": {},
    }
    # Deleting start node should do nothing (sentinel protection)
    updated = topology.delete_node(flow, "start")
    assert len(updated["nodes"]) == 2

    # Deleting step_1 should succeed
    updated = topology.delete_node(updated, "step_1")
    assert len(updated["nodes"]) == 1
    assert updated["nodes"][0]["id"] == "start"


def test_delete_node_cascade_edges_and_ops():
    flow = {
        "nodes": [
            {"id": "step_1", "node_type": "STEP", "slots": []},
            {"id": "switch_1", "node_type": "SWITCH", "slots": [{"id": "switch_1_option_a"}]},
        ],
        "edges": [
            {"id": "e1", "source_id": "step_1", "target_id": "switch_1"},
            {"id": "e2", "source_id": "switch_1_option_a", "target_id": "end"},
        ],
        "operations": {"logical": [{"id": "op_step_1", "assignments": []}]},
    }
    # Link step_1 with operation
    flow["nodes"][0]["ref_id"] = "op_step_1"

    updated = topology.delete_node(flow, "switch_1")
    # Both edges e1 and e2 should be deleted since they link to switch_1 or its slot
    assert len(updated["edges"]) == 0
    assert len(updated["nodes"]) == 1

    updated = topology.delete_node(updated, "step_1")
    # Operation op_step_1 should be removed
    assert len(updated["operations"]["logical"]) == 0


def test_shortcircuit_node():
    flow = {
        "nodes": [
            {"id": "step_1", "node_type": "STEP", "slots": []},
            {"id": "step_2", "node_type": "STEP", "slots": []},
            {"id": "step_3", "node_type": "STEP", "slots": []},
        ],
        "edges": [
            {"id": "e1", "source_id": "step_1", "target_id": "step_2"},
            {"id": "e2", "source_id": "step_2", "target_id": "step_3"},
        ],
    }
    # Shortcircuit step_2 -> step_1 should connect directly to step_3
    updated = topology.shortcircuit_node(flow, "step_2")
    assert len(updated["nodes"]) == 2
    assert len(updated["edges"]) == 1
    edge = updated["edges"][0]
    assert edge["source_id"] == "step_1"
    assert edge["target_id"] == "step_3"


def test_update_node_id_cascades():
    flow = {
        "nodes": [
            {"id": "step_1", "node_type": "STEP", "slots": []},
            {"id": "switch_1", "node_type": "SWITCH", "slots": [{"id": "switch_1_option_a"}]},
        ],
        "edges": [
            {
                "id": "e1",
                "source_id": "step_1",
                "target_id": "switch_1",
                "source_handle": "step_1",
                "target_handle": "switch_1",
            },
            {"id": "e2", "source_id": "switch_1_option_a", "target_id": "end", "source_handle": "switch_1_option_a"},
        ],
    }

    # Rename switch_1 to switch_new
    updated = topology.update_node(flow, "switch_1", new_id="switch_new")
    assert updated["nodes"][1]["id"] == "switch_new"
    assert updated["nodes"][1]["slots"][0]["id"] == "switch_new_option_a"

    e1 = next(e for e in updated["edges"] if e["id"] == "e1")
    assert e1["target_id"] == "switch_new"
    assert e1["target_handle"] == "switch_new"

    e2 = next(e for e in updated["edges"] if e["id"] == "e2")
    assert e2["source_id"] == "switch_new_option_a"
    assert e2["source_handle"] == "switch_new_option_a"


def test_slot_crud_operations():
    flow = {
        "nodes": [{"id": "switch_1", "node_type": "SWITCH", "slots": [{"id": "switch_1_option_a", "raw_string": "a"}]}],
        "edges": [{"id": "e1", "source_id": "switch_1_option_a", "target_id": "end"}],
    }

    # Create slot
    updated = topology.create_slot(flow, "switch_1", index=1)
    slots = updated["nodes"][0]["slots"]
    assert len(slots) == 2
    assert slots[1]["id"] == "switch_1_option_2"
    assert slots[1]["raw_string"] == "option_2"

    # Update slot
    updated = topology.update_slot(
        updated, "switch_1_option_2", raw_string="option_b_updated", expression={"kind": "literal", "value": True}
    )
    assert slots[1]["raw_string"] == "option_b_updated"
    assert slots[1]["expression"] == {"kind": "literal", "value": True}

    # Move slot
    # Move slot 2 to top
    updated = topology.move_slot(updated, "switch_1_option_2", direction="top")
    assert slots[0]["id"] == "switch_1_option_2"

    # Delete slot should also cascade delete connected edge
    # Let's add an edge to the updated slot first
    updated["edges"].append({"id": "e2", "source_id": "switch_1_option_a", "target_id": "end"})
    updated = topology.delete_slot(updated, "switch_1_option_a")
    assert len(updated["nodes"][0]["slots"]) == 1
    assert len(updated["edges"]) == 0


def test_edge_crud_operations():
    flow = {
        "nodes": [
            {"id": "step_1", "node_type": "STEP", "slots": []},
            {"id": "step_2", "node_type": "STEP", "slots": []},
            {"id": "switch_1", "node_type": "SWITCH", "slots": [{"id": "switch_1_option_a"}]},
        ],
        "edges": [],
    }

    # Create edge step_1 -> step_2
    updated = topology.create_edge(
        flow, source="step_1", target="step_2", source_handle="step_1", target_handle="step_2"
    )
    assert len(updated["edges"]) == 1
    edge = updated["edges"][0]
    assert edge["source_type"] == "node"
    assert edge["target_type"] == "node"

    # Create edge from switch slot: switch_1_option_a -> step_2
    updated = topology.create_edge(
        updated, source="switch_1", target="step_2", source_handle="switch_1_option_a", target_handle="step_2"
    )
    assert len(updated["edges"]) == 2
    edge2 = updated["edges"][1]
    assert edge2["source_type"] == "slot"
    assert edge2["source_id"] == "switch_1_option_a"

    # Reconnect edge
    edge_id = uuid.UUID(edge["id"])
    updated = topology.reconnect_edge(
        updated, edge_id, source="step_1", target="switch_1", source_handle="step_1", target_handle="switch_1"
    )
    assert edge["target_id"] == "switch_1"
    assert edge["target_type"] == "node"

    # Delete edge
    updated = topology.delete_edge(updated, edge_id)
    assert len(updated["edges"]) == 1
