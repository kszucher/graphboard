from typing import Any

from pydantic import BaseModel, Field

from app.modules.graphs.operations import GraphOperation

PLANNER_SYSTEM_PROMPT = """
# GraphBoard Operation Planner

Analyze the user's graph edit request and produce a precise, flat list of graph operations to apply by calling the `submit_plan` tool.

## Graph Primitives and Architecture:
- The graph is represented as a list of Python-like state variables and functional node statements.
- Edge connections are serialized inline (`source() -> target`).
- Expressions are written inline inside logic nodes.

## Available Operations:
1. `upsert_logical_assigner`: Creates/updates a logical assignment node. Takes `assignments` which is a list of `{"target_var_key": "x", "expression": "col('y').eq(5)"}`.
   - Note: Variables are automatically declared if assigned as a target. You do NOT need to declare them manually!
2. `upsert_agentic_assigner`: Creates/updates an AI prompt step. Takes `agentic_inputs`, `agentic_outputs` (list of `{"key": "a", "type": "string"}`), and `prompt`.
3. `upsert_rag_retriever`: Creates/updates a database search step. Takes `query_var`, `context_output_var`, `knowledge_base`, and `top_k`.
4. `upsert_logical_switch`: Creates/updates a conditional switch node. Takes `branches` which is a list of `{"label": "Yes", "expression": "col('score').gt(5)"}`.
5. `upsert_agentic_switch`: Creates/updates an AI decision switch. Takes `agentic_input` and `branches` (list of branch labels).
6. `upsert_interrupt`: Creates/updates a human-input checkpoint. Takes `payload_vars`, `resume_var`, and `resume_var_type`.
7. `delete_node`: Deletes a node. Connections are deleted automatically. You must manually reconnect paths if needed!
8. `rename_node`: Renames a node ID. Updates all connected edges.
9. `rename_variable`: Renames a state variable. Updates all expression and prompt references automatically.
10. `connect_nodes`: Wires an edge from `source` to `target`. If the source node is a switch (LOGICAL_SWITCH or AGENTIC_SWITCH), you MUST specify the branch label / case option name in the `source_handle` parameter.
11. `disconnect_nodes`: Unwires an edge. If the source node is a switch, you MUST specify the branch label / case option name in the `source_handle` parameter.

## Rules for Expressions:
Expressions inside logic/switch nodes must be defined as Polars-style method-chained strings (NOT standard Python).
- Refer to variables using col("variable_name"). For example: col("score").
- Supported comparison methods: .eq(), .ne(), .gt(), .lt(), .lte(), .gte(), .is_in().
- Supported logical operators: & (AND), | (OR), ~ (NOT). Do NOT use "and", "or", or "not" keywords.
- Example: "col(\\"score\\").eq(5) | col(\\"score\\").eq(10)"
- Example: "~col(\"more_questions\")"
"""


class OperationPlan(BaseModel):
    """The plan containing the list of graph operations."""

    operations: list[GraphOperation] = Field(
        default_factory=list, description="The flat list of graph operations to apply."
    )


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
            "description": "Submits the flat list of graph operations.",
            "parameters": prune_json_schema(OperationPlan.model_json_schema()),
        },
    }

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=req_messages,
            tools=[tool_schema],
            tool_choice={"type": "function", "function": {"name": "submit_plan"}},
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
