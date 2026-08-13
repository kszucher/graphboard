from __future__ import annotations

from app.exceptions import ValidationError
from app.graphs.nodes import StartNode
from app.graphs.schemas import GraphFlowData
from app.graphs.variables import get_node_variable_references


def assert_flow_is_complete(flow_data: GraphFlowData) -> None:
    """Verifies that the graph is topologically complete and has valid references before execution."""
    edge_sources = {(e.source, e.source_handle) for e in flow_data.edges if e.source_handle}

    user_nodes = flow_data.nodes

    # 1. Check Unset Expressions and Unconnected Slots on routing nodes
    for n in user_nodes:
        n.validate_integrity(edge_sources)

    # 2. Check reachability of nodes from "start"
    # Build adjacency list: node_id -> set of target node_ids
    adj: dict[str, set[str]] = {n.id: set() for n in user_nodes}
    if "start" not in adj:
        adj["start"] = set()
    if "end" not in adj:
        adj["end"] = set()

    for e in flow_data.edges:
        src_node = e.source
        tgt_node = e.target
        if src_node in adj:
            adj[src_node].add(tgt_node)

    # Traverse from "start"
    visited = set()

    def dfs(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        for nxt in adj.get(node_id, []):
            dfs(nxt)

    if "start" in adj:
        dfs("start")

    # START node is excluded from reachability checks
    for node_item in user_nodes:
        if isinstance(node_item, StartNode):
            continue
        if node_item.id not in visited:
            raise ValidationError(f"Node '{node_item.id}' is unreachable from the START node.")

    # 3. Check for invalid variable references
    valid_keys = {var.key for var in flow_data.state if var.key} if flow_data.state else set()
    for node_item in user_nodes:
        # Check for missing state variables centrally
        node_refs = get_node_variable_references(node_item, flow_data.expressions)
        invalid_refs = node_refs - valid_keys
        if invalid_refs:
            raise ValidationError(
                f"Invalid variable reference on node '{node_item.id}': variable(s) {', '.join(sorted(invalid_refs))} missing or deleted."
            )
