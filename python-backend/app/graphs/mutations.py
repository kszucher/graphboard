from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Any

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs.expressions import get_expression_variables, parse_expression
from app.graphs.node_helpers import get_node_variable_references, rename_node_variable_references
from app.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    ConnectOp,
    DefinerVariableSchema,
    DeleteNodeOp,
    DeleteStateVarOp,
    DisconnectOp,
    EdgeRead,
    EndNode,
    GraphFlowData,
    GraphOperation,
    InterruptNode,
    LiteralExpression,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    NodeRead,
    SlotRead,
    StartNode,
    UpsertNodeOp,
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
        if op.op == "upsert_node":
            flow_data = _upsert_node(flow_data, op)
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
def _upsert_node(flow_data: GraphFlowData, op: UpsertNodeOp) -> GraphFlowData:
    nodes = flow_data.nodes
    edges = flow_data.edges
    node_id = op.node_id
    node_type = op.node_type

    existing_node = next((n for n in nodes if n.id == node_id), None)
    target_node: NodeRead

    # Instantiate or replace node
    if existing_node is None:
        new_node: NodeRead
        if node_type == NodeType.START:
            new_node = StartNode(id=node_id)
        elif node_type == NodeType.END:
            new_node = EndNode(id=node_id)
        elif node_type == NodeType.LOGICAL_ASSIGNER:
            new_node = LogicalAssignerNode(id=node_id, assignments=[])
        elif node_type == NodeType.AGENTIC_ASSIGNER:
            new_node = AgenticAssignerNode(id=node_id, prompt="", agentic_inputs=[], agentic_outputs=[])
        elif node_type == NodeType.LOGICAL_SWITCH:
            new_node = LogicalSwitchNode(id=node_id, slots=[])
        elif node_type == NodeType.AGENTIC_SWITCH:
            new_node = AgenticSwitchNode(id=node_id, slots=[], agentic_input="")
        elif node_type == NodeType.INTERRUPT:
            new_node = InterruptNode(id=node_id, payload_vars=[], resume_var="")
        else:
            raise ValidationError(f"Unsupported node type: {node_type}")
        nodes.append(new_node)
        target_node = new_node
    else:
        # If type changed, we replace the node object
        if existing_node.node_type != node_type:
            nodes.remove(existing_node)
            if node_type == NodeType.START:
                target_node = StartNode(id=node_id)
            elif node_type == NodeType.END:
                target_node = EndNode(id=node_id)
            elif node_type == NodeType.LOGICAL_ASSIGNER:
                target_node = LogicalAssignerNode(id=node_id, assignments=[])
            elif node_type == NodeType.AGENTIC_ASSIGNER:
                target_node = AgenticAssignerNode(id=node_id, prompt="", agentic_inputs=[], agentic_outputs=[])
            elif node_type == NodeType.LOGICAL_SWITCH:
                target_node = LogicalSwitchNode(id=node_id, slots=[])
            elif node_type == NodeType.AGENTIC_SWITCH:
                target_node = AgenticSwitchNode(id=node_id, slots=[], agentic_input="")
            elif node_type == NodeType.INTERRUPT:
                target_node = InterruptNode(id=node_id, payload_vars=[], resume_var="")
            else:
                raise ValidationError(f"Unsupported node type: {node_type}")
            nodes.append(target_node)
        else:
            target_node = existing_node

    # Apply configuration
    config = op.config
    valid_keys = {v.key for v in flow_data.state}

    # 1. Handle Slots (LogicalSwitchNode, AgenticSwitchNode)
    if isinstance(target_node, (LogicalSwitchNode, AgenticSwitchNode)) and "slots" in config:
        slots_data = config["slots"]
        parsed_slots = []
        for s in slots_data:
            s_id = s.get("id") or f"{node_id}_option_{uuid.uuid4().hex[:6]}"
            raw_str = s.get("raw_string") or ""
            expr = parse_expression(s.get("expression"))
            target_var = s.get("target_var_key")

            # Validate slot expression variables
            if expr is not None and not (get_expression_variables(expr) <= valid_keys):
                raise ValidationError(f"Switch slot '{raw_str}' expression references undefined variables.")

            parsed_slots.append(
                SlotRead(
                    id=s_id,
                    raw_string=raw_str,
                    expression=expr,
                    target_var_key=target_var,
                )
            )
        target_node.slots = parsed_slots

    # 2. Handle Assignments (LogicalAssignerNode)
    if isinstance(target_node, LogicalAssignerNode) and "assignments" in config:
        assignments_data = config["assignments"]
        parsed_assignments = []
        for a in assignments_data:
            a_id = a.get("id") or str(uuid.uuid4())
            target_var = a.get("target_var_key", "").strip()

            expr_data = a.get("expression")
            expr = parse_expression(expr_data) if expr_data is not None else None

            target_var_schema = next((v for v in flow_data.state if v.key == target_var), None)
            if not target_var_schema:
                raise ValidationError(f"Assignment target variable '{target_var}' is not defined in state schema.")

            if expr is not None:
                if not (get_expression_variables(expr) <= valid_keys):
                    raise ValidationError(f"Assignment expression for '{target_var}' references undefined variables.")
                if isinstance(expr, LiteralExpression):
                    validate_default_value_type(target_var_schema.type, expr.value)

            parsed_assignments.append(
                LogicalAssignmentSchema(
                    id=a_id,
                    target_var_key=target_var,
                    expression=expr,
                )
            )
        target_node.assignments = parsed_assignments

    # 3. Handle prompt, agentic_inputs, agentic_outputs (AgenticAssignerNode)
    if isinstance(target_node, AgenticAssignerNode):
        if "prompt" in config:
            target_node.prompt = config["prompt"]
        if "agentic_inputs" in config:
            inputs = config["agentic_inputs"]
            for inp in inputs:
                if inp not in valid_keys:
                    raise ValidationError(f"Agentic input '{inp}' is not defined in state schema.")
            target_node.agentic_inputs = inputs
        if "agentic_outputs" in config:
            outputs = config["agentic_outputs"]
            for outp in outputs:
                if outp not in valid_keys:
                    raise ValidationError(f"Agentic output '{outp}' is not defined in state schema.")
            target_node.agentic_outputs = outputs

    # 4. Handle agentic_input (AgenticSwitchNode)
    if isinstance(target_node, AgenticSwitchNode):
        if "agentic_input" in config:
            inp = config["agentic_input"]
            if inp and inp not in valid_keys:
                raise ValidationError(f"Agentic switch input '{inp}' is not defined in state schema.")
            target_node.agentic_input = inp

    # 5. Handle payload_vars, resume_var (InterruptNode)
    if isinstance(target_node, InterruptNode):
        if "payload_vars" in config:
            p_vars = config["payload_vars"]
            for pv in p_vars:
                if pv not in valid_keys:
                    raise ValidationError(f"Interrupt payload variable '{pv}' is not defined in state schema.")
            target_node.payload_vars = p_vars
        if "resume_var" in config:
            r_var = config["resume_var"]
            if r_var and r_var not in valid_keys:
                raise ValidationError(f"Interrupt resume variable '{r_var}' is not defined in state schema.")
            target_node.resume_var = r_var

    # 6. Handle potential Node ID Rename
    if "new_id" in config and config["new_id"] and config["new_id"] != node_id:
        new_id = config["new_id"]
        # Verify new ID is unique
        if any(n.id == new_id for n in nodes if n.id != node_id):
            raise ValidationError(f"Node ID '{new_id}' is already taken.")

        target_node.id = new_id

        # Update slots ID prefixes
        if hasattr(target_node, "slots"):
            for slot in getattr(target_node, "slots", []):
                if slot.id.startswith(f"{node_id}_"):
                    slot.id = slot.id.replace(f"{node_id}_", f"{new_id}_", 1)

        # Update edges targeting/sourcing this node
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

    if hasattr(source_node, "slots") and op.source_handle:
        if not any(s.id == op.source_handle for s in getattr(source_node, "slots", [])):
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
                rename_node_variable_references(node, old_key, key)

    return flow_data


def _delete_state_var(flow_data: GraphFlowData, op: DeleteStateVarOp) -> GraphFlowData:
    var_key = op.key
    target_var = next((v for v in flow_data.state if v.key == var_key), None)
    if not target_var:
        return flow_data

    # Check dependencies to block delete
    for node in flow_data.nodes:
        if var_key in get_node_variable_references(node):
            raise ValidationError(f"Cannot delete variable '{var_key}' because it is referenced in node '{node.id}'.")

    flow_data.state = [v for v in flow_data.state if v.key != var_key]
    return flow_data
