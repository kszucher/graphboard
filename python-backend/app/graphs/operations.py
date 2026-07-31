import re
import uuid
from typing import Any

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs.schemas import (
    DefinerVariableSchema,
    DefinerVariableUpdates,
    GraphFlowData,
    LogicalAssignmentSchema,
    LogicalAssignmentUpdates,
    VariableType,
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


# ----------------------------------------------------
# AST Expression Helpers
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


# ----------------------------------------------------
# Type Validation
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


def get_all_definer_variables(flow_data: GraphFlowData) -> list[DefinerVariableSchema]:
    return flow_data.state


# ----------------------------------------------------
# Definer Variable CRUD
# ----------------------------------------------------
def create_definer_variable(
    flow_data: GraphFlowData,
    key: str,
    var_type: VariableType = "string",
    default_value: Any = None,
    description: str | None = None,
) -> GraphFlowData:
    key = key.strip()
    if not re.match(r"^[a-z_][a-z0-9_]*$", key):
        raise ValidationError(f"Variable name '{key}' must be valid snake_case.")

    if key in PYTHON_KEYWORDS:
        raise ValidationError(f"Variable name '{key}' cannot be a Python keyword.")

    existing_vars = get_all_definer_variables(flow_data)
    if any(v.key == key for v in existing_vars):
        raise ValidationError(f"Variable name '{key}' already exists in state schema.")

    validated_default = validate_default_value_type(var_type, default_value)

    new_var = DefinerVariableSchema(
        id=str(uuid.uuid4()),
        key=key,
        type=var_type,
        default_value=validated_default,
        description=description,
    )
    flow_data.state.append(new_var)
    return flow_data


def update_definer_variable(flow_data: GraphFlowData, var_id: str, updates: DefinerVariableUpdates) -> GraphFlowData:
    target_var = next((v for v in flow_data.state if v.id == var_id), None)

    if not target_var:
        raise ValidationError(f"Variable with ID '{var_id}' not found.")

    old_key = target_var.key
    new_key = updates.get("key", "").strip() if "key" in updates else None

    # Rename validation
    if new_key and new_key != old_key:
        if not re.match(r"^[a-z_][a-z0-9_]*$", new_key):
            raise ValidationError(f"Variable name '{new_key}' must be valid snake_case.")
        if new_key in PYTHON_KEYWORDS:
            raise ValidationError(f"Variable name '{new_key}' cannot be a Python keyword.")
        existing_vars = get_all_definer_variables(flow_data)
        if any(v.key == new_key for v in existing_vars):
            raise ValidationError(f"Variable name '{new_key}' already exists in state schema.")

        # Apply rename cascading
        target_var.key = new_key

        # 1. Update target_var_key in STEP slots
        for node in flow_data.nodes:
            if node.node_type == NodeType.STEP:
                for slot in node.slots:
                    if slot.target_var_key == old_key:
                        slot.target_var_key = new_key

        # 2. Update target_var_key and expression in LOGICAL_ASSIGNER assignments
        for node in flow_data.nodes:
            if node.node_type == NodeType.LOGICAL_ASSIGNER and node.assignments is not None:
                for asgn in node.assignments:
                    if asgn.target_var_key == old_key:
                        asgn.target_var_key = new_key
                    if asgn.expression:
                        rename_expression_variables(asgn.expression, old_key, new_key)

        # 3. Update expression in SWITCH slots
        for node in flow_data.nodes:
            if node.node_type == NodeType.SWITCH:
                for slot in node.slots:
                    if slot.expression:
                        rename_expression_variables(slot.expression, old_key, new_key)

        # 4. Update agentic_inputs, agentic_outputs, and prompt in AGENTIC_ASSIGNER nodes
        for node in flow_data.nodes:
            if node.node_type == NodeType.AGENTIC_ASSIGNER:
                if node.agentic_inputs:
                    node.agentic_inputs = [new_key if k == old_key else k for k in node.agentic_inputs]
                if node.agentic_outputs:
                    node.agentic_outputs = [new_key if k == old_key else k for k in node.agentic_outputs]
                if node.prompt:
                    node.prompt = node.prompt.replace(f"{{{old_key}}}", f"{{{new_key}}}")

    new_type = updates.get("type") or target_var.type
    if "type" in updates and updates["type"]:
        target_var.type = updates["type"]
    if "default_value" in updates:
        target_var.default_value = validate_default_value_type(new_type, updates["default_value"])
    if "description" in updates:
        target_var.description = updates["description"]

    return flow_data


def delete_definer_variable(flow_data: GraphFlowData, var_id: str) -> GraphFlowData:
    # Find variable
    target_var = next((v for v in flow_data.state if v.id == var_id), None)
    if not target_var:
        raise ValidationError(f"Variable with ID '{var_id}' not found.")
    var_key = target_var.key

    # Check dependencies to block delete
    # 1. Check STEP slots target_var_key
    for node in flow_data.nodes:
        if node.node_type == NodeType.STEP:
            for slot in node.slots:
                if slot.target_var_key == var_key:
                    raise ValidationError(
                        f"Cannot delete variable '{var_key}' because it is referenced by Step node '{node.id}'."
                    )

    # 2. Check LOGICAL_ASSIGNER assignments target_var_key & expression
    for node in flow_data.nodes:
        if node.node_type == NodeType.LOGICAL_ASSIGNER and node.assignments is not None:
            for asgn in node.assignments:
                if asgn.target_var_key == var_key:
                    raise ValidationError(
                        f"Cannot delete variable '{var_key}' because it is referenced as assignment target in Assigner node '{node.id}'."
                    )
                if asgn.expression and is_variable_referenced_in_expression(asgn.expression, var_key):
                    raise ValidationError(
                        f"Cannot delete variable '{var_key}' because it is referenced in assignment expression in Assigner node '{node.id}'."
                    )

    # 3. Check SWITCH slot expressions
    for node in flow_data.nodes:
        if node.node_type == NodeType.SWITCH:
            for slot in node.slots:
                if slot.expression and is_variable_referenced_in_expression(slot.expression, var_key):
                    raise ValidationError(
                        f"Cannot delete variable '{var_key}' because it is referenced in Switch node '{node.id}' option '{slot.raw_string}'."
                    )

    # 4. Check AGENTIC_ASSIGNER inputs and outputs
    for node in flow_data.nodes:
        if node.node_type == NodeType.AGENTIC_ASSIGNER:
            if node.agentic_inputs and var_key in node.agentic_inputs:
                raise ValidationError(
                    f"Cannot delete variable '{var_key}' because it is referenced as an input in Agentic Assigner node '{node.id}'."
                )
            if node.agentic_outputs and var_key in node.agentic_outputs:
                raise ValidationError(
                    f"Cannot delete variable '{var_key}' because it is referenced as an output in Agentic Assigner node '{node.id}'."
                )

    flow_data.state = [v for v in flow_data.state if v.id != var_id]
    return flow_data


# ----------------------------------------------------
# Logical Assignment CRUD
# ----------------------------------------------------
def create_logical_assignment(
    flow_data: GraphFlowData,
    node_id: str,
    target_var_key: str,
    value_type: VariableType = "string",
    value: Any = None,
    expression: dict[str, Any] | None = None,
) -> GraphFlowData:
    target_var_key = target_var_key.strip()
    existing_vars = get_all_definer_variables(flow_data)
    if not any(v.key == target_var_key for v in existing_vars):
        raise ValidationError(f"Variable '{target_var_key}' is not defined in state schema.")

    valid_keys = {v.key for v in existing_vars}
    if expression is not None and not check_expression_variables(expression, valid_keys):
        raise ValidationError("Assignment expression references undefined variables.")

    validated_val = validate_default_value_type(value_type, value)

    nodes = flow_data.nodes
    target_node = next((n for n in nodes if n.id == node_id), None)
    if not target_node:
        raise ValidationError(f"Node '{node_id}' not found.")

    if target_node.assignments is None:
        target_node.assignments = []

    existing_asgn = next((a for a in target_node.assignments if a.target_var_key == target_var_key), None)
    if existing_asgn:
        existing_asgn.value_type = value_type
        existing_asgn.value = validated_val
        if expression is not None:
            existing_asgn.expression = expression
    else:
        new_asgn = LogicalAssignmentSchema(
            id=str(uuid.uuid4()),
            target_var_key=target_var_key,
            value_type=value_type,
            value=validated_val,
            expression=expression,
        )
        target_node.assignments.append(new_asgn)

    return flow_data


def update_logical_assignment(
    flow_data: GraphFlowData, assignment_id: str, updates: LogicalAssignmentUpdates
) -> GraphFlowData:
    for node in flow_data.nodes:
        if node.node_type == NodeType.LOGICAL_ASSIGNER and node.assignments is not None:
            for asgn in node.assignments:
                if asgn.id == assignment_id:
                    existing_vars = get_all_definer_variables(flow_data)
                    valid_keys = {v.key for v in existing_vars}

                    if "target_var_key" in updates and updates["target_var_key"]:
                        target_key = updates["target_var_key"].strip()
                        if not any(v.key == target_key for v in existing_vars):
                            raise ValidationError(f"Variable '{target_key}' is not defined in state schema.")
                        asgn.target_var_key = target_key

                    if "expression" in updates and updates["expression"] is not None:
                        if not check_expression_variables(updates["expression"], valid_keys):
                            raise ValidationError("Assignment expression references undefined variables.")
                        asgn.expression = updates["expression"]

                    val_type = updates.get("value_type") or asgn.value_type
                    if "value_type" in updates and updates["value_type"]:
                        asgn.value_type = updates["value_type"]
                    if "value" in updates:
                        asgn.value = validate_default_value_type(val_type, updates["value"])

                    return flow_data
    raise ValidationError(f"Logical Assignment with ID '{assignment_id}' not found.")


def delete_logical_assignment(flow_data: GraphFlowData, assignment_id: str) -> GraphFlowData:
    for node in flow_data.nodes:
        if node.node_type == NodeType.LOGICAL_ASSIGNER and node.assignments is not None:
            if any(a.id == assignment_id for a in node.assignments):
                node.assignments = [a for a in node.assignments if a.id != assignment_id]
                return flow_data
    raise ValidationError(f"Logical Assignment with ID '{assignment_id}' not found.")


# ----------------------------------------------------
# Switch Expression CRUD
# ----------------------------------------------------
def update_switch_expression(
    flow_data: GraphFlowData,
    slot_id: str,
    expression: dict[str, Any] | None,
    raw_string: str | None = None,
) -> GraphFlowData:
    """Updates a switch node slot expression and raw string, validating that referenced variables exist."""
    if expression is not None:
        valid_keys = {v.key for v in get_all_definer_variables(flow_data)}
        if not check_expression_variables(expression, valid_keys):
            raise ValidationError("Switch expression references undefined variables.")

    from app.graphs import topology as graph_topology

    return graph_topology.update_slot(flow_data, slot_id, raw_string=raw_string, expression=expression)
