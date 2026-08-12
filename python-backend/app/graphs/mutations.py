from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Any

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs.nodes import (
    NodeRead,
)
from app.graphs.schemas import (
    ConnectOp,
    DefinerVariableSchema,
    DeleteNodeOp,
    DeleteStateVarOp,
    DisconnectOp,
    EdgeRead,
    GraphFlowData,
    GraphOperation,
    UpsertAgenticAssignerOp,
    UpsertAgenticSwitchOp,
    UpsertInterruptOp,
    UpsertLogicalAssignerOp,
    UpsertLogicalSwitchOp,
    UpsertRagRetrieverOp,
    UpsertStateVarOp,
)

PYTHON_KEYWORDS = {
    "False",
    "None",
    "True",
    "and",
    "as",
    "assert",
    "async",
    "await",
    "break",
    "class",
    "continue",
    "def",
    "del",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "global",
    "if",
    "import",
    "in",
    "is",
    "lambda",
    "nonlocal",
    "not",
    "or",
    "pass",
    "raise",
    "return",
    "try",
    "while",
    "with",
    "yield",
}

SENTINEL_NODE_TYPES = {NodeType.START, NodeType.END}


# ----------------------------------------------------
# AST Expression & Validation Helpers
# ----------------------------------------------------


def validate_default_value_type(var_type: str, val: Any) -> Any:
    if val is None or val == "":
        return None

    if var_type == "number":
        if isinstance(val, int) and not isinstance(val, bool):
            return val
    elif var_type == "float":
        if isinstance(val, (float, int)) and not isinstance(val, bool):
            return float(val)
    elif var_type == "boolean":
        if isinstance(val, bool):
            return val
    elif var_type == "string":
        if isinstance(val, str):
            return val

    raise ValidationError(f"Default value '{val}' is not of type '{var_type}'.")


# ----------------------------------------------------
# Main Patch Executor
# ----------------------------------------------------
def apply_patch(flow_data: GraphFlowData, patch: Sequence[GraphOperation]) -> GraphFlowData:
    """Applies a list of patch operations transactionally on the given GraphFlowData."""
    for op in patch:
        if op.op == "upsert_logical_assigner":
            flow_data = _upsert_logical_assigner(flow_data, op)
        elif op.op == "upsert_agentic_assigner":
            flow_data = _upsert_agentic_assigner(flow_data, op)
        elif op.op == "upsert_logical_switch":
            flow_data = _upsert_logical_switch(flow_data, op)
        elif op.op == "upsert_agentic_switch":
            flow_data = _upsert_agentic_switch(flow_data, op)
        elif op.op == "upsert_interrupt":
            flow_data = _upsert_interrupt(flow_data, op)
        elif op.op == "upsert_rag_retriever":
            flow_data = _upsert_rag_retriever(flow_data, op)
        elif op.op == "delete_node":
            flow_data = _delete_node(flow_data, op)
        elif op.op == "connect":
            flow_data = _connect(flow_data, op)
        elif op.op == "disconnect":
            flow_data = _disconnect(flow_data, op)
        elif op.op == "upsert_state_var":
            flow_data = _upsert_state_var(flow_data, op)
        elif op.op == "delete_state_var":
            flow_data = _delete_state_var(flow_data, op)
        else:
            raise ValidationError(f"Unknown operation type: {op}")
    return flow_data


# ----------------------------------------------------
# Core Operation Implementations
# ----------------------------------------------------
def _upsert_node_generic(
    flow_data: GraphFlowData,
    node_id: str,
    node_type: NodeType,
    config_fields: dict[str, Any],
    new_id: str | None = None,
) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges

    existing_node = next((n for n in nodes if n.id == node_id), None)
    target_node: NodeRead

    from app.graphs.nodes import NODE_CLASS_MAP

    node_cls = NODE_CLASS_MAP.get(node_type)
    if not node_cls:
        raise ValidationError(f"Unsupported node type: {node_type}")

    from typing import cast

    if existing_node is None:
        # Build flat dictionary payload for model_validate
        node_payload = {"id": node_id, "node_type": node_type, **config_fields}
        target_node = cast(NodeRead, node_cls.model_validate(node_payload))
        nodes.append(target_node)
    else:
        if existing_node.node_type != node_type:
            nodes.remove(existing_node)
            node_payload = {"id": node_id, "node_type": node_type, **config_fields}
            target_node = cast(NodeRead, node_cls.model_validate(node_payload))
            nodes.append(target_node)
        else:
            # Merge existing state with non-None configuration updates
            non_none_config = {k: v for k, v in config_fields.items() if v is not None}
            merged_payload = {
                **existing_node.model_dump(mode="json"),
                **non_none_config,
                "id": node_id,
                "node_type": node_type,
            }
            validated = node_cls.model_validate(merged_payload)
            for k in validated.model_fields.keys():
                if k not in ("id", "node_type"):
                    setattr(existing_node, k, getattr(validated, k))
            target_node = existing_node

    # Handle rename
    if new_id and new_id != node_id:
        if any(n.id == new_id for n in nodes if n.id != node_id):
            raise ValidationError(f"Node ID '{new_id}' is already taken.")

        target_node.id = new_id

        if hasattr(target_node, "branches"):
            for branch in getattr(target_node, "branches", []):
                if branch.id.startswith(f"{node_id}_"):
                    branch.id = branch.id.replace(f"{node_id}_", f"{new_id}_", 1)

        for edge in edges:
            if edge.source == node_id:
                edge.source = new_id
                if edge.source_handle and edge.source_handle.startswith(f"{node_id}_"):
                    edge.source_handle = edge.source_handle.replace(f"{node_id}_", f"{new_id}_", 1)
            elif edge.source.startswith(f"{node_id}_"):
                edge.source = edge.source.replace(f"{node_id}_", f"{new_id}_", 1)

            if edge.target == node_id:
                edge.target = new_id
                if edge.target_handle and edge.target_handle.startswith(f"{node_id}_"):
                    edge.target_handle = edge.target_handle.replace(f"{node_id}_", f"{new_id}_", 1)
            elif edge.target.startswith(f"{node_id}_"):
                edge.target = edge.target.replace(f"{node_id}_", f"{new_id}_", 1)

    return flow_data


