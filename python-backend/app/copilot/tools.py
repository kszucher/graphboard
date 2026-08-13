from __future__ import annotations

from typing import Any, get_args

from app.graphs.schemas import GraphOperation

# Extract union members dynamically from GraphOperation (Annotated[Union[...], Field(...)])
union_wrapper = get_args(GraphOperation)[0]
operation_classes = get_args(union_wrapper)


def prune_json_schema(schema: Any, is_inside_defs: bool = False) -> Any:
    """Recursively prunes unnecessary fields from the JSON Schema to optimize LLM tokens."""
    if isinstance(schema, dict):
        schema.pop("title", None)
        if is_inside_defs:
            schema.pop("description", None)

        for k, v in list(schema.items()):
            next_inside_defs = is_inside_defs or (k == "$defs")
            schema[k] = prune_json_schema(v, next_inside_defs)
    elif isinstance(schema, list):
        return [prune_json_schema(item, is_inside_defs) for item in schema]
    return schema


ALL_FLAT_TOOLS = {}

for cls in operation_classes:
    op_name = cls.model_fields["op"].default
    raw_schema = cls.model_json_schema()
    pruned_schema = prune_json_schema(raw_schema)
    ALL_FLAT_TOOLS[op_name] = {
        "type": "function",
        "function": {
            "name": op_name,
            "description": cls.__doc__.strip() if cls.__doc__ else f"Execute {op_name}",
            "parameters": pruned_schema,
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
