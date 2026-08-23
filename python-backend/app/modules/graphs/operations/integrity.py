from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.core.exceptions import ValidationError
from app.modules.graphs.operations.variables import get_node_variable_references
from app.modules.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    RagRetrieverNode,
    StartNode,
)


def is_type_compatible(var_type: str, val: Any) -> bool:
    """Verifies that a literal value conforms to the declared variable type."""
    match var_type:
        case "number":
            return isinstance(val, (int, float)) and not isinstance(val, bool)
        case "string":
            return isinstance(val, str)
        case "boolean":
            return isinstance(val, bool)
        case "array":
            return isinstance(val, list)
        case "object":
            return isinstance(val, dict)
        case _:
            return True


def assert_flow_is_complete(flow_data: GraphFlowData) -> None:
    """Verifies that the graph is topologically complete, type-safe, and referentially sound before execution."""
    # ---------------------------------------------------------
    # 1. State Variables Integrity & Soundness
    # ---------------------------------------------------------
    valid_vars = {v.key: v for v in flow_data.state if v.key}
    var_keys_list = [v.key for v in flow_data.state]

    if len(var_keys_list) != len(valid_vars):
        raise ValidationError("Duplicate state variable keys detected in graph state definition.")

    for var in flow_data.state:
        if not var.key or not var.key.strip():
            raise ValidationError("State variable key cannot be empty.")
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", var.key):
            raise ValidationError(
                f"State variable key '{var.key}' is invalid. Must be a valid identifier (alphanumeric and underscores)."
            )
        if var.default_value is not None and not is_type_compatible(var.type, var.default_value):
            raise ValidationError(
                f"Variable '{var.key}' of type '{var.type}' has incompatible default value '{var.default_value}'."
            )

    all_referenced_vars: set[str] = set()
    for node in flow_data.nodes:
        node_refs = get_node_variable_references(node)
        invalid_refs = node_refs - set(valid_vars.keys())
        if invalid_refs:
            raise ValidationError(
                f"Invalid variable reference on node '{node.id}': undefined variable(s) {', '.join(sorted(invalid_refs))}."
            )
        all_referenced_vars.update(node_refs)

    orphan_vars = set(valid_vars.keys()) - all_referenced_vars
    if orphan_vars:
        raise ValidationError(
            f"State variable(s) {', '.join(sorted(orphan_vars))} are defined in state but never referenced by any node."
        )

    # ---------------------------------------------------------
    # 2. Node Schema & Primitive Configuration Integrity
    # ---------------------------------------------------------
    node_ids_list = [n.id for n in flow_data.nodes]
    if len(node_ids_list) != len(set(node_ids_list)):
        raise ValidationError("Duplicate node IDs detected in graph definition.")

    edge_sources = {(e.source, e.source_handle) for e in flow_data.edges if e.source_handle}
    for n in flow_data.nodes:
        n.validate_integrity(edge_sources)

    # ---------------------------------------------------------
    # 3. Closed-Universe Endpoints & Edge Referential Integrity
    # ---------------------------------------------------------
    known_node_ids = {n.id for n in flow_data.nodes} | {"start", "end"}
    switch_branch_map = {
        n.id: {b.id for b in n.branches}
        for n in flow_data.nodes
        if isinstance(n, (LogicalSwitchNode, AgenticSwitchNode))
    }

    for edge in flow_data.edges:
        if edge.source not in known_node_ids:
            raise ValidationError(f"Edge source '{edge.source}' does not exist in the graph.")
        if edge.target not in known_node_ids:
            raise ValidationError(f"Edge target '{edge.target}' does not exist in the graph.")
        if edge.source == "end":
            raise ValidationError("END node cannot have outgoing edges.")
        if edge.target == "start":
            raise ValidationError("START node cannot be the target of an edge.")

        if edge.source in switch_branch_map:
            if not edge.source_handle or edge.source_handle not in switch_branch_map[edge.source]:
                raise ValidationError(
                    f"Switch '{edge.source}' edge has invalid or missing branch handle '{edge.source_handle}'."
                )
        else:
            if edge.source_handle is not None:
                raise ValidationError(f"Linear node '{edge.source}' cannot have a branch handle on its outgoing edge.")

    # ---------------------------------------------------------
    # 4. Deterministic Outgoing Degree
    # ---------------------------------------------------------
    outgoing_counts: dict[tuple[str, str | None], int] = defaultdict(int)
    for edge in flow_data.edges:
        outgoing_counts[(edge.source, edge.source_handle)] += 1

    if outgoing_counts.get(("start", None), 0) != 1:
        raise ValidationError(
            f"START node must have exactly 1 outgoing edge, found {outgoing_counts.get(('start', None), 0)}."
        )

    for node in flow_data.nodes:
        if isinstance(node, (LogicalAssignerNode, AgenticAssignerNode, RagRetrieverNode, InterruptNode)):
            cnt = outgoing_counts.get((node.id, None), 0)
            if cnt != 1:
                raise ValidationError(f"Linear node '{node.id}' must have exactly 1 outgoing target, found {cnt}.")
        elif isinstance(node, (LogicalSwitchNode, AgenticSwitchNode)):
            for branch in node.branches:
                cnt = outgoing_counts.get((node.id, branch.id), 0)
                if cnt != 1:
                    raise ValidationError(
                        f"Switch '{node.id}' branch '{branch.label}' must have exactly 1 target, found {cnt}."
                    )

    # ---------------------------------------------------------
    # 5. Global Reachability from START
    # ---------------------------------------------------------
    adj: dict[str, set[str]] = defaultdict(set)
    for edge in flow_data.edges:
        adj[edge.source].add(edge.target)

    visited: set[str] = set()

    def dfs(curr: str) -> None:
        if curr in visited:
            return
        visited.add(curr)
        for nxt in adj.get(curr, []):
            dfs(nxt)

    dfs("start")

    for node in flow_data.nodes:
        if not isinstance(node, StartNode) and node.id not in visited:
            raise ValidationError(f"Node '{node.id}' is unreachable from the START node.")
