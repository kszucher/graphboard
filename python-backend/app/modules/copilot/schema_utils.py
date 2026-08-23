from __future__ import annotations

from typing import Any, cast


def prune_json_schema(schema: Any) -> Any:
    """Recursively prunes title metadata, default: null, and collapses anyOf: [T, {type: 'null'}] -> T."""
    if isinstance(schema, dict):
        # 1. Collapse anyOf: [T, {'type': 'null'}] -> T (zero-risk nullable union pruning)
        if "anyOf" in schema and len(schema["anyOf"]) == 2:
            non_null_variants = [t for t in schema["anyOf"] if t != {"type": "null"}]
            if len(non_null_variants) == 1:
                inner = prune_json_schema(non_null_variants[0])
                if isinstance(inner, dict):
                    # Preserve outer field attributes like description if not on inner
                    for k, v in schema.items():
                        if k not in {"anyOf", "title"} and k not in inner:
                            if k == "default" and v is None:
                                continue
                            inner[k] = prune_json_schema(v)
                    return inner

        cleaned: dict[str, Any] = {}
        for k, v in schema.items():
            if k == "title":
                continue
            if k == "default" and v is None:
                continue
            cleaned[k] = prune_json_schema(v)
        return cleaned

    elif isinstance(schema, list):
        return [prune_json_schema(item) for item in schema]

    return schema


def dereference_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively resolves $ref keys in a JSON schema using definitions from $defs."""
    if not isinstance(schema, dict):
        return schema

    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]
                parts = ref_path.split("/")
                def_name = parts[-1]
                if def_name in defs:
                    return resolve(defs[def_name])
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        elif isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return cast(dict[str, Any], resolve(schema))
