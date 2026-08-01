import uuid

from app.constants import NodeType
from app.graphs import topology
from app.graphs.schemas import (
    EdgeRead,
    GraphFlowData,
    NodeRead,
    SlotRead,
)


def test_generate_node_id() -> None:
    existing = [
        NodeRead(id="logical_assigner_1", node_type=NodeType.LOGICAL_ASSIGNER),
        NodeRead(id="logical_assigner_2", node_type=NodeType.LOGICAL_ASSIGNER),
        NodeRead(id="switch_1", node_type=NodeType.SWITCH),
    ]
    assert topology.generate_node_id(NodeType.LOGICAL_ASSIGNER, existing) == "logical_assigner_3"
    assert topology.generate_node_id(NodeType.SWITCH, existing) == "switch_2"
    assert topology.generate_node_id("NEW_TYPE", existing) == "new_type_1"


def test_add_node_basic() -> None:
    flow = GraphFlowData(nodes=[], edges=[])
    updated = topology.add_node(flow, NodeType.LOGICAL_ASSIGNER)
    assert len(updated.nodes) == 1
    node = updated.nodes[0]
    assert node.id == "logical_assigner_1"
    assert node.node_type == NodeType.LOGICAL_ASSIGNER


def test_add_node_switch() -> None:
    flow = GraphFlowData(nodes=[], edges=[])
    updated = topology.add_node(flow, NodeType.SWITCH)
    node = updated.nodes[0]
    assert node.node_type == NodeType.SWITCH
    assert len(node.slots) == 2
    assert node.slots[0].id == "switch_1_option_a"


def test_add_node_operations() -> None:
    flow = GraphFlowData(nodes=[], edges=[])
    updated = topology.add_node(flow, NodeType.LOGICAL_ASSIGNER)
    assert updated.nodes[0].assignments == []


def test_add_node_with_connector_after() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="logical_assigner_1", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
            NodeRead(id="logical_assigner_2", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
        ],
        edges=[
            EdgeRead(id=uuid.uuid4(), source_id="logical_assigner_1", target_id="logical_assigner_2", source_type="node", target_type="node")
        ],
    )
    # Add logical_assigner_3 after logical_assigner_1
    updated = topology.add_node(flow, NodeType.LOGICAL_ASSIGNER, connector_id="logical_assigner_1", direction="after")

    # Needs to split edge: logical_assigner_1 -> logical_assigner_3 -> logical_assigner_2
    assert len(updated.nodes) == 3
    new_node_id = "logical_assigner_3"
    assert any(n.id == new_node_id for n in updated.nodes)

    edges = updated.edges
    # We should have two edges now
    assert len(edges) == 2

    # One edge from logical_assigner_1 to logical_assigner_3
    edge_1_to_3 = next((e for e in edges if e.source_id == "logical_assigner_1" and e.target_id == "logical_assigner_3"), None)
    assert edge_1_to_3 is not None

    # One edge from logical_assigner_3 to logical_assigner_2
    edge_3_to_2 = next((e for e in edges if e.source_id == "logical_assigner_3" and e.target_id == "logical_assigner_2"), None)
    assert edge_3_to_2 is not None


def test_delete_node_protection() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="start", node_type=NodeType.START, slots=[]),
            NodeRead(id="logical_assigner_1", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
        ],
        edges=[],
    )
    # Deleting start node should do nothing (sentinel protection)
    updated = topology.delete_node(flow, "start")
    assert len(updated.nodes) == 2

    # Deleting logical_assigner_1 should succeed
    updated = topology.delete_node(updated, "logical_assigner_1")
    assert len(updated.nodes) == 1
    assert updated.nodes[0].id == "start"


def test_delete_node_cascade_edges_and_ops() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="logical_assigner_1", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
            NodeRead(id="switch_1", node_type=NodeType.SWITCH, slots=[SlotRead(id="switch_1_option_a")]),
        ],
        edges=[
            EdgeRead(id=uuid.uuid4(), source_id="logical_assigner_1", target_id="switch_1"),
            EdgeRead(id=uuid.uuid4(), source_id="switch_1_option_a", target_id="end"),
        ],
    )

    updated = topology.delete_node(flow, "switch_1")
    # Both edges should be deleted since they link to switch_1 or its slot
    assert len(updated.edges) == 0
    assert len(updated.nodes) == 1

    updated = topology.delete_node(updated, "logical_assigner_1")
    assert len(updated.nodes) == 0


