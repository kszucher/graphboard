from __future__ import annotations

import copy
from typing import Any, get_args

from app.graphs.schemas import GraphOperation

# Extract union members dynamically from GraphOperation (Annotated[Union[...], Field(...)])
union_wrapper = get_args(GraphOperation)[0]
operation_classes = get_args(union_wrapper)

# Names of recursive AST expression types — their nested children are depth-capped
_EXPR_DEF_NAMES = {"BinaryExpr", "UnaryExpr", "FunctionCallExpr", "LiteralExpr", "VariableExpr"}


def _resolve_refs(schema: Any, defs: dict[str, Any], depth: int, max_depth: int) -> Any:
    """Recursively resolves $ref pointers inline, capping depth on recursive expression types."""
    if not isinstance(schema, dict):
        if isinstance(schema, list):
            return [_resolve_refs(item, defs, depth, max_depth) for item in schema]
        return schema

    # Resolve $ref
    if "$ref" in schema:
        ref_path = schema["$ref"]  # e.g. "#/$defs/BinaryExpr"
        def_name = ref_path.split("/")[-1]
        if def_name in defs:
            if depth >= max_depth and def_name in _EXPR_DEF_NAMES:
                # At max depth, replace recursive expression refs with a simple object stub
                # that still shows the discriminator `type` field so the LLM knows it's an AST node
                return {"type": "object"}
            return _resolve_refs(copy.deepcopy(defs[def_name]), defs, depth + 1, max_depth)
        return schema

    resolved: dict[str, Any] = {}
    for k, v in schema.items():
        if k == "$defs":
            continue  # drop $defs block after inlining
        resolved[k] = _resolve_refs(v, defs, depth, max_depth)
    return resolved


def _prune(schema: Any, is_inside_defs: bool = False) -> Any:
    """Strips noisy metadata fields from a schema dict."""
    if isinstance(schema, dict):
        schema.pop("title", None)
        schema.pop("discriminator", None)
        if is_inside_defs:
            schema.pop("description", None)

        # Collapse oneOf -> anyOf (discriminator is gone; anyOf is sufficient for LLM guidance)
        if "oneOf" in schema and "anyOf" not in schema:
            schema["anyOf"] = schema.pop("oneOf")

        for k, v in list(schema.items()):
            schema[k] = _prune(v, is_inside_defs or k == "$defs")
    elif isinstance(schema, list):
        return [_prune(item, is_inside_defs) for item in schema]
    return schema


def _simplify(schema: Any) -> Any:
    """Post-resolution cleanup: collapses redundant anyOf stubs and flattens double-wrapped anyOf."""
    if isinstance(schema, list):
        return [_simplify(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    # Recurse first
    schema = {k: _simplify(v) for k, v in schema.items()}

    if "anyOf" in schema:
        variants = schema["anyOf"]
        # Collapse all-identical-object stubs: [{type:object}, {type:object}, ...] -> {type:object}
        if all(v == {"type": "object"} for v in variants):
            schema.pop("anyOf")
            schema["type"] = "object"
            return schema
        # Flatten single-element anyOf
        if len(variants) == 1:
            schema.pop("anyOf")
            schema.update(variants[0])
            return schema
        # Flatten nested anyOf: anyOf containing one anyOf + null -> merge
        flat: list[Any] = []
        for v in variants:
            if isinstance(v, dict) and list(v.keys()) == ["anyOf"]:
                flat.extend(v["anyOf"])
            else:
                flat.append(v)
        schema["anyOf"] = flat

    return schema


def build_tool_schema(raw_schema: dict[str, Any], max_expr_depth: int = 2) -> dict[str, Any]:
    """Produces a compact, ref-free tool parameter schema.

    1. Prunes noisy metadata (titles, discriminators).
    2. Resolves all $refs inline, capping recursive expression nesting at max_expr_depth.
    3. Drops the now-unnecessary $defs block.
    4. Simplifies redundant anyOf stubs produced by depth capping.
    """
    pruned = _prune(copy.deepcopy(raw_schema))
    defs = pruned.get("$defs", {})
    resolved = _resolve_refs(pruned, defs, depth=0, max_depth=max_expr_depth)
    result = _simplify(resolved)
    assert isinstance(result, dict)
    return result


ALL_FLAT_TOOLS: dict[str, Any] = {}

# upsert_expression owns the full AST schema — depth 1 is enough:
# top-level variants are fully described; recursive children are stubbed as {type:object}.
# Other tools (assigner/switch) carry no AST at all — depth irrelevant.
_EXPR_DEPTH: dict[str, int] = {"upsert_expression": 1}

for cls in operation_classes:
    op_name = cls.model_fields["op"].default
    raw_schema = cls.model_json_schema()
    compact_schema = build_tool_schema(raw_schema, max_expr_depth=_EXPR_DEPTH.get(op_name, 2))
    ALL_FLAT_TOOLS[op_name] = {
        "type": "function",
        "function": {
            "name": op_name,
            "description": cls.__doc__.strip() if cls.__doc__ else f"Execute {op_name}",
            "parameters": compact_schema,
        },
    }


def translate_tool_calls_to_operations(tool_calls: list[Any]) -> list[GraphOperation]:
    """Translates raw LLM tool call dictionaries to GraphOperation instances."""
    from pydantic import TypeAdapter

    ops: list[GraphOperation] = []
    for tc in tool_calls:
        func_name = tc.function.name
        args_str = tc.function.arguments

        import json

        try:
            args = json.loads(args_str)
        except Exception:
            args = {}

        args["op"] = func_name
        ops.append(TypeAdapter(GraphOperation).validate_python(args))
    return ops
