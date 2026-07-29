from __future__ import annotations

from typing import Any

from app.graphs.schemas import DiagnosticRead, GraphFlowData


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


def validate_flow_data(flow_data: GraphFlowData) -> list[DiagnosticRead]:
    diagnostics = []
    valid_keys = {
        var.key
        for node in flow_data.nodes
        if node.node_type == "DEFINER" and node.variables
        for var in node.variables
        if var.key
    }

    for node in flow_data.nodes:
        if node.node_type == "STEP":
            for slot in node.slots:
                if slot.target_var_key and slot.target_var_key not in valid_keys:
                    diagnostics.append(
                        DiagnosticRead(
                            line=1,
                            column=1,
                            code="E001",
                            severity="error",
                            message=f"Invalid mutation target: variable '{slot.target_var_key}' is missing or deleted.",
                            node_id=node.id,
                            slot_id=slot.id,
                        )
                    )

        elif node.node_type == "LOGICAL_ASSIGNER":
            assignments = node.assignments or []
            for asgn in assignments:
                if asgn.target_var_key and asgn.target_var_key not in valid_keys:
                    diagnostics.append(
                        DiagnosticRead(
                            line=1,
                            column=1,
                            code="E002",
                            severity="error",
                            message=f"Invalid assignment target: variable '{asgn.target_var_key}' is missing or deleted.",
                            node_id=node.id,
                            slot_id=asgn.id,
                        )
                    )

        elif node.node_type == "SWITCH":
            for slot in node.slots:
                if slot.expression:
                    for invalid_var in _find_invalid_state_refs(slot.expression, valid_keys):
                        diagnostics.append(
                            DiagnosticRead(
                                line=1,
                                column=1,
                                code="E003",
                                severity="error",
                                message=f"Invalid state reference: variable '{invalid_var}' is missing or deleted.",
                                node_id=node.id,
                                slot_id=slot.id,
                            )
                        )

    return diagnostics