def test_shortcircuit_node() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="logical_assigner_1", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
            NodeRead(id="logical_assigner_2", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
            NodeRead(id="logical_assigner_3", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
        ],
        edges=[
            EdgeRead(id=uuid.uuid4(), source_id="logical_assigner_1", target_id="logical_assigner_2"),
            EdgeRead(id=uuid.uuid4(), source_id="logical_assigner_2", target_id="logical_assigner_3"),
        ],
    )
    # Shortcircuit logical_assigner_2 -> logical_assigner_1 should connect directly to logical_assigner_3
    updated = topology.shortcircuit_node(flow, "logical_assigner_2")
    assert len(updated.nodes) == 2
    assert len(updated.edges) == 1
    edge = updated.edges[0]
    assert edge.source_id == "logical_assigner_1"
    assert edge.target_id == "logical_assigner_3"


def test_update_node_id_cascades() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="logical_assigner_1", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
            NodeRead(id="switch_1", node_type=NodeType.SWITCH, slots=[SlotRead(id="switch_1_option_a")]),
        ],
        edges=[
            EdgeRead(id=uuid.uuid4(), source_id="logical_assigner_1", target_id="switch_1"),
            EdgeRead(id=uuid.uuid4(), source_id="switch_1_option_a", target_id="end"),
        ],
    )

    # Rename switch_1 to switch_new
    updated = topology.update_node(flow, "switch_1", new_id="switch_new")
    assert updated.nodes[1].id == "switch_new"
    assert updated.nodes[1].slots[0].id == "switch_new_option_a"

    assert updated.edges[0].target_id == "switch_new"
    assert updated.edges[1].source_id == "switch_new_option_a"


def test_slot_crud_operations() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="switch_1", node_type=NodeType.SWITCH, slots=[SlotRead(id="switch_1_option_a", raw_string="a")])
        ],
        edges=[EdgeRead(id=uuid.uuid4(), source_id="switch_1_option_a", target_id="end")],
    )

    # Create slot
    updated = topology.create_slot(flow, "switch_1", index=1)
    slots = updated.nodes[0].slots
    assert len(slots) == 2
    assert slots[1].id == "switch_1_option_2"
    assert slots[1].raw_string == "option_2"

    # Update slot
    updated = topology.update_slot(
        updated, "switch_1_option_2", raw_string="option_b_updated", expression={"kind": "literal", "value": True}
    )
    assert slots[1].raw_string == "option_b_updated"
    assert slots[1].expression == {"kind": "literal", "value": True}

    # Move slot
    # Move slot 2 to top
    updated = topology.move_slot(updated, "switch_1_option_2", direction="top")
    assert slots[0].id == "switch_1_option_2"

    # Delete slot should also cascade delete connected edge
    updated.edges.append(EdgeRead(id=uuid.uuid4(), source_id="switch_1_option_a", target_id="end"))
    updated = topology.delete_slot(updated, "switch_1_option_a")
    assert len(updated.nodes[0].slots) == 1
    assert len(updated.edges) == 0


def test_edge_crud_operations() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="logical_assigner_1", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
            NodeRead(id="logical_assigner_2", node_type=NodeType.LOGICAL_ASSIGNER, slots=[]),
            NodeRead(id="switch_1", node_type=NodeType.SWITCH, slots=[SlotRead(id="switch_1_option_a")]),
        ],
        edges=[],
    )

    # Create edge logical_assigner_1 -> logical_assigner_2
    updated = topology.create_edge(
        flow, source="logical_assigner_1", target="logical_assigner_2", source_handle="logical_assigner_1", target_handle="logical_assigner_2"
    )
    assert len(updated.edges) == 1
    edge = updated.edges[0]
    assert edge.source_type == "node"
    assert edge.target_type == "node"

    # Create edge from switch slot: switch_1_option_a -> logical_assigner_2
    updated = topology.create_edge(
        updated, source="switch_1", target="logical_assigner_2", source_handle="switch_1_option_a", target_handle="logical_assigner_2"
    )
    assert len(updated.edges) == 2
    edge2 = updated.edges[1]
    assert edge2.source_type == "slot"
    assert edge2.source_id == "switch_1_option_a"

    # Reconnect edge
    edge_id = edge.id
    updated = topology.reconnect_edge(
        updated, edge_id, source="logical_assigner_1", target="switch_1", source_handle="logical_assigner_1", target_handle="switch_1"
    )
    assert edge.target_id == "switch_1"
    assert edge.target_type == "node"

    # Delete edge
    updated = topology.delete_edge(updated, edge_id)
    assert len(updated.edges) == 1
