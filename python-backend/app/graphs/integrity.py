from __future__ import annotations

from typing import Any

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs.schemas import GraphFlowData


def _find_invalid_state_refs(expr_node: dict[str, Any] | None, valid_keys: set[str]) -> set[str]:
    if not expr_node or not isinstance(expr_node, dict):
        return set()

    invalid = set()
    kind = expr_node.get("kind")
    if kind == "stateRef":
        var_key = expr_node.get("varKey")
        if var_key and var_key not in valid_keys:
            invalid.add(var_key)
    elif kind == "binaryOp":
        invalid.update(_find_invalid_state_refs(expr_node.get("left"), valid_keys))
        invalid.update(_find_invalid_state_refs(expr_node.get("right"), valid_keys))
    elif kind == "unaryOp":
        invalid.update(_find_invalid_state_refs(expr_node.get("expr"), valid_keys))

    return invalid


def assert_flow_is_complete(flow_data: GraphFlowData) -> None:
    """Verifies that the graph is topologically complete and has valid references before execution.

    Raises ValidationError if there are:
      1. Unset expressions in SWITCH node slots.
      2. Unconnected switch slots (no outgoing edge).
      3. Unreachable nodes (no path from START node).
      4. Invalid variable reference targets or expression state references.
    """
    # 1. Check Unset Expressions and Unconnected Slots on SWITCH nodes
    switch_nodes = [n for n in flow_data.nodes if n.node_type == NodeType.SWITCH]
    edge_sources = {e.source_id for e in flow_data.edges}

    for n in switch_nodes:
        for slot in n.slots:
            if slot.expression is None:
                raise ValidationError(f"Switch node '{n.id}' has an unset condition on option '{slot.raw_string}'.")
            if slot.id not in edge_sources:
                raise ValidationError(
                    f"Switch option '{slot.raw_string}' on node '{n.id}' is not connected to any target node."
                )

    # 2. Check reachability of nodes from "start"
    slot_to_node: dict[str, str] = {}
    for n in flow_data.nodes:
        for s in n.slots:
            slot_to_node[s.id] = n.id

    # Build adjacency list: node_id -> set of target node_ids
    adj: dict[str, set[str]] = {n.id: set() for n in flow_data.nodes}
    if "start" not in adj:
        adj["start"] = set()
    if "end" not in adj:
        adj["end"] = set()

    for e in flow_data.edges:
        src_node = slot_to_node.get(e.source_id, e.source_id)
        tgt_node = slot_to_node.get(e.target_id, e.target_id)
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
    for n in flow_data.nodes:
        if n.node_type == NodeType.START:
            continue
        if n.id not in visited:
            raise ValidationError(f"Node '{n.id}' is unreachable from the START node.")

    # 3. Check for invalid variable references
    valid_keys = {var.key for var in flow_data.state if var.key} if flow_data.state else set()

    for n in flow_data.nodes:
        if n.node_type == NodeType.LOGICAL_ASSIGNER:
            for asgn in n.assignments or []:
                if asgn.target_var_key and asgn.target_var_key not in valid_keys:
                    raise ValidationError(
                        f"Invalid assignment target: variable '{asgn.target_var_key}' is missing or deleted."
                    )
                if asgn.expression:
                    invalid_refs = _find_invalid_state_refs(asgn.expression, valid_keys)
                    if invalid_refs:
                        raise ValidationError(
                            f"Invalid state reference: variable '{next(iter(invalid_refs))}' is missing or deleted."
                        )
        elif n.node_type == NodeType.SWITCH:
            for slot in n.slots:
                if slot.expression:
                    invalid_refs = _find_invalid_state_refs(slot.expression, valid_keys)
                    if invalid_refs:
                        raise ValidationError(
                            f"Invalid state reference: variable '{next(iter(invalid_refs))}' is missing or deleted."
                        )
        elif n.node_type == NodeType.AGENTIC_ASSIGNER:
            if not n.prompt or not n.prompt.strip():
                raise ValidationError(f"Agentic Assigner node '{n.id}' has an empty prompt.")
            if not n.agentic_outputs:
                raise ValidationError(f"Agentic Assigner node '{n.id}' must have at least one output variable.")
            if n.agentic_inputs:
                for k in n.agentic_inputs:
                    if k not in valid_keys:
                        raise ValidationError(f"Invalid input reference: variable '{k}' is missing or deleted.")
            if n.agentic_outputs:
                for k in n.agentic_outputs:
                    if k not in valid_keys:
                        raise ValidationError(f"Invalid output target: variable '{k}' is missing or deleted.")
