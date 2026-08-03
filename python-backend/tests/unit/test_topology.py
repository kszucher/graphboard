import uuid

from app.constants import NodeType
from app.graphs import topology
from app.graphs.schemas import (
    EdgeRead,
    GraphFlowData,
    LogicalAssignerNode,
    LogicalSwitchNode,
    SlotRead,
    StartNode,
)


def test_generate_node_id() -> None:
    existing = [
        LogicalAssignerNode(id="logical_assigner_1"),
        LogicalAssignerNode(id="logical_assigner_2"),
        LogicalSwitchNode(id="logical_switch_1"),
    ]
    assert topology.generate_node_id(NodeType.LOGICAL_ASSIGNER, existing) == "logical_assigner_3"
    assert topology.generate_node_id(NodeType.LOGICAL_SWITCH, existing) == "logical_switch_2"
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
    updated = topology.add_node(flow, NodeType.LOGICAL_SWITCH)
    node = updated.nodes[0]
    assert node.node_type == NodeType.LOGICAL_SWITCH
    assert isinstance(node, LogicalSwitchNode)
    assert len(node.slots) == 2
    assert node.slots[0].id == "logical_switch_1_option_a"


def test_add_node_operations() -> None:
    flow = GraphFlowData(nodes=[], edges=[])
    updated = topology.add_node(flow, NodeType.LOGICAL_ASSIGNER)
    node = updated.nodes[0]
    assert isinstance(node, LogicalAssignerNode)
    assert node.assignments == []


def test_add_node_with_connector_after() -> None:
    flow = GraphFlowData(
        nodes=[
            LogicalAssignerNode(id="logical_assigner_1"),
            LogicalAssignerNode(id="logical_assigner_2"),
        ],
        edges=[
            EdgeRead(
                id=uuid.uuid4(),
                source_id="logical_assigner_1",
                target_id="logical_assigner_2",
                source_type="node",
                target_type="node",
            )
        ],
    )
    updated = topology.add_node(flow, NodeType.LOGICAL_ASSIGNER, connector_id="logical_assigner_1", direction="after")
    assert len(updated.nodes) == 3
    new_node_id = "logical_assigner_3"
    assert any(n.id == new_node_id for n in updated.nodes)

    edges = updated.edges
    assert len(edges) == 2

    edge_1_to_3 = next(
        (e for e in edges if e.source_id == "logical_assigner_1" and e.target_id == "logical_assigner_3"), None
    )
    assert edge_1_to_3 is not None

    edge_3_to_2 = next(
        (e for e in edges if e.source_id == "logical_assigner_3" and e.target_id == "logical_assigner_2"), None
    )
    assert edge_3_to_2 is not None


def test_delete_node_protection() -> None:
    flow = GraphFlowData(
        nodes=[
            StartNode(id="start"),
            LogicalAssignerNode(id="logical_assigner_1"),
        ],
        edges=[],
    )
    updated = topology.delete_node(flow, "start")
    assert len(updated.nodes) == 2

    updated = topology.delete_node(updated, "logical_assigner_1")
    assert len(updated.nodes) == 1
    assert updated.nodes[0].id == "start"


def test_delete_node_cascade_edges_and_ops() -> None:
    flow = GraphFlowData(
        nodes=[
            LogicalAssignerNode(id="logical_assigner_1"),
            LogicalSwitchNode(id="logical_switch_1", slots=[SlotRead(id="logical_switch_1_option_a")]),
        ],
        edges=[
            EdgeRead(id=uuid.uuid4(), source_id="logical_assigner_1", target_id="logical_switch_1"),
            EdgeRead(id=uuid.uuid4(), source_id="logical_switch_1_option_a", target_id="end"),
        ],
    )

    updated = topology.delete_node(flow, "logical_switch_1")
    assert len(updated.edges) == 0
    assert len(updated.nodes) == 1

    updated = topology.delete_node(updated, "logical_assigner_1")
    assert len(updated.nodes) == 0


def test_shortcircuit_node() -> None:
    flow = GraphFlowData(
        nodes=[
            LogicalAssignerNode(id="logical_assigner_1"),
            LogicalAssignerNode(id="logical_assigner_2"),
            LogicalAssignerNode(id="logical_assigner_3"),
        ],
        edges=[
            EdgeRead(id=uuid.uuid4(), source_id="logical_assigner_1", target_id="logical_assigner_2"),
            EdgeRead(id=uuid.uuid4(), source_id="logical_assigner_2", target_id="logical_assigner_3"),
        ],
    )
    updated = topology.shortcircuit_node(flow, "logical_assigner_2")
    assert len(updated.nodes) == 2
    assert len(updated.edges) == 1
    edge = updated.edges[0]
    assert edge.source_id == "logical_assigner_1"
    assert edge.target_id == "logical_assigner_3"


