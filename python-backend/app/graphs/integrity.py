from __future__ import annotations

from typing import Any

from app.exceptions import ValidationError
from app.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    StartNode,
)


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
    """Verifies that the graph is topologically complete and has valid references before execution."""
    edge_sources = {e.source_id for e in flow_data.edges}

    # Filter out synthetic nodes (starting with __)
    user_nodes = [n for n in flow_data.nodes if not n.id.startswith("__")]

    # 1. Check Unset Expressions and Unconnected Slots on routing nodes
    for n in user_nodes:
        if isinstance(n, LogicalSwitchNode):
            for slot in n.slots:
                if slot.expression is None:
                    raise ValidationError(
                        f"Logical Switch node '{n.id}' has an unset condition on option '{slot.raw_string}'."
                    )
                if slot.id not in edge_sources:
                    raise ValidationError(
                        f"Logical Switch option '{slot.raw_string}' on node '{n.id}' is not connected to any target node."
                    )
        elif isinstance(n, AgenticSwitchNode):
            for slot in n.slots:
                if slot.id not in edge_sources:
                    raise ValidationError(
                        f"Agentic Switch option '{slot.raw_string}' on node '{n.id}' is not connected to any target node."
                    )

    # 2. Check reachability of nodes from "start"
    slot_to_node: dict[str, str] = {}
    for node_item in user_nodes:
        if hasattr(node_item, "slots"):
            for s in getattr(node_item, "slots", []):
                slot_to_node[s.id] = node_item.id

    # Build adjacency list: node_id -> set of target node_ids
    adj: dict[str, set[str]] = {n.id: set() for n in user_nodes}
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
    for node_item in user_nodes:
        if isinstance(node_item, StartNode):
            continue
        if node_item.id not in visited:
            raise ValidationError(f"Node '{node_item.id}' is unreachable from the START node.")

    # 3. Check for invalid variable references
    valid_keys = {var.key for var in flow_data.state if var.key} if flow_data.state else set()

    for node_item in user_nodes:
        if isinstance(node_item, LogicalAssignerNode):
            for asgn in node_item.assignments:
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
        elif isinstance(node_item, LogicalSwitchNode):
            for slot in node_item.slots:
                if slot.expression:
                    invalid_refs = _find_invalid_state_refs(slot.expression, valid_keys)
                    if invalid_refs:
                        raise ValidationError(
                            f"Invalid state reference: variable '{next(iter(invalid_refs))}' is missing or deleted."
                        )
        elif isinstance(node_item, (AgenticAssignerNode, AgenticSwitchNode)):
            if isinstance(node_item, AgenticAssignerNode):
                if not node_item.prompt or not node_item.prompt.strip():
                    raise ValidationError(f"Node '{node_item.id}' has an empty prompt.")
                if not node_item.agentic_outputs:
                    raise ValidationError(
                        f"Agentic Assigner node '{node_item.id}' must have at least one output variable."
                    )
            if node_item.agentic_inputs:
                for k in node_item.agentic_inputs:
                    if k not in valid_keys:
                        raise ValidationError(f"Invalid input reference: variable '{k}' is missing or deleted.")
            if isinstance(node_item, AgenticAssignerNode) and node_item.agentic_outputs:
                for k in node_item.agentic_outputs:
                    if k not in valid_keys:
                        raise ValidationError(f"Invalid output target: variable '{k}' is missing or deleted.")
        elif isinstance(node_item, InterruptNode):
            if not node_item.resume_var or node_item.resume_var not in valid_keys:
                raise ValidationError(f"Interrupt node '{node_item.id}' must have a valid resume_var.")
            for k in node_item.payload_vars:
                if k not in valid_keys:
                    raise ValidationError(f"Interrupt node '{node_item.id}' payload variable '{k}' is missing.")
