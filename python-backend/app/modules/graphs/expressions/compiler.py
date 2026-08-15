from __future__ import annotations

from typing import Any

from app.core.exceptions import ValidationError


def compile_value(val: Any, valid_keys: set[str] | None = None) -> str:
    """Compiles a value (literal or variable reference) to python code."""
    if isinstance(val, dict) and "var" in val:
        var_name = val["var"]
        if not isinstance(var_name, str):
            raise ValidationError("Variable reference 'var' must be a string.")
        if valid_keys is not None and var_name not in valid_keys:
            raise ValidationError(f"Variable '{var_name}' is not defined in the graph state.")
        return f"state.get({repr(var_name)})"
    if isinstance(val, str):
        return repr(val)
    if isinstance(val, (int, float, bool)):
        return str(val)
    if val is None:
        return "None"
    return repr(val)


def compile_comparison(var_name: str, op: str, filter_val: Any, valid_keys: set[str] | None = None) -> str:
    """Compiles a single field comparison operator to python code."""
    if valid_keys is not None and var_name not in valid_keys:
        raise ValidationError(f"Variable '{var_name}' is not defined in the graph state.")

    left = f"state.get({repr(var_name)})"
    right = compile_value(filter_val, valid_keys)

    op_mapping = {
        "equals": "==",
        "eq": "==",
        "ne": "!=",
        "not": "!=",
        "lt": "<",
        "lte": "<=",
        "gt": ">",
        "gte": ">=",
    }

    if op in op_mapping:
        return f"({left} {op_mapping[op]} {right})"

    if op in {"in", "isin"}:
        if not isinstance(filter_val, list):
            raise ValidationError("Operator 'in' requires a list value.")
        list_items = [compile_value(item, valid_keys) for item in filter_val]
        return f"({left} in [{', '.join(list_items)}])"

    raise ValidationError(f"Unsupported operator '{op}'.")


def expression_to_code(
    expr_data: Any | None, valid_keys: set[str], fallback: str = "True", target_var_key: str | None = None
) -> str:
    """Converts a Prisma-style structured expression object to safe executable Python code."""
    if expr_data is None:
        return fallback

    if not isinstance(expr_data, dict):
        # Fallback to scalar compilation if it's not a dictionary query
        return compile_value(expr_data, valid_keys)

    # 1. Handle logical operators at the top level
    if "AND" in expr_data:
        parts = expr_data["AND"]
        if not isinstance(parts, list):
            raise ValidationError("Logical 'AND' must be a list of condition blocks.")
        compiled_parts = [expression_to_code(p, valid_keys, fallback, target_var_key) for p in parts]
        if len(compiled_parts) == 1:
            return compiled_parts[0]
        return f"({' and '.join(compiled_parts)})"

    if "OR" in expr_data:
        parts = expr_data["OR"]
        if not isinstance(parts, list):
            raise ValidationError("Logical 'OR' must be a list of condition blocks.")
        compiled_parts = [expression_to_code(p, valid_keys, fallback, target_var_key) for p in parts]
        if len(compiled_parts) == 1:
            return compiled_parts[0]
        return f"({' or '.join(compiled_parts)})"

    if "NOT" in expr_data:
        part = expr_data["NOT"]
        return f"(not {expression_to_code(part, valid_keys, fallback, target_var_key)})"

    # 2. Handle atomic updates (increment, decrement, multiply, divide, set)
    atomic_ops = {"increment", "decrement", "multiply", "divide", "set"}
    if any(op in expr_data for op in atomic_ops):
        if "set" in expr_data:
            return compile_value(expr_data["set"], valid_keys)

        if target_var_key is None:
            raise ValidationError("Atomic operations require a target variable context.")

        left = f"state.get({repr(target_var_key)})"
        if "increment" in expr_data:
            return f"{left} + {compile_value(expr_data['increment'], valid_keys)}"
        if "decrement" in expr_data:
            return f"{left} - {compile_value(expr_data['decrement'], valid_keys)}"
        if "multiply" in expr_data:
            return f"{left} * {compile_value(expr_data['multiply'], valid_keys)}"
        if "divide" in expr_data:
            return f"{left} / {compile_value(expr_data['divide'], valid_keys)}"

    # 3. Handle standard field comparison blocks: {"score": {"gt": 5}}
    compiled_conditions = []
    for var_name, filter_block in expr_data.items():
        if isinstance(filter_block, dict):
            for op, val in filter_block.items():
                compiled_conditions.append(compile_comparison(var_name, op, val, valid_keys))
        else:
            # Shorthand for equals: {"score": 5} -> {"score": {"equals": 5}}
            compiled_conditions.append(compile_comparison(var_name, "equals", filter_block, valid_keys))

    if not compiled_conditions:
        return fallback

    if len(compiled_conditions) == 1:
        return compiled_conditions[0]

    return f"({' and '.join(compiled_conditions)})"


def get_expression_variables(expr_data: Any | None) -> set[str]:
    """Recursively extracts all variable name references from the structured expression."""
    if expr_data is None:
        return set()

    variables = set()

    if isinstance(expr_data, dict):
        if "var" in expr_data:
            if isinstance(expr_data["var"], str):
                variables.add(expr_data["var"])
            return variables

        for k, v in expr_data.items():
            if k in {"AND", "OR"}:
                if isinstance(v, list):
                    for item in v:
                        variables.update(get_expression_variables(item))
            elif k == "NOT":
                variables.update(get_expression_variables(v))
            elif k in {"increment", "decrement", "multiply", "divide", "set"}:
                variables.update(get_expression_variables(v))
            else:
                # k is a variable name being queried
                variables.add(k)
                # v might contain variable references inside its filter, e.g. {"equals": {"var": "other"}}
                if isinstance(v, dict):
                    for op_val in v.values():
                        variables.update(get_expression_variables(op_val))
                else:
                    variables.update(get_expression_variables(v))
    elif isinstance(expr_data, list):
        for item in expr_data:
            variables.update(get_expression_variables(item))

    return variables


def rename_expression_variables(expr_data: Any | None, old_key: str, new_key: str) -> Any | None:
    """Recursively renames all references of old_key to new_key inside structured expression."""
    if expr_data is None:
        return None

    if isinstance(expr_data, dict):
        new_dict: dict[str, Any] = {}
        for k, v in expr_data.items():
            current_key = new_key if k == old_key else k
            if k == "var" and v == old_key:
                new_dict[k] = new_key
            else:
                new_dict[current_key] = rename_expression_variables(v, old_key, new_key)
        return new_dict

    if isinstance(expr_data, list):
        return [rename_expression_variables(item, old_key, new_key) for item in expr_data]

    return expr_data
