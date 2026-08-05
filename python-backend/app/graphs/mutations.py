from __future__ import annotations

import re
import uuid
from typing import Any

from app.constants import NodeType
from app.exceptions import ValidationError
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
def check_expression_variables(expr: dict | None, valid_keys: set[str]) -> bool:
    """Recursively checks if all state references in the expression exist in valid_keys."""
    if not expr or not isinstance(expr, dict):
        return True

    kind = expr.get("kind")
    if kind == "stateRef":
        var_key = expr.get("varKey")
        return var_key in valid_keys
    elif kind == "binaryOp":
        return check_expression_variables(expr.get("left"), valid_keys) and check_expression_variables(
            expr.get("right"), valid_keys
        )
    elif kind == "unaryOp":
        return check_expression_variables(expr.get("expr"), valid_keys)

    return True


def rename_expression_variables(expr: dict | None, old_key: str, new_key: str) -> None:
    """Recursively walks the expression and renames all matching state reference keys."""
    if not expr or not isinstance(expr, dict):
        return

    kind = expr.get("kind")
    if kind == "stateRef":
        if expr.get("varKey") == old_key:
            expr["varKey"] = new_key
    elif kind == "binaryOp":
        rename_expression_variables(expr.get("left"), old_key, new_key)
        rename_expression_variables(expr.get("right"), old_key, new_key)
    elif kind == "unaryOp":
        rename_expression_variables(expr.get("expr"), old_key, new_key)


