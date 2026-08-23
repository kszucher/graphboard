from __future__ import annotations

from typing import Any, cast


def prune_json_schema(schema: Any) -> Any:
    """Recursively removes title metadata from the JSON schema to save token overhead."""
    if isinstance(schema, dict):
        return {k: prune_json_schema(v) for k, v in schema.items() if k != "title"}
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
