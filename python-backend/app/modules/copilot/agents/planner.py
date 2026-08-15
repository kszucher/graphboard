from typing import Any

from app.modules.copilot.agents.planner_schemas import OperationPlan

PLANNER_SYSTEM_PROMPT = """
# GraphBoard Prisma Graph Update Planner

Analyze the user's graph edit request and produce a precise Prisma-style update query to apply changes to the graph flow, variables, and routing by calling the `submit_plan` tool **exactly once** with the complete `update` object containing ALL changes in a single atomic transaction. Do NOT call `submit_plan` multiple times.

## Graph Database Architecture:
The graph has state variables and nodes.
- Control flow (routing) is defined inline inside node definitions via the `target` parameter or switch branch `target` properties.
- Use `start_target` to configure the start entrypoint node.

## Prisma Update API Schema:
You will construct an update statement matching the Prisma update nested payload schema:
- `variables`:
  - `upsert`: Declares or updates global state variables (`key`, `type`, `default_value`, `description`).
    * **Constraint**: `type` MUST be one of: `"boolean"`, `"bool"`, `"string"`, `"number"`, `"float"`, `"int"`, `"integer"`.
    * **Strict Constraint**: You MUST declare a variable in `variables.upsert` before referencing it in any node assignment or branch expression!
  - `delete`: List of variable keys to delete.
- `nodes`:
  - `upsert`: List of node definitions to create or update.
  - `delete`: List of node IDs to delete.
- `rename_variables`: List of variable renames (`old_key`, `new_key`).
- `rename_nodes`: List of node renames (`old_key`, `new_key`).

## Node Types and Field Mappings:
- `LOGICAL_ASSIGNER`: Uses `assignments: [{"target_var_key": "x", "expression": ...}]`.
- `LOGICAL_SWITCH`: Uses `branches: {"LabelA": {"expression": ..., "target": "dest"}, "LabelB": {"target": "end"}}`. Dict keys are branch labels (unique by structure). Omit `expression` on a branch to make it a fallback "else".
- `AGENTIC_ASSIGNER`: Uses `prompt`, `agentic_inputs: [...]`, `agentic_outputs: [{"key": "out", "type": "string"}]`.
- `AGENTIC_SWITCH`: Uses `agentic_input`, `branches: {"LabelA": {"target": "dest"}, "LabelB": {"target": "other"}}`.
- `RAG_RETRIEVER`: Uses `query_var`, `context_output_var`, `knowledge_base`, `top_k`.
- `INTERRUPT`: Uses `payload_vars: [...]`, `resume_var`, `resume_var_type`.

## Rules for Prisma Filter Expressions:
Logical switch branch expressions are defined as Prisma-style nested query objects:
- Standard comparison: `{"score": {"gt": 5}}` or `{"more_questions": {"equals": false}}`
- Reference another variable: `{"parsed_answer": {"equals": {"var": "correct_answer"}}}`
- Operators supported: `equals`, `not`, `in`, `lt`, `lte`, `gt`, `gte`
- Logical composition:
  - `{"AND": [{"score": {"gt": 5}}, {"more_questions": {"equals": false}}]}`
  - `{"OR": [...]}`
  - `{"NOT": {"score": {"equals": 0}}}`

## Rules for Prisma Atomic Update Assignments:
Assignments inside `LOGICAL_ASSIGNER` use standard atomic update structures:
- Set value: `{"set": 10}` or `{"set": {"var": "user_input"}}` or simply a scalar value like `10` or `"topic"`
- Numeric operators: `{"increment": 1}`, `{"decrement": 5}`, `{"multiply": 2}`, `{"divide": 3}`
"""


def prune_json_schema(schema: Any) -> Any:
    """Recursively removes title metadata from the JSON schema to save token overhead."""
    if isinstance(schema, dict):
        return {k: prune_json_schema(v) for k, v in schema.items() if k != "title"}
    elif isinstance(schema, list):
        return [prune_json_schema(item) for item in schema]
    return schema


async def generate_plan(client: Any, trace_id: str, graph_id: str, messages: list[dict[str, Any]]) -> OperationPlan:
    """Invokes the LLM to produce a structured operation plan."""
    import json
    import os

    from app.modules.copilot.logger import log_llm_call

    model_name = os.environ.get("COPILOT_MODEL", "llama-3.3-70b-versatile")
    req_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}] + messages

    tool_schema = {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": "Submits the Prisma update graph payload.",
            "parameters": prune_json_schema(OperationPlan.model_json_schema()),
        },
    }

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=req_messages,
            tools=[tool_schema],
            tool_choice={"type": "function", "function": {"name": "submit_plan"}},
            parallel_tool_calls=False,
            temperature=0.0,
        )
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model=model_name,
            messages=req_messages,
            response=response,
            graph_id=graph_id,
        )
    except Exception as e:
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model=model_name,
            messages=req_messages,
            error=str(e),
            graph_id=graph_id,
        )
        raise e

    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise Exception("Planner failed to generate a plan tool call.")

    try:
        args = json.loads(tool_calls[0].function.arguments)
        return OperationPlan.model_validate(args)
    except Exception as e:
        raise Exception(f"Failed to validate planner tool call arguments: {str(e)}")