def test_update_node_id_cascades() -> None:
    flow = GraphFlowData(
        nodes=[
            LogicalAssignerNode(id="logical_assigner_1"),
            LogicalSwitchNode(id="logical_switch_1", slots=[SlotRead(id="logical_switch_1_option_a")]),
        ],
        edges=[
            EdgeRead(id=uuid.uuid4(), source_id="logical_assigner_1", target_id="logical_switch_1"),
            EdgeRead(id=uuid.uuid4(), source_id="logical_switch_1_option_a", target_id="end"),
        ],
    )

    updated = topology.update_node(flow, "logical_switch_1", new_id="switch_new")
    assert updated.nodes[1].id == "switch_new"
    switch_node = updated.nodes[1]
    assert isinstance(switch_node, LogicalSwitchNode)
    assert switch_node.slots[0].id == "switch_new_option_a"

    assert updated.edges[0].target_id == "switch_new"
    assert updated.edges[1].source_id == "switch_new_option_a"


def test_slot_crud_operations() -> None:
    flow = GraphFlowData(
        nodes=[
            LogicalSwitchNode(id="logical_switch_1", slots=[SlotRead(id="logical_switch_1_option_a", raw_string="a")])
        ],
        edges=[EdgeRead(id=uuid.uuid4(), source_id="logical_switch_1_option_a", target_id="end")],
    )

    updated = topology.create_slot(flow, "logical_switch_1", index=1)
    switch_node = updated.nodes[0]
    assert isinstance(switch_node, LogicalSwitchNode)
    slots = switch_node.slots
    assert len(slots) == 2
    assert slots[1].id == "logical_switch_1_option_2"
    assert slots[1].raw_string == "option_2"

    updated = topology.update_slot(
        updated,
        "logical_switch_1_option_2",
        raw_string="option_b_updated",
        expression={"kind": "literal", "value": True},
    )
    assert slots[1].raw_string == "option_b_updated"
    assert slots[1].expression == {"kind": "literal", "value": True}

    updated = topology.move_slot(updated, "logical_switch_1_option_2", direction="top")
    assert slots[0].id == "logical_switch_1_option_2"

    updated.edges.append(EdgeRead(id=uuid.uuid4(), source_id="logical_switch_1_option_a", target_id="end"))
    updated = topology.delete_slot(updated, "logical_switch_1_option_a")
    assert len(switch_node.slots) == 1
    assert len(updated.edges) == 0


def test_edge_crud_operations() -> None:
    flow = GraphFlowData(
        nodes=[
            LogicalAssignerNode(id="logical_assigner_1"),
            LogicalAssignerNode(id="logical_assigner_2"),
            LogicalSwitchNode(id="logical_switch_1", slots=[SlotRead(id="logical_switch_1_option_a")]),
        ],
        edges=[],
    )

    updated = topology.create_edge(
        flow,
        source="logical_assigner_1",
        target="logical_assigner_2",
        source_handle="logical_assigner_1",
        target_handle="logical_assigner_2",
    )
    assert len(updated.edges) == 1
    edge = updated.edges[0]
    assert edge.source_type == "node"
    assert edge.target_type == "node"

    updated = topology.create_edge(
        updated,
        source="logical_switch_1",
        target="logical_assigner_2",
        source_handle="logical_switch_1_option_a",
        target_handle="logical_assigner_2",
    )
    assert len(updated.edges) == 2
    edge2 = updated.edges[1]
    assert edge2.source_type == "slot"
    assert edge2.source_id == "logical_switch_1_option_a"

    edge_id = edge.id
    updated = topology.reconnect_edge(
        updated,
        edge_id,
        source="logical_assigner_1",
        target="logical_switch_1",
        source_handle="logical_assigner_1",
        target_handle="logical_switch_1",
    )
    assert edge.target_id == "logical_switch_1"
    assert edge.target_type == "node"

    updated = topology.delete_edge(updated, edge_id)
    assert len(updated.edges) == 1


def test_agentic_switch_topology_operations() -> None:
    flow = GraphFlowData(
        nodes=[
            LogicalAssignerNode(id="assigner_1"),
            LogicalAssignerNode(id="assigner_2"),
        ],
        edges=[
            EdgeRead(id=uuid.uuid4(), source_id="assigner_1", target_id="assigner_2"),
        ],
    )

    # Test inserting AGENTIC_SWITCH after an edge
    updated = topology.add_node(
        flow,
        node_type=NodeType.AGENTIC_SWITCH,
        connector_id="assigner_1",
        direction="after",
    )
    switch_node = next(n for n in updated.nodes if n.node_type == NodeType.AGENTIC_SWITCH)
    assert switch_node is not None
    # Edge from assigner_1 -> AGENTIC_SWITCH
    edge_in = next(e for e in updated.edges if e.target_id == switch_node.id)
    assert edge_in.source_id == "assigner_1"
    # Edge from AGENTIC_SWITCH first slot -> assigner_2
    edge_out = next(e for e in updated.edges if e.target_id == "assigner_2")
    assert edge_out.source_type == "slot"
    assert edge_out.source_id == switch_node.slots[0].id

    # Test create edge from AGENTIC_SWITCH slot
    updated = topology.create_edge(
        updated,
        source=switch_node.id,
        target="assigner_1",
        source_handle=switch_node.slots[1].id,
        target_handle="assigner_1",
    )
    new_edge = updated.edges[-1]
    assert new_edge.source_type == "slot"
    assert new_edge.source_id == switch_node.slots[1].id
