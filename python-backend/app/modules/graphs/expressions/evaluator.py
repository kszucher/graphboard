from __future__ import annotations

import random
import re
from typing import Any

from app.core.exceptions import ValidationError


def eval_value(val: Any, state: dict[str, Any]) -> Any:
    """Evaluates a value (literal or variable reference) against the runtime state."""
    if isinstance(val, dict):
        if "var" in val:
            var_name = val["var"]
            if not isinstance(var_name, str):
                raise ValidationError("Variable reference 'var' must be a string.")
            return state.get(var_name)
        if "op" in val:
            return evaluate_expression(val, state)
    if isinstance(val, list):
        return [eval_value(x, state) for x in val]
    return val


def eval_comparison(left_val: Any, op: str, filter_val: Any, state: dict[str, Any]) -> bool:
    """Evaluates a comparison operator between a variable value and filter value."""
    right_val = eval_value(filter_val, state)

    if op in {"equals", "eq"}:
        return bool(left_val == right_val)
    if op in {"not_equals", "ne", "not"}:
        return bool(left_val != right_val)
    if op == "lt":
        return bool(left_val < right_val)
    if op == "lte":
        return bool(left_val <= right_val)
    if op == "gt":
        return bool(left_val > right_val)
    if op == "gte":
        return bool(left_val >= right_val)
    if op in {"in", "isin"}:
        if isinstance(right_val, (list, tuple, set)):
            return bool(left_val in right_val)
        return False

    raise ValidationError(f"Unsupported operator '{op}'.")


def evaluate_expression(expr_data: Any | None, state: dict[str, Any], target_var_key: str | None = None) -> Any:
    """Safely evaluates a structured expression in pure Python against runtime state."""
    if expr_data is None:
        return None

    if not isinstance(expr_data, dict):
        return eval_value(expr_data, state)

    # 1. Compound logic (AND, OR, NOT)
    if "AND" in expr_data:
        parts = expr_data["AND"]
        if not isinstance(parts, list):
            raise ValidationError("Logical 'AND' must be a list of condition blocks.")
        return all(bool(evaluate_expression(p, state, target_var_key)) for p in parts)

    if "OR" in expr_data:
        parts = expr_data["OR"]
        if not isinstance(parts, list):
            raise ValidationError("Logical 'OR' must be a list of condition blocks.")
        return any(bool(evaluate_expression(p, state, target_var_key)) for p in parts)

    if "NOT" in expr_data:
        return not bool(evaluate_expression(expr_data["NOT"], state, target_var_key))

    # 2. Variable reference or literal set
    if "var" in expr_data and len(expr_data) == 1:
        return eval_value(expr_data, state)

    if "set" in expr_data:
        return eval_value(expr_data["set"], state)

    # 3. Atomic updates on target variable
    atomic_ops = {"increment", "decrement", "multiply", "divide"}
    if any(op in expr_data for op in atomic_ops) and "op" not in expr_data:
        if target_var_key is None:
            raise ValidationError("Atomic operations require a target variable context.")
        current_val = state.get(target_var_key, 0) or 0
        if "increment" in expr_data:
            return current_val + eval_value(expr_data["increment"], state)
        if "decrement" in expr_data:
            return current_val - eval_value(expr_data["decrement"], state)
        if "multiply" in expr_data:
            return current_val * eval_value(expr_data["multiply"], state)
        if "divide" in expr_data:
            return current_val / eval_value(expr_data["divide"], state)

    # 4. Orthogonal algebraic operations ("op": ...)
    if "op" in expr_data:
        op = expr_data["op"]

        # Math
        if op == "add":
            return eval_value(expr_data.get("left", 0), state) + eval_value(expr_data.get("right", 0), state)
        if op == "subtract":
            return eval_value(expr_data.get("left", 0), state) - eval_value(expr_data.get("right", 0), state)
        if op == "multiply":
            return eval_value(expr_data.get("left", 0), state) * eval_value(expr_data.get("right", 0), state)
        if op == "divide":
            return eval_value(expr_data.get("left", 0), state) / eval_value(expr_data.get("right", 1), state)
        if op == "modulo":
            return eval_value(expr_data.get("left", 0), state) % eval_value(expr_data.get("right", 1), state)
        if op == "round":
            val = eval_value(expr_data.get("val", 0), state)
            ndigits = expr_data.get("ndigits")
            if ndigits is not None:
                return round(val, eval_value(ndigits, state))
            return round(val)
        if op == "min":
            args = [eval_value(a, state) for a in expr_data.get("args", [])]
            return min(args) if args else None
        if op == "max":
            args = [eval_value(a, state) for a in expr_data.get("args", [])]
            return max(args) if args else None
        if op == "random_int":
            min_i = int(eval_value(expr_data.get("min", 0), state))
            max_i = int(eval_value(expr_data.get("max", 100), state))
            return random.randint(min_i, max_i)
        if op == "random_float":
            min_f = float(eval_value(expr_data.get("min", 0.0), state))
            max_f = float(eval_value(expr_data.get("max", 1.0), state))
            return random.uniform(min_f, max_f)

        # Strings
        if op == "format":
            template = expr_data.get("template", "")
            vars_list = expr_data.get("vars")
            if vars_list is None:
                vars_list = re.findall(r"\{([a-zA-Z0-9_]+)\}", template)
            kwargs = {v: state.get(v) for v in vars_list}
            return template.format(**kwargs)
        if op == "join":
            items = (
                eval_value(expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), state) or []
            )
            sep = str(eval_value(expr_data.get("sep", "\n"), state))
            return sep.join(str(x) for x in items)
        if op == "split":
            text = str(
                eval_value(expr_data.get("text") if "text" in expr_data else expr_data.get("str", ""), state) or ""
            )
            sep = str(eval_value(expr_data.get("sep", " "), state))
            return text.split(sep)

        # Collections & Sampling
        if op == "sample":
            items = (
                eval_value(expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), state) or []
            )
            count = int(eval_value(expr_data.get("count", 1), state))
            sample_size = min(len(items), count)
            return random.sample(items, sample_size)
        if op == "choice":
            items = (
                eval_value(expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), state) or []
            )
            return random.choice(items) if items else None
        if op == "remove":
            items = (
                eval_value(expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), state) or []
            )
            item_val = eval_value(expr_data.get("item"), state)
            if isinstance(item_val, list):
                return [x for x in items if x not in item_val]
            return [x for x in items if x != item_val]
        if op == "append":
            items = list(
                eval_value(expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), state) or []
            )
            item_val = eval_value(expr_data.get("item"), state)
            items.append(item_val)
            return items
        if op == "length":
            items = (
                eval_value(expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), state) or []
            )
            return len(items)
        if op == "slice":
            items = (
                eval_value(expr_data.get("items") if "items" in expr_data else expr_data.get("list", []), state) or []
            )
            start = expr_data.get("start")
            end = expr_data.get("end")
            start_idx = int(eval_value(start, state)) if start is not None else None
            end_idx = int(eval_value(end, state)) if end is not None else None
            return items[start_idx:end_idx]

        raise ValidationError(f"Unsupported expression operation '{op}'.")

    # 5. Field comparisons: {"score": {"gt": 5}}
    conditions = []
    for var_name, filter_block in expr_data.items():
        left_val = state.get(var_name)
        if isinstance(filter_block, dict):
            for op, val in filter_block.items():
                conditions.append(eval_comparison(left_val, op, val, state))
        else:
            conditions.append(eval_comparison(left_val, "equals", filter_block, state))

    return all(conditions) if conditions else True
