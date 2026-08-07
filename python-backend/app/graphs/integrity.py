from __future__ import annotations

from app.exceptions import ValidationError
from app.graphs.nodes import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    InterruptNode,
    LogicalSwitchNode,
    StartNode,
)
from app.graphs.schemas import (
    GraphFlowData,
)


def assert_flow_is_complete(flow_data: GraphFlowData) -> None:
    """Verifies that the graph is topologically complete and has valid references before execution."""
    edge_sources = {(e.source, e.source_handle) for e in flow_data.edges if e.source_handle}

    user_nodes = flow_data.nodes

    # 1. Check Unset Expressions and Unconnected Slots on routing nodes
    for n in user_nodes:
        if isinstance(n, LogicalSwitchNode):
            for slot in n.slots:
                if slot.expression is None:
                    raise ValidationError(
                        f"Logical Switch node '{n.id}' has an unset condition on option '{slot.raw_string}'."
                    )
                if (n.id, slot.id) not in edge_sources:
                    raise ValidationError(
                        f"Logical Switch option '{slot.raw_string}' on node '{n.id}' is not connected to any target node."
                    )
        elif isinstance(n, AgenticSwitchNode):
            for aslot in n.slots:
                if (n.id, aslot.id) not in edge_sources:
                    raise ValidationError(
                        f"Agentic Switch option '{aslot.raw_string}' on node '{n.id}' is not connected to any target node."
                    )

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
        # Generic polymorphic check for missing state variables
        invalid_refs = node_item.get_variable_references() - valid_keys
        if invalid_refs:
            raise ValidationError(
                f"Invalid variable reference on node '{node_item.id}': variable(s) {', '.join(sorted(invalid_refs))} missing or deleted."
            )

        # Specific structural checks
        if isinstance(node_item, AgenticAssignerNode):
            if not node_item.prompt or not node_item.prompt.strip():
                raise ValidationError(f"Node '{node_item.id}' has an empty prompt.")
            if not node_item.agentic_outputs:
                raise ValidationError(f"Agentic Assigner node '{node_item.id}' must have at least one output variable.")
        elif isinstance(node_item, InterruptNode):
            if not node_item.resume_var:
                raise ValidationError(f"Interrupt node '{node_item.id}' must have a valid resume_var.")