def is_variable_referenced_in_expression(expr: dict | None, var_key: str) -> bool:
    """Recursively checks if the expression references the given variable key."""
    if not expr or not isinstance(expr, dict):
        return False

    kind = expr.get("kind")
    if kind == "stateRef":
        return expr.get("varKey") == var_key
    elif kind == "binaryOp":
        return is_variable_referenced_in_expression(expr.get("left"), var_key) or is_variable_referenced_in_expression(
            expr.get("right"), var_key
        )
    elif kind == "unaryOp":
        return is_variable_referenced_in_expression(expr.get("expr"), var_key)

    return False


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
def apply_patch(flow_data: GraphFlowData, patch: list[GraphOperation]) -> GraphFlowData:
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
            expr = s.get("expression")
            target_var = s.get("target_var_key")

            # Validate slot expression variables
            if expr is not None and not check_expression_variables(expr, valid_keys):
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
            val_type = a.get("value_type", "string")
            val = a.get("value")
            expr = a.get("expression")

            if not any(v.key == target_var for v in flow_data.state):
                raise ValidationError(f"Assignment target variable '{target_var}' is not defined in state schema.")

            if expr is not None and not check_expression_variables(expr, valid_keys):
                raise ValidationError(f"Assignment expression for '{target_var}' references undefined variables.")

            validated_val = validate_default_value_type(val_type, val)

            parsed_assignments.append(
                LogicalAssignmentSchema(
                    id=a_id,
                    target_var_key=target_var,
                    value_type=val_type,
                    value=validated_val,
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
            if edge.source_id == node_id:
                edge.source_id = new_id
            elif edge.source_id.startswith(f"{node_id}_"):
                edge.source_id = edge.source_id.replace(f"{node_id}_", f"{new_id}_", 1)

            if edge.target_id == node_id:
                edge.target_id = new_id
            elif edge.target_id.startswith(f"{node_id}_"):
                edge.target_id = edge.target_id.replace(f"{node_id}_", f"{new_id}_", 1)

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

    slot_ids = (
        {s.id for s in target_node.slots} if isinstance(target_node, (LogicalSwitchNode, AgenticSwitchNode)) else set()
    )

    flow_data.nodes = [n for n in nodes if n.id != node_id]
    flow_data.edges = [
        e
        for e in edges
        if e.source_id != node_id
        and e.target_id != node_id
        and e.source_id not in slot_ids
        and e.target_id not in slot_ids
    ]
    return flow_data


def _connect(flow_data: GraphFlowData, op: ConnectOp) -> GraphFlowData:
    # Check if target/source nodes exist
    nodes = flow_data.nodes
    edges = flow_data.edges

    source_node = next(
        (
            n
            for n in nodes
            if n.id == op.source_id
            or (hasattr(n, "slots") and any(s.id == op.source_id for s in getattr(n, "slots", [])))
        ),
        None,
    )
    target_node = next(
        (
            n
            for n in nodes
            if n.id == op.target_id
            or (hasattr(n, "slots") and any(s.id == op.target_id for s in getattr(n, "slots", [])))
        ),
        None,
    )

    if not source_node:
        raise ValidationError(f"Source ID '{op.source_id}' not found.")
    if not target_node:
        raise ValidationError(f"Target ID '{op.target_id}' not found.")

    # Remove existing edges from this specific source handle to maintain single outbound constraints where relevant
    # (Except for switch slots where each slot has 1 outbound edge, and sequential nodes have 1 outbound edge)
    # Let's delete any edge that shares the same source_id
    flow_data.edges = [e for e in edges if e.source_id != op.source_id]

    new_edge = EdgeRead(
        id=uuid.uuid4(),
        source_id=op.source_id,
        target_id=op.target_id,
        source_type=op.source_type,
        target_type=op.target_type,
    )
    flow_data.edges.append(new_edge)
    return flow_data


def _disconnect(flow_data: GraphFlowData, op: DisconnectOp) -> GraphFlowData:
    flow_data.edges = [
        e
        for e in flow_data.edges
        if not (
            e.source_id == op.source_id
            and e.target_id == op.target_id
            and e.source_type == op.source_type
            and e.target_type == op.target_type
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
            # 1. Update target_var_key and expression in LOGICAL_ASSIGNER assignments
            for node in flow_data.nodes:
                if isinstance(node, LogicalAssignerNode):
                    for asgn in node.assignments:
                        if asgn.target_var_key == old_key:
                            asgn.target_var_key = key
                        if asgn.expression:
                            rename_expression_variables(asgn.expression, old_key, key)

            # 2. Update expression in LOGICAL_SWITCH slots
            for node in flow_data.nodes:
                if isinstance(node, LogicalSwitchNode):
                    for slot in node.slots:
                        if slot.expression:
                            rename_expression_variables(slot.expression, old_key, key)

            # 3. Update agentic_inputs, agentic_outputs, and prompt in AGENTIC_ASSIGNER and AGENTIC_SWITCH nodes
            for node in flow_data.nodes:
                if isinstance(node, AgenticAssignerNode):
                    if node.agentic_inputs:
                        node.agentic_inputs = [key if k == old_key else k for k in node.agentic_inputs]
                    if node.agentic_outputs:
                        node.agentic_outputs = [key if k == old_key else k for k in node.agentic_outputs]
                    if node.prompt:
                        node.prompt = node.prompt.replace(f"{{{old_key}}}", f"{{{key}}}")
                elif isinstance(node, AgenticSwitchNode):
                    if node.agentic_input == old_key:
                        node.agentic_input = key

            # 4. Update INTERRUPT payload_vars and resume_var
            for node in flow_data.nodes:
                if isinstance(node, InterruptNode):
                    if node.payload_vars:
                        node.payload_vars = [key if k == old_key else k for k in node.payload_vars]
                    if node.resume_var == old_key:
                        node.resume_var = key

    return flow_data


def _delete_state_var(flow_data: GraphFlowData, op: DeleteStateVarOp) -> GraphFlowData:
    var_key = op.key
    target_var = next((v for v in flow_data.state if v.key == var_key), None)
    if not target_var:
        return flow_data

    # Check dependencies to block delete
    # 1. Check LOGICAL_ASSIGNER assignments target_var_key & expression
    for node in flow_data.nodes:
        if isinstance(node, LogicalAssignerNode):
            for asgn in node.assignments:
                if asgn.target_var_key == var_key:
                    raise ValidationError(
                        f"Cannot delete variable '{var_key}' because it is referenced as assignment target in Assigner node '{node.id}'."
                    )
                if asgn.expression and is_variable_referenced_in_expression(asgn.expression, var_key):
                    raise ValidationError(
                        f"Cannot delete variable '{var_key}' because it is referenced in assignment expression in Assigner node '{node.id}'."
                    )

    # 2. Check LOGICAL_SWITCH slot expressions
    for node in flow_data.nodes:
        if isinstance(node, LogicalSwitchNode):
            for slot in node.slots:
                if slot.expression and is_variable_referenced_in_expression(slot.expression, var_key):
                    raise ValidationError(
                        f"Cannot delete variable '{var_key}' because it is referenced in Switch node '{node.id}' option '{slot.raw_string}'."
                    )

    # 3. Check AGENTIC_ASSIGNER and AGENTIC_SWITCH inputs/outputs
    for node in flow_data.nodes:
        if isinstance(node, AgenticAssignerNode):
            if node.agentic_inputs and var_key in node.agentic_inputs:
                raise ValidationError(
                    f"Cannot delete variable '{var_key}' because it is referenced as an input in Agentic node '{node.id}'."
                )
            if node.agentic_outputs and var_key in node.agentic_outputs:
                raise ValidationError(
                    f"Cannot delete variable '{var_key}' because it is referenced as an output in Agentic Assigner node '{node.id}'."
                )
        elif isinstance(node, AgenticSwitchNode):
            if node.agentic_input == var_key:
                raise ValidationError(
                    f"Cannot delete variable '{var_key}' because it is referenced as an input in Agentic node '{node.id}'."
                )

    # 4. Check INTERRUPT node
    for node in flow_data.nodes:
        if isinstance(node, InterruptNode):
            if node.resume_var == var_key:
                raise ValidationError(
                    f"Cannot delete variable '{var_key}' because it is referenced as resume_var in Interrupt node '{node.id}'."
                )
            if node.payload_vars and var_key in node.payload_vars:
                raise ValidationError(
                    f"Cannot delete variable '{var_key}' because it is referenced in payload_vars in Interrupt node '{node.id}'."
                )

    flow_data.state = [v for v in flow_data.state if v.key != var_key]
    return flow_data
