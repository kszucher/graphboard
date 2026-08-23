from __future__ import annotations

import re
from typing import Any, TypeAlias

from app.core.exceptions import ValidationError

Expression: TypeAlias = str | int | float | bool | dict[str, Any]
ComparisonExpression: TypeAlias = dict[str, Any] | bool


def compile_value(val: Any, valid_keys: set[str] | None = None) -> str:
    """Compiles a value (literal or variable reference) to python code."""
    if isinstance(val, dict):
        if "var" in val:
            var_name = val["var"]
            if not isinstance(var_name, str):
                raise ValidationError("Variable reference 'var' must be a string.")
            if valid_keys is not None and var_name not in valid_keys:
                raise ValidationError(f"Variable '{var_name}' is not defined in the graph state.")
            return f"state.get({repr(var_name)})"
        # If it's a nested sub-expression with "op"
        if "op" in val:
            return expression_to_code(val, valid_keys or set())
    if isinstance(val, str):
        return repr(val)
    if isinstance(val, (int, float, bool)):
        return str(val)
    if isinstance(val, list):
        items = [compile_value(x, valid_keys) for x in val]
        return f"[{', '.join(items)}]"
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
        "not_equals": "!=",
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
        if isinstance(filter_val, list):
            list_items = [compile_value(item, valid_keys) for item in filter_val]
            return f"({left} in [{', '.join(list_items)}])"
        else:
            return f"({left} in {compile_value(filter_val, valid_keys)})"

    raise ValidationError(f"Unsupported operator '{op}'.")


