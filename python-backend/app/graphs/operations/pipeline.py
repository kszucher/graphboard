from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, TypeAlias

from pydantic import Field

from app.exceptions import ValidationError
from app.graphs.schemas import GraphFlowData

from .rename_ops import (
    RenameNodeOp,
    RenameVariableOp,
    rename_node,
    rename_variable,
)
from .topology_ops import (
    ConnectNodesOp,
    DeleteNodeOp,
    DisconnectNodesOp,
    connect_nodes,
    delete_node,
    disconnect_nodes,
)
from .upsert_ops import (
    UpsertAgenticAssignerOp,
    UpsertAgenticSwitchOp,
    UpsertInterruptOp,
    UpsertLogicalAssignerOp,
    UpsertLogicalSwitchOp,
    UpsertRagRetrieverOp,
    upsert_agentic_assigner,
    upsert_agentic_switch,
    upsert_interrupt,
    upsert_logical_assigner,
    upsert_logical_switch,
    upsert_rag_retriever,
)

GraphOperation: TypeAlias = Annotated[
    UpsertLogicalAssignerOp
    | UpsertAgenticAssignerOp
    | UpsertRagRetrieverOp
    | UpsertLogicalSwitchOp
    | UpsertAgenticSwitchOp
    | UpsertInterruptOp
    | DeleteNodeOp
    | RenameNodeOp
    | RenameVariableOp
    | ConnectNodesOp
    | DisconnectNodesOp,
    Field(discriminator="op"),
]


def sort_operations_by_dependency(ops: Sequence[GraphOperation]) -> list[GraphOperation]:
    """Sorts operations: renames first -> deletes -> upserts -> connections."""
    rename_ops = []
    delete_ops = []
    upsert_ops = []
    connect_ops = []

    for op in ops:
        if op.op in ("rename_node", "rename_variable"):
            rename_ops.append(op)
        elif op.op in ("delete_node", "disconnect_nodes"):
            delete_ops.append(op)
        elif op.op in (
            "upsert_logical_assigner",
            "upsert_agentic_assigner",
            "upsert_rag_retriever",
            "upsert_logical_switch",
            "upsert_agentic_switch",
            "upsert_interrupt",
        ):
            upsert_ops.append(op)
        elif op.op == "connect_nodes":
            connect_ops.append(op)

    return rename_ops + delete_ops + upsert_ops + connect_ops


def prune_dead_variables_and_expressions(flow_data: GraphFlowData) -> None:
    """Automatically removes unused state variables and orphaned expression records from the flow."""
    from app.graphs.expressions import get_expression_variables

    referenced = set()
    active_expr_ids = set()

    for node in flow_data.nodes:
        node_type = node.node_type.value

        if node_type == "LOGICAL_ASSIGNER":
            for a in getattr(node, "assignments", []):
                referenced.add(a.target_var_key)
                if a.expr_id:
                    active_expr_ids.add(a.expr_id)
                    if flow_data.expressions and a.expr_id in flow_data.expressions:
                        referenced.update(get_expression_variables(flow_data.expressions[a.expr_id].expr))

        elif node_type == "AGENTIC_ASSIGNER":
            referenced.update(getattr(node, "agentic_inputs", []))
            referenced.update(getattr(node, "agentic_outputs", []))

        elif node_type == "RAG_RETRIEVER":
            query = getattr(node, "query_var", None)
            out = getattr(node, "context_output_var", None)
            if query:
                referenced.add(query)
            if out:
                referenced.add(out)

        elif node_type == "LOGICAL_SWITCH":
            for b in getattr(node, "branches", []):
                if b.expr_id:
                    active_expr_ids.add(b.expr_id)
                    if flow_data.expressions and b.expr_id in flow_data.expressions:
                        referenced.update(get_expression_variables(flow_data.expressions[b.expr_id].expr))

        elif node_type == "AGENTIC_SWITCH":
            inp = getattr(node, "agentic_input", None)
            if inp:
                referenced.add(inp)

        elif node_type == "INTERRUPT":
            referenced.update(getattr(node, "payload_vars", []))
            res = getattr(node, "resume_var", None)
            if res:
                referenced.add(res)

    # 1. Prune unused variables
    flow_data.state = [v for v in flow_data.state if v.key in referenced]

    # 2. Prune unused expressions
    flow_data.expressions = {k: v for k, v in flow_data.expressions.items() if k in active_expr_ids}


def apply_patch(flow_data: GraphFlowData, patch: Sequence[GraphOperation]) -> GraphFlowData:
    """Applies a list of patch operations transactionally on the given GraphFlowData."""
    sorted_patch = sort_operations_by_dependency(patch)

    for op in sorted_patch:
        if op.op == "upsert_logical_assigner":
            flow_data = upsert_logical_assigner(flow_data, op)
        elif op.op == "upsert_agentic_assigner":
            flow_data = upsert_agentic_assigner(flow_data, op)
        elif op.op == "upsert_rag_retriever":
            flow_data = upsert_rag_retriever(flow_data, op)
        elif op.op == "upsert_logical_switch":
            flow_data = upsert_logical_switch(flow_data, op)
        elif op.op == "upsert_agentic_switch":
            flow_data = upsert_agentic_switch(flow_data, op)
        elif op.op == "upsert_interrupt":
            flow_data = upsert_interrupt(flow_data, op)
        elif op.op == "delete_node":
            flow_data = delete_node(flow_data, op)
        elif op.op == "rename_node":
            flow_data = rename_node(flow_data, op)
        elif op.op == "rename_variable":
            flow_data = rename_variable(flow_data, op)
        elif op.op == "connect_nodes":
            flow_data = connect_nodes(flow_data, op)
        elif op.op == "disconnect_nodes":
            flow_data = disconnect_nodes(flow_data, op)
        else:
            raise ValidationError(f"Unknown operation type: {op}")

    # Prune unused variables and expressions at the end of the transaction
    prune_dead_variables_and_expressions(flow_data)

    return flow_data
