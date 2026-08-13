from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, TypeAlias

from pydantic import Field

from app.exceptions import ValidationError
from app.graphs.schemas import GraphFlowData

from .config_ops import (
    BindBranchConditionOp,
    BindLogicalAssignmentOp,
    ConfigureAgenticPromptOp,
    ConfigureAgenticSwitchOp,
    ConfigureInterruptOp,
    ConfigureRagSearchOp,
    bind_branch_condition,
    bind_logical_assignment,
    configure_agentic_prompt,
    configure_agentic_switch,
    configure_interrupt,
    configure_rag_search,
)
from .state_ops import (
    DeclareVariableOp,
    DefineExpressionOp,
    DeleteVariableOp,
    declare_variable,
    define_expression,
    delete_variable,
)
from .topology_ops import (
    AddSwitchBranchOp,
    ConnectOp,
    CreateNodeOp,
    DeleteNodeOp,
    DisconnectOp,
    RemoveSwitchBranchOp,
    add_switch_branch,
    connect,
    create_node,
    delete_node,
    disconnect,
    remove_switch_branch,
)

GraphOperation: TypeAlias = Annotated[
    DeclareVariableOp
    | DeleteVariableOp
    | DefineExpressionOp
    | CreateNodeOp
    | DeleteNodeOp
    | AddSwitchBranchOp
    | RemoveSwitchBranchOp
    | ConnectOp
    | DisconnectOp
    | BindLogicalAssignmentOp
    | BindBranchConditionOp
    | ConfigureAgenticPromptOp
    | ConfigureAgenticSwitchOp
    | ConfigureRagSearchOp
    | ConfigureInterruptOp,
    Field(discriminator="op"),
]


def sort_operations_by_dependency(ops: Sequence[GraphOperation]) -> list[GraphOperation]:
    """Sorts operations: deletes -> state declarations -> expression definitions -> node creation -> config -> connections."""
    delete_ops = []
    state_ops = []
    expr_ops = []
    node_ops = []
    config_ops = []
    connect_ops = []

    for op in ops:
        if op.op in ("delete_node", "delete_variable", "disconnect", "remove_switch_branch"):
            delete_ops.append(op)
        elif op.op == "declare_variable":
            state_ops.append(op)
        elif op.op == "define_expression":
            expr_ops.append(op)
        elif op.op in ("create_node", "add_switch_branch"):
            node_ops.append(op)
        elif op.op in (
            "bind_logical_assignment",
            "bind_branch_condition",
            "configure_agentic_prompt",
            "configure_agentic_switch",
            "configure_rag_search",
            "configure_interrupt",
        ):
            config_ops.append(op)
        elif op.op == "connect":
            connect_ops.append(op)

    return delete_ops + state_ops + expr_ops + node_ops + config_ops + connect_ops


def apply_patch(flow_data: GraphFlowData, patch: Sequence[GraphOperation]) -> GraphFlowData:
    """Applies a list of patch operations transactionally on the given GraphFlowData."""
    for op in patch:
        if op.op == "declare_variable":
            flow_data = declare_variable(flow_data, op)
        elif op.op == "delete_variable":
            flow_data = delete_variable(flow_data, op)
        elif op.op == "define_expression":
            flow_data = define_expression(flow_data, op)
        elif op.op == "create_node":
            flow_data = create_node(flow_data, op)
        elif op.op == "delete_node":
            flow_data = delete_node(flow_data, op)
        elif op.op == "add_switch_branch":
            flow_data = add_switch_branch(flow_data, op)
        elif op.op == "remove_switch_branch":
            flow_data = remove_switch_branch(flow_data, op)
        elif op.op == "connect":
            flow_data = connect(flow_data, op)
        elif op.op == "disconnect":
            flow_data = disconnect(flow_data, op)
        elif op.op == "bind_logical_assignment":
            flow_data = bind_logical_assignment(flow_data, op)
        elif op.op == "bind_branch_condition":
            flow_data = bind_branch_condition(flow_data, op)
        elif op.op == "configure_agentic_prompt":
            flow_data = configure_agentic_prompt(flow_data, op)
        elif op.op == "configure_agentic_switch":
            flow_data = configure_agentic_switch(flow_data, op)
        elif op.op == "configure_rag_search":
            flow_data = configure_rag_search(flow_data, op)
        elif op.op == "configure_interrupt":
            flow_data = configure_interrupt(flow_data, op)
        else:
            raise ValidationError(f"Unknown operation type: {op}")
    return flow_data