def _upsert_logical_assigner(flow_data: GraphFlowData, op: UpsertLogicalAssignerOp) -> GraphFlowData:
    return _upsert_node_generic(
        flow_data,
        node_id=op.node_id,
        node_type=NodeType.LOGICAL_ASSIGNER,
        config_fields={"assignments": [a.model_dump() for a in op.assignments]},
        new_id=op.new_id,
    )


def _upsert_agentic_assigner(flow_data: GraphFlowData, op: UpsertAgenticAssignerOp) -> GraphFlowData:
    return _upsert_node_generic(
        flow_data,
        node_id=op.node_id,
        node_type=NodeType.AGENTIC_ASSIGNER,
        config_fields={
            "prompt": op.prompt,
            "agentic_inputs": op.agentic_inputs,
            "agentic_outputs": op.agentic_outputs,
        },
        new_id=op.new_id,
    )


def _upsert_logical_switch(flow_data: GraphFlowData, op: UpsertLogicalSwitchOp) -> GraphFlowData:
    return _upsert_node_generic(
        flow_data,
        node_id=op.node_id,
        node_type=NodeType.LOGICAL_SWITCH,
        config_fields={"branches": [b.model_dump() for b in op.branches]},
        new_id=op.new_id,
    )


def _upsert_agentic_switch(flow_data: GraphFlowData, op: UpsertAgenticSwitchOp) -> GraphFlowData:
    return _upsert_node_generic(
        flow_data,
        node_id=op.node_id,
        node_type=NodeType.AGENTIC_SWITCH,
        config_fields={"branches": [b.model_dump() for b in op.branches], "agentic_input": op.agentic_input},
        new_id=op.new_id,
    )


def _upsert_interrupt(flow_data: GraphFlowData, op: UpsertInterruptOp) -> GraphFlowData:
    return _upsert_node_generic(
        flow_data,
        node_id=op.node_id,
        node_type=NodeType.INTERRUPT,
        config_fields={"payload_vars": op.payload_vars, "resume_var": op.resume_var},
        new_id=op.new_id,
    )


def _upsert_rag_retriever(flow_data: GraphFlowData, op: UpsertRagRetrieverOp) -> GraphFlowData:
    return _upsert_node_generic(
        flow_data,
        node_id=op.node_id,
        node_type=NodeType.RAG_RETRIEVER,
        config_fields={
            "query_var": op.query_var,
            "context_output_var": op.context_output_var,
            "knowledge_base": op.knowledge_base,
            "top_k": op.top_k,
        },
        new_id=op.new_id,
    )


def _delete_node(flow_data: GraphFlowData, op: DeleteNodeOp) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges
    node_id = op.node_id

    target_node = next((n for n in nodes if n.id == node_id), None)
    if not target_node:
        return flow_data

    # START and END nodes cannot be deleted
    if target_node.node_type in SENTINEL_NODE_TYPES:
        raise ValidationError(f"Sentinel node of type '{target_node.node_type}' cannot be deleted.")

    flow_data.nodes = [n for n in nodes if n.id != node_id]
    flow_data.edges = [e for e in edges if e.source != node_id and e.target != node_id]
    return flow_data


