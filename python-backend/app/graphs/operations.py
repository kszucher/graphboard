import re
import uuid
from typing import Any

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


def validate_and_coerce_default(var_type: str, val: Any) -> Any:
    if val is None or val == "":
        return None
    try:
        if var_type == "number":
            return int(val)
        if var_type == "float":
            return float(val)
        if var_type == "boolean":
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "1", "t", "yes")
            return bool(val)
        return str(val)
    except (ValueError, TypeError):
        raise ValueError(f"Default value '{val}' cannot be converted to type '{var_type}'.")


def get_all_definer_variables(flow_json: dict) -> list[dict]:
    ops = flow_json.get("operations", {})
    definer_ops = ops.get("definer", [])
    variables = []
    for op in definer_ops:
        variables.extend(op.get("variables", []))
    return variables


def create_definer_variable(
    flow_json: dict,
    node_id: str,
    key: str,
    var_type: str = "string",
    default_value: Any = None,
    description: str | None = None,
) -> dict:
    key = key.strip()
    # 1. snake_case regex validation
    if not re.match(r"^[a-z_][a-z0-9_]*$", key):
        raise ValueError(f"Variable name '{key}' must be valid snake_case.")

    # 2. Python keyword protection
    if key in PYTHON_KEYWORDS:
        raise ValueError(f"Variable name '{key}' cannot be a Python keyword.")

    # 3. Uniqueness validation across all definer operations
    existing_vars = get_all_definer_variables(flow_json)
    if any(v["key"] == key for v in existing_vars):
        raise ValueError(f"Variable name '{key}' already exists in state schema.")

    # 4. Default value type coercion & validation
    coerced_default = validate_and_coerce_default(var_type, default_value)

    nodes = flow_json.get("nodes", [])
    target_node = next((n for n in nodes if n["id"] == node_id), None)
    if not target_node:
        raise ValueError(f"Node '{node_id}' not found.")

    ops = flow_json.setdefault("operations", {"definer": [], "agentic": [], "logical": [], "switch": []})
    definer_ops = ops.setdefault("definer", [])

    ref_id = target_node.get("ref_id")
    target_op = next((o for o in definer_ops if o["id"] == ref_id), None) if ref_id else None

    if not target_op:
        ref_id = f"op_{node_id}"
        target_node["ref_id"] = ref_id
        target_op = {"id": ref_id, "variables": []}
        definer_ops.append(target_op)

    new_var = {
        "id": str(uuid.uuid4()),
        "key": key,
        "type": var_type,
        "default_value": coerced_default,
        "description": description,
    }
    target_op.setdefault("variables", []).append(new_var)
    return flow_json


def update_definer_variable(flow_json: dict, var_id: str, updates: dict) -> dict:
    ops = flow_json.get("operations", {})
    definer_ops = ops.get("definer", [])
    for op in definer_ops:
        for var in op.get("variables", []):
            if var["id"] == var_id:
                new_type = updates.get("type") or var.get("type", "string")
                if "type" in updates and updates["type"]:
                    var["type"] = updates["type"]
                if "default_value" in updates:
                    var["default_value"] = validate_and_coerce_default(new_type, updates["default_value"])
                if "description" in updates:
                    var["description"] = updates["description"]
                return flow_json
    return flow_json


def delete_definer_variable(flow_json: dict, var_id: str) -> dict:
    ops = flow_json.get("operations", {})
    definer_ops = ops.get("definer", [])
    for op in definer_ops:
        vars_list = op.get("variables", [])
        if any(v["id"] == var_id for v in vars_list):
            op["variables"] = [v for v in vars_list if v["id"] != var_id]
            return flow_json
    return flow_json
