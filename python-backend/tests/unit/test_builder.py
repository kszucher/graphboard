from app.constants import NodeType
from app.graphs.builder import GraphBuilder
from app.graphs.mutations import apply_patch
from app.graphs.schemas import (
    ConnectOp,
    GraphFlowData,
    UpsertNodeOp,
    UpsertStateVarOp,
)


def test_graph_builder_flow() -> None:
    b = GraphBuilder()
    b.state("x", "number", 10)

    start = b.start_chain("start_node", NodeType.START)
    start.then_node("end_node", NodeType.END)

    assert len(b.patch) == 4
    assert isinstance(b.patch[0], UpsertStateVarOp)
    assert isinstance(b.patch[1], UpsertNodeOp)
    assert isinstance(b.patch[2], UpsertNodeOp)
    assert isinstance(b.patch[3], ConnectOp)

    # Verify we can execute it transactionally
    flow = GraphFlowData(nodes=[], edges=[])
    updated = apply_patch(flow, b.patch)
    assert len(updated.state) == 1
    assert len(updated.nodes) == 2
    assert len(updated.edges) == 1
    assert updated.edges[0].source_id == "start_node"
    assert updated.edges[0].target_id == "end_node"