def _connect(flow_data: GraphFlowData, op: ConnectOp) -> GraphFlowData:
    # Check if target/source nodes exist
    nodes = flow_data.nodes
    edges = flow_data.edges

    source_node = next((n for n in nodes if n.id == op.source), None)
    target_node = next((n for n in nodes if n.id == op.target), None)

    if not source_node:
        raise ValidationError(f"Source Node '{op.source}' not found.")
    if not target_node:
        raise ValidationError(f"Target Node '{op.target}' not found.")

    # Automatically register branch on Switch nodes if case is provided
    if source_node.node_type in (NodeType.LOGICAL_SWITCH, NodeType.AGENTIC_SWITCH) and op.case:
        from app.graphs.nodes import Branch, _make_slot_id

        branches = getattr(source_node, "branches", [])
        branch = next((b for b in branches if b.label == op.case), None)
        if not branch:
            branch_id = _make_slot_id(op.source, op.case)
            new_branch = Branch(
                id=branch_id,
                label=op.case,
                expression=None,
                target_var_key=None,
            )
            if source_node.node_type == NodeType.LOGICAL_SWITCH and op.expression:
                from app.graphs.expressions import parse_expression

                new_branch.expression = parse_expression(op.expression)
            branches.append(new_branch)
            op.source_handle = branch_id
        else:
            if op.expression is not None and source_node.node_type == NodeType.LOGICAL_SWITCH:
                from app.graphs.expressions import parse_expression

                branch.expression = parse_expression(op.expression)
            op.source_handle = branch.id

    if hasattr(source_node, "branches") and op.source_handle:
        if not any(b.id == op.source_handle for b in getattr(source_node, "branches", [])):
            raise ValidationError(f"Source handle '{op.source_handle}' not found on node '{op.source}'.")

    # Remove existing edges from this specific source handle to maintain single outbound constraints
    if op.source_handle:
        flow_data.edges = [e for e in edges if not (e.source == op.source and e.source_handle == op.source_handle)]
    else:
        flow_data.edges = [e for e in edges if not (e.source == op.source and e.source_handle is None)]

    new_edge = EdgeRead(
        id=uuid.uuid4(),
        source=op.source,
        source_handle=op.source_handle,
        target=op.target,
        target_handle=op.target_handle,
    )
    flow_data.edges.append(new_edge)
    return flow_data


def _disconnect(flow_data: GraphFlowData, op: DisconnectOp) -> GraphFlowData:
    flow_data.edges = [
        e
        for e in flow_data.edges
        if not (
            e.source == op.source
            and e.source_handle == op.source_handle
            and e.target == op.target
            and e.target_handle == op.target_handle
        )
    ]
    return flow_data


def _upsert_state_var(flow_data: GraphFlowData, op: UpsertStateVarOp) -> GraphFlowData:
    key = op.key.strip()
    if not re.match(r"^[a-z_][a-z0-9_]*$", key):
        raise ValidationError(f"Variable name '{key}' must be valid snake_case.")

    if key in PYTHON_KEYWORDS:
        raise ValidationError(f"Variable name '{key}' cannot be a Python keyword.")

    # Find existing variable by ID first, then by key
    existing_var = None
    if op.id:
        existing_var = next((v for v in flow_data.state if v.id == op.id), None)
    if not existing_var:
        existing_var = next((v for v in flow_data.state if v.key == key), None)

    validated_default = validate_default_value_type(op.type, op.default_value)

    if existing_var is None:
        new_var = DefinerVariableSchema(
            id=op.id or str(uuid.uuid4()),
            key=key,
            type=op.type,
            default_value=validated_default,
            description=op.description,
        )
        flow_data.state.append(new_var)
    else:
        # Update existing variable key (cascade if key changes)
        old_key = existing_var.key
        existing_var.key = key
        existing_var.type = op.type
        existing_var.default_value = validated_default
        existing_var.description = op.description

        if key != old_key:
            for node in flow_data.nodes:
                node.rename_variable_references(old_key, key)

    return flow_data


def _delete_state_var(flow_data: GraphFlowData, op: DeleteStateVarOp) -> GraphFlowData:
    var_key = op.key
    target_var = next((v for v in flow_data.state if v.key == var_key), None)
    if not target_var:
        return flow_data

    # Check dependencies to block delete
    for node in flow_data.nodes:
        if var_key in node.get_variable_references():
            raise ValidationError(f"Cannot delete variable '{var_key}' because it is referenced in node '{node.id}'.")

    flow_data.state = [v for v in flow_data.state if v.key != var_key]
    return flow_data


def sort_operations_by_dependency(ops: Sequence[GraphOperation]) -> list[GraphOperation]:
    """Sorts operations: State declarations -> Node additions/deletes -> Connections/disconnects."""
    state_ops = []
    node_ops = []
    connect_ops = []
    delete_ops = []  # Run deletes first to avoid constraints

    for op in ops:
        if op.op in ("delete_node", "delete_state_var", "disconnect"):
            delete_ops.append(op)
        elif op.op == "upsert_state_var":
            state_ops.append(op)
        elif op.op.startswith("upsert_"):
            node_ops.append(op)
        elif op.op == "connect":
            connect_ops.append(op)

    return delete_ops + state_ops + node_ops + connect_ops