def expression_to_code(
    expr_data: Any | None, valid_keys: set[str], fallback: str = "True", target_var_key: str | None = None
) -> str:
    """Converts a structured expression object to safe executable Python code."""
    if expr_data is None:
        return fallback

    if not isinstance(expr_data, dict):
        return compile_value(expr_data, valid_keys)

    # 1. Handle logical operators at top level (for Switch conditions)
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

    # 2. Handle variable reference or literal set
    if "var" in expr_data and len(expr_data) == 1:
        return compile_value(expr_data, valid_keys)

    if "set" in expr_data:
        return compile_value(expr_data["set"], valid_keys)

    # 3. Handle atomic target variable deltas
    atomic_ops = {"increment", "decrement", "multiply", "divide"}
    if any(op in expr_data for op in atomic_ops) and "op" not in expr_data:
        if target_var_key is None:
            raise ValidationError("Atomic operations require a target variable context.")
        left = f"state.get({repr(target_var_key)})"
        if "increment" in expr_data:
            return f"({left} + {compile_value(expr_data['increment'], valid_keys)})"
        if "decrement" in expr_data:
            return f"({left} - {compile_value(expr_data['decrement'], valid_keys)})"
        if "multiply" in expr_data:
            return f"({left} * {compile_value(expr_data['multiply'], valid_keys)})"
        if "divide" in expr_data:
            return f"({left} / {compile_value(expr_data['divide'], valid_keys)})"

    # 4. Handle orthogonal algebraic operations ("op": ...)
    if "op" in expr_data:
        op = expr_data["op"]

        # A. Math Operations
        math_binary = {
            "add": "+",
            "subtract": "-",
            "multiply": "*",
            "divide": "/",
            "modulo": "%",
        }
        if op in math_binary:
            left = compile_value(expr_data.get("left", 0), valid_keys)
            right = compile_value(expr_data.get("right", 0), valid_keys)
            return f"({left} {math_binary[op]} {right})"

        if op == "round":
            val = compile_value(expr_data.get("val", 0), valid_keys)
            ndigits = expr_data.get("ndigits")
            if ndigits is not None:
                return f"round({val}, {compile_value(ndigits, valid_keys)})"
            return f"round({val})"

        if op in {"min", "max"}:
            args = expr_data.get("args", [])
            compiled_args = [compile_value(a, valid_keys) for a in args]
            return f"{op}({', '.join(compiled_args)})"

        if op == "random_int":
            min_val = compile_value(expr_data.get("min", 0), valid_keys)
            max_val = compile_value(expr_data.get("max", 100), valid_keys)
            return f"random.randint({min_val}, {max_val})"

        if op == "random_float":
            min_val = compile_value(expr_data.get("min", 0.0), valid_keys)
            max_val = compile_value(expr_data.get("max", 1.0), valid_keys)
            return f"random.uniform({min_val}, {max_val})"

        # B. String Operations
        if op == "format":
            template = expr_data.get("template", "")
            vars_list = expr_data.get("vars")
            if vars_list is None:
                vars_list = re.findall(r"\{([a-zA-Z0-9_]+)\}", template)
            kwargs_parts = [f"{v}=state.get({repr(v)})" for v in vars_list]
            return f"{repr(template)}.format({', '.join(kwargs_parts)})"

        if op == "join":
            list_val = compile_value(
                expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), valid_keys
            )
            sep = compile_value(expr_data.get("sep", "\n"), valid_keys)
            return f"{sep}.join(str(x) for x in ({list_val} or []))"

        if op == "split":
            str_val = compile_value(
                expr_data.get("text") if "text" in expr_data else expr_data.get("str", ""), valid_keys
            )
            sep = compile_value(expr_data.get("sep", " "), valid_keys)
            return f"({str_val} or '').split({sep})"

        # C. Collection & Sampling Operations
        if op == "sample":
            list_val = compile_value(
                expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), valid_keys
            )
            count = compile_value(expr_data.get("count", 1), valid_keys)
            return f"random.sample(({list_val} or []), min(len({list_val} or []), {count}))"

        if op == "choice":
            list_val = compile_value(
                expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), valid_keys
            )
            return f"(random.choice({list_val}) if ({list_val}) else None)"

        if op == "remove":
            list_val = compile_value(
                expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), valid_keys
            )
            item_val = compile_value(expr_data.get("item"), valid_keys)
            return f"[x for x in ({list_val} or []) if (x not in {item_val} if isinstance({item_val}, list) else x != {item_val})]"

        if op == "append":
            list_val = compile_value(
                expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), valid_keys
            )
            item_val = compile_value(expr_data.get("item"), valid_keys)
            return f"(({list_val} or []) + [{item_val}])"

        if op == "length":
            list_val = compile_value(
                expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), valid_keys
            )
            return f"len({list_val} or [])"

        if op == "slice":
            list_val = compile_value(
                expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), valid_keys
            )
            start = expr_data.get("start")
            end = expr_data.get("end")
            start_str = compile_value(start, valid_keys) if start is not None else ""
            end_str = compile_value(end, valid_keys) if end is not None else ""
            return f"(({list_val} or [])[{start_str}:{end_str}])"

        raise ValidationError(f"Unsupported expression operation '{op}'.")

    # 5. Handle standard field comparison blocks: {"score": {"gt": 5}}
    compiled_conditions = []
    for var_name, filter_block in expr_data.items():
        if isinstance(filter_block, dict):
            for op, val in filter_block.items():
                compiled_conditions.append(compile_comparison(var_name, op, val, valid_keys))
        else:
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

    variables: set[str] = set()

    if isinstance(expr_data, dict):
        if "var" in expr_data and isinstance(expr_data["var"], str):
            variables.add(expr_data["var"])
            return variables

        if "vars" in expr_data and isinstance(expr_data["vars"], list):
            for v in expr_data["vars"]:
                if isinstance(v, str):
                    variables.add(v)

        for k, v in expr_data.items():
            if k in {"AND", "OR", "args"}:
                if isinstance(v, list):
                    for item in v:
                        variables.update(get_expression_variables(item))
            elif k in {
                "NOT",
                "left",
                "right",
                "val",
                "list",
                "items",
                "text",
                "str",
                "item",
                "count",
                "min",
                "max",
                "set",
                "increment",
                "decrement",
                "multiply",
                "divide",
            }:
                variables.update(get_expression_variables(v))
            elif k not in {"op", "template", "sep", "start", "end", "ndigits", "vars", "var"}:
                variables.add(k)
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
            elif k == "vars" and isinstance(v, list):
                new_dict[k] = [new_key if item == old_key else item for item in v]
            else:
                new_dict[current_key] = rename_expression_variables(v, old_key, new_key)
        return new_dict

    if isinstance(expr_data, list):
        return [rename_expression_variables(item, old_key, new_key) for item in expr_data]

    return expr_data
