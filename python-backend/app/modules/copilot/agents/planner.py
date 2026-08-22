from typing import Any, cast

PLANNER_SYSTEM_PROMPT = """# GraphBoard Operations Planner

You are the AI Graph Operations Planner. Analyze the user's graph edit request, view the current graph state (state variables and node flow), and call the appropriate operations tools to modify the graph.

## Single-Turn Execution Invariant
- IMPORTANT: You MUST generate ALL necessary tool calls to completely fulfill the user's request in a SINGLE turn.
- State variables must be defined with `upsert_variable` before being referenced in node assignments or switch conditions.

## Core Operations Tools

1. `upsert_variable(key, type, default_value=null, description=null)`
   - Creates or updates a state variable definition.

2. `upsert_node(id, node_type, config, target=null)`
   - Creates or updates a node with its complete configuration.
   - For linear nodes (`LOGICAL_ASSIGNER`, `AGENTIC_ASSIGNER`, `RAG_RETRIEVER`, `INTERRUPT`), specify downstream `target="<node_id_or_end>"`.
   - Node Configurations:
     - `LOGICAL_ASSIGNER`: `config={"assignments": [{"target_var_key": "score", "assignment": {"value": 10}}]}`
     - `AGENTIC_ASSIGNER`: `config={"prompt": "...", "agentic_inputs": ["topic"], "agentic_outputs": [{"key": "out", "type": "string"}]}`
     - `RAG_RETRIEVER`: `config={"query_var": "q", "context_output_var": "docs", "knowledge_base": "kb", "top_k": 3}`
     - `INTERRUPT`: `config={"resume_var": "ans", "payload_vars": ["display_text"]}`
     - `LOGICAL_SWITCH`: `config={"branches": [{"label": "Yes", "condition": {"logic": "ALL", "conditions": [{"var": "score", "op": "gte", "literal_value": 10}]}, "target": "node_a"}, {"label": "Default", "condition": null, "target": "node_b"}]}`
     - `AGENTIC_SWITCH`: `config={"agentic_input": "user_choice", "branches": [{"label": "Audience", "target": "poll_audience"}, {"label": "Phone", "target": "call_phone"}]}`

3. `upsert_switch_branch(node_id, label, target, condition=null)`
   - Surgically adds or updates a single branch on an existing switch without overwriting or reconstructing other branches.
   - For `LOGICAL_SWITCH`, specify `condition` (or `null` for fallback).
   - For `AGENTIC_SWITCH`, `condition` is `null`.

4. `reroute_edge(source, branch=null, new_target=null)`
   - Redirects an existing connection without re-specifying the node config.
   - `reroute_edge(source="start", new_target="first_node")`: Changes graph entrypoint.
   - `reroute_edge(source="assigner_a", new_target="new_node")`: Redirects a linear node.
   - `reroute_edge(source="my_switch", branch="Yes", new_target="new_node")`: Redirects a switch branch. Set `new_target=null` to disconnect.

5. `delete_entity(kind, id, parent_id=null)`
   - `kind="node"`: Deletes a node (`id="node_id"`).
   - `kind="variable"`: Deletes a state variable (`id="var_key"`).
   - `kind="switch_branch"`: Deletes a switch branch (`id="branch_label", parent_id="switch_node_id"`).

6. `rename_entity(kind, old_name, new_name)`
   - `kind="node"` or `kind="variable"`.

## Closed-Schema Expressions
- **Comparisons**: `{"var": "score", "op": "equals", "literal_value": 10}` or `{"var": "parsed", "op": "equals", "compare_var": "correct"}`
- **Supported operators**: `equals`, `not_equals`, `gt`, `gte`, `lt`, `lte`, `in`
- **Assignments**:
  - Literal: `{"value": 10}` or `{"value": true}` or `{"value": "A"}`
  - Variable copy: `{"var": "source_var"}`
  - Numeric delta: `{"op": "increment", "amount": 1}` or `{"op": "decrement", "amount": 1}`
"""


def prune_json_schema(schema: Any) -> Any:
    """Recursively removes title metadata from the JSON schema to save token overhead."""
    if isinstance(schema, dict):
        return {k: prune_json_schema(v) for k, v in schema.items() if k != "title"}
    elif isinstance(schema, list):
        return [prune_json_schema(item) for item in schema]
    return schema


def dereference_schema(schema: dict) -> dict:
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


async def generate_plan(
    client: Any,
    trace_id: str,
    graph_id: str,
    messages: list[dict[str, Any]],
    initial_flow: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Invokes the LLM with granular tools to produce a sequence of operations."""
    import json
    import os

    from google.genai import types

    from app.modules.copilot.agents import planner_schemas
    from app.modules.copilot.logger import log_llm_call

    model_name = os.environ.get("COPILOT_MODEL", "gemini-3.6-flash")
    req_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}] + messages

    # Define closed-schema tools dynamically from planner_schemas
    tools_declarations = [
        types.FunctionDeclaration(
            name="upsert_variable",
            description="Create or update a state variable definition.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertVariable.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="upsert_node",
            description="Create or update a node with its complete type configuration and inline target.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertNode.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="upsert_switch_branch",
            description="Surgically add or update a single branch on an existing switch node without overwriting other branches.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertSwitchBranch.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="reroute_edge",
            description="Reroute an existing outgoing transition from a source node or 'start' to a new target (or null to disconnect).",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.RerouteEdge.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="delete_entity",
            description="Delete a node, state variable, or switch branch.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.DeleteEntity.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="rename_entity",
            description="Rename a node ID or state variable key and update all graph references.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.RenameEntity.model_json_schema())
            ),
        ),
    ]

    tools: list[Any] = [types.Tool(function_declarations=tools_declarations)]

    # Map messages to types.Content structure
    gemini_contents = []
    for msg in messages:
        role = msg["role"]
        gemini_contents.append(
            types.Content(role="user" if role == "user" else "model", parts=[types.Part.from_text(text=msg["content"])])
        )

    config = types.GenerateContentConfig(
        system_instruction=PLANNER_SYSTEM_PROMPT,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.0,
    )

    tools_info = [
        {"name": td.name, "description": td.description, "parameters": td.parameters_json_schema}
        for td in tools_declarations
    ]

    try:
        async with client.aio as aclient:
            response = await aclient.models.generate_content(
                model=model_name,
                contents=gemini_contents,
                config=config,
            )
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model=model_name,
            messages=req_messages,
            response=response,
            graph_id=graph_id,
            tools=tools_info,
            initial_flow=initial_flow,
        )
    except Exception as e:
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model=model_name,
            messages=req_messages,
            error=str(e),
            graph_id=graph_id,
            tools=tools_info,
            initial_flow=initial_flow,
        )
        raise e

    function_calls = getattr(response, "function_calls", None)
    if not function_calls:
        raise Exception("Planner failed to generate any tool calls.")

    # Return serialized tool calls lists
    return [
        {
            "name": fc.name,
            "arguments": json.dumps(fc.args) if isinstance(fc.args, dict) else (fc.args or "{}"),
        }
        for fc in function_calls
    ]
