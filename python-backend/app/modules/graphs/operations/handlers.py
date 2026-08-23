from __future__ import annotations

from app.core.constants import NodeType
from app.core.exceptions import ValidationError
from app.modules.graphs.operations.schemas import NodeUpsertInput
from app.modules.graphs.schemas import (
    AgenticAssignerNode,
    AgenticBranch,
    AgenticSwitchNode,
    BaseNode,
    Branch,
    EdgeRead,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    RagRetrieverNode,
    _make_slot_id,
    get_expression_variables,
)


def apply_logical_assigner(
    node: BaseNode,
    u_node: NodeUpsertInput,
    flow_data: GraphFlowData,
    valid_keys: set[str],
) -> None:
    if not isinstance(node, LogicalAssignerNode):
        raise ValidationError(f"Node '{u_node.id}' is not an instance of LogicalAssignerNode.")

    if u_node.assignments is None:
        raise ValidationError(f"Node '{u_node.id}' of type LOGICAL_ASSIGNER must specify 'assignments'.")

    assignments = []
    for a in u_node.assignments:
        if a.target_var_key not in valid_keys:
            raise ValidationError(f"Variable '{a.target_var_key}' is not defined in the graph state.")

        referenced = get_expression_variables(a.expression)
        for ref in referenced:
            if ref not in valid_keys:
                raise ValidationError(f"Variable '{ref}' referenced in expression is not defined in the graph state.")

        assignments.append(LogicalAssignmentSchema(target_var_key=a.target_var_key, expression=a.expression))

    node.assignments = assignments


def apply_agentic_assigner(
    node: BaseNode,
    u_node: NodeUpsertInput,
    flow_data: GraphFlowData,
    valid_keys: set[str],
) -> None:
    if not isinstance(node, AgenticAssignerNode):
        raise ValidationError(f"Node '{u_node.id}' is not an instance of AgenticAssignerNode.")

    if u_node.prompt is None:
        raise ValidationError(f"Node '{u_node.id}' of type AGENTIC_ASSIGNER must specify 'prompt'.")
    node.prompt = u_node.prompt

    if u_node.agentic_inputs is not None:
        for inp in u_node.agentic_inputs:
            if inp not in valid_keys:
                raise ValidationError(f"Variable '{inp}' is not defined in graph state.")
        node.agentic_inputs = u_node.agentic_inputs

    if u_node.agentic_outputs is not None:
        outputs = []
        for out in u_node.agentic_outputs:
            if out.key not in valid_keys:
                raise ValidationError(f"Output variable '{out.key}' is not defined in graph state.")
            outputs.append(out.key)
        node.agentic_outputs = outputs


def apply_logical_switch(
    node: BaseNode,
    u_node: NodeUpsertInput,
    flow_data: GraphFlowData,
    valid_keys: set[str],
) -> None:
    if not isinstance(node, LogicalSwitchNode):
        raise ValidationError(f"Node '{u_node.id}' is not an instance of LogicalSwitchNode.")

    if u_node.branches is None:
        raise ValidationError(f"Node '{u_node.id}' of type LOGICAL_SWITCH must specify 'branches'.")

    logical_branches = []
    for label, br in u_node.branches.items():
        branch_id = _make_slot_id(u_node.id, label)
        expr_val = br.expression if br.expression is not None else True

        referenced = get_expression_variables(expr_val)
        for ref in referenced:
            if ref not in valid_keys:
                raise ValidationError(
                    f"Variable '{ref}' referenced in branch expression is not defined in the graph state."
                )

        logical_branches.append(Branch(id=branch_id, label=label, expression=expr_val))

        # Update branch target edge
        if br.target is not None:
            flow_data.edges = [
                e for e in flow_data.edges if not (e.source == u_node.id and e.source_handle == branch_id)
            ]
            if br.target:
                flow_data.edges.append(EdgeRead(source=u_node.id, source_handle=branch_id, target=br.target))

    node.branches = logical_branches


def apply_agentic_switch(
    node: BaseNode,
    u_node: NodeUpsertInput,
    flow_data: GraphFlowData,
    valid_keys: set[str],
) -> None:
    if not isinstance(node, AgenticSwitchNode):
        raise ValidationError(f"Node '{u_node.id}' is not an instance of AgenticSwitchNode.")

    if u_node.branches is None:
        raise ValidationError(f"Node '{u_node.id}' of type AGENTIC_SWITCH must specify 'branches'.")

    if u_node.agentic_input is not None:
        if u_node.agentic_input not in valid_keys:
            raise ValidationError(
                f"Agentic switch input variable '{u_node.agentic_input}' is not defined in graph state."
            )
        node.agentic_input = u_node.agentic_input
    elif not node.agentic_input:
        raise ValidationError(f"Node '{u_node.id}' of type AGENTIC_SWITCH must specify 'agentic_input'.")

    agentic_branches = []
    for label, br in u_node.branches.items():
        branch_id = _make_slot_id(u_node.id, label)
        agentic_branches.append(AgenticBranch(id=branch_id, label=label))

        if br.target is not None:
            flow_data.edges = [
                e for e in flow_data.edges if not (e.source == u_node.id and e.source_handle == branch_id)
            ]
            if br.target:
                flow_data.edges.append(EdgeRead(source=u_node.id, source_handle=branch_id, target=br.target))

    node.branches = agentic_branches


def apply_interrupt(
    node: BaseNode,
    u_node: NodeUpsertInput,
    flow_data: GraphFlowData,
    valid_keys: set[str],
) -> None:
    if not isinstance(node, InterruptNode):
        raise ValidationError(f"Node '{u_node.id}' is not an instance of InterruptNode.")

    if u_node.resume_var not in valid_keys:
        raise ValidationError(f"Resume variable '{u_node.resume_var}' is not defined in graph state.")
    node.resume_var = u_node.resume_var

    if u_node.payload_vars is not None:
        for pv in u_node.payload_vars:
            if pv not in valid_keys:
                raise ValidationError(f"Payload variable '{pv}' is not defined in graph state.")
        node.payload_vars = u_node.payload_vars


def apply_rag_retriever(
    node: BaseNode,
    u_node: NodeUpsertInput,
    flow_data: GraphFlowData,
    valid_keys: set[str],
) -> None:
    if not isinstance(node, RagRetrieverNode):
        raise ValidationError(f"Node '{u_node.id}' is not an instance of RagRetrieverNode.")

    if u_node.query_var not in valid_keys:
        raise ValidationError(f"Query variable '{u_node.query_var}' is not defined in graph state.")
    if u_node.context_output_var not in valid_keys:
        raise ValidationError(f"Context output variable '{u_node.context_output_var}' is not defined in graph state.")
    node.query_var = u_node.query_var
    node.context_output_var = u_node.context_output_var
    if u_node.knowledge_base is not None:
        node.knowledge_base = u_node.knowledge_base
    if u_node.top_k is not None:
        node.top_k = u_node.top_k


NODE_HANDLERS = {
    NodeType.LOGICAL_ASSIGNER: apply_logical_assigner,
    NodeType.AGENTIC_ASSIGNER: apply_agentic_assigner,
    NodeType.LOGICAL_SWITCH: apply_logical_switch,
    NodeType.AGENTIC_SWITCH: apply_agentic_switch,
    NodeType.INTERRUPT: apply_interrupt,
    NodeType.RAG_RETRIEVER: apply_rag_retriever,
}
