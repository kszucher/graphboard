from __future__ import annotations

import json
import os
from typing import Any

from google.genai import types

from app.modules.copilot.agents import planner_schemas
from app.modules.copilot.agents.schema_utils import dereference_schema, prune_json_schema
from app.modules.copilot.logger import log_llm_call

PLANNER_SYSTEM_PROMPT = """# GraphBoard Operations Planner

You are the AI Graph Operations Planner. Analyze the user's graph edit request, view the current graph state (state variables and node flow), and call the appropriate operations tools to modify the graph.

## Single-Turn Batch Generation Invariant
- IMPORTANT: You MUST generate the COMPLETE batch of ALL tool calls to fulfill the entire request in this single response (e.g. `upsert_variable` followed immediately by all `upsert_node` and `upsert_switch_branch` calls).
- Do NOT stop after creating variables or a single node. Do NOT wait for tool execution results or responses—emit all operations together in one single batch.
- State variables must be defined with `upsert_variable` in the same batch before being referenced in node assignments or switch conditions.

## State Lifecycle & Flow Invariants
- **Complete Variable Lifecycle (Write & Read)**: When introducing new state variables (e.g. milestones, safety nets, flags, or modifiers), always complete both sides of the lifecycle: ensure the variable is not only updated on triggers, but also read and applied where its effect matters (e.g. falling back on loss/exit paths, applying multipliers, or rendering UI).
- **End-to-End Flow Tracing**: When altering mechanics or business logic, trace both the success path and the failure/exit path to ensure state mutations produce observable consequences before termination (`end`).

## Core Operations Tools

1. `upsert_variable(key, type, default_value=null, description=null)`
   - Creates or updates a state variable definition.

2. `upsert_node(id, node_type=null, config=null, target=null)`
   - Creates or updates a node and its outgoing target.
   - **Creating new nodes**: Provide `id`, `node_type`, `config`, and downstream `target="<node_id_or_end>"` (for linear nodes).
   - **Retargeting existing nodes**: Simply call `upsert_node(id="existing_node", target="new_dest")` without repeating config.
   - **Setting graph entrypoint**: `upsert_node(id="start", target="first_step")`.
   - Node Configurations:
     - `LOGICAL_ASSIGNER`: `config={"assignments": [{"target_var_key": "score", "assignment": {"value": 10}}]}`
     - `AGENTIC_ASSIGNER`: `config={"prompt": "...", "agentic_inputs": ["topic"], "agentic_outputs": [{"key": "out", "type": "string"}]}`
     - `RAG_RETRIEVER`: `config={"query_var": "q", "context_output_var": "docs", "knowledge_base": "kb", "top_k": 3}`
     - `INTERRUPT`: `config={"resume_var": "ans", "payload_vars": ["question_text", "options"]}`
     - `LOGICAL_SWITCH`: `config={"branches": [{"label": "Yes", "condition": {"logic": "ALL", "conditions": [{"var": "score", "op": "gte", "literal_value": 10}]}, "target": "node_a"}, {"label": "Default", "condition": null, "target": "node_b"}]}`
     - `AGENTIC_SWITCH`: `config={"agentic_input": "user_choice", "branches": [{"label": "Audience", "target": "poll_audience"}, {"label": "Phone", "target": "call_phone"}]}`

3. `upsert_switch_branch(node_id, label, target, condition=null)`
   - Surgically adds or updates a single branch on an existing switch without overwriting or reconstructing other branches.
   - For `LOGICAL_SWITCH`, specify `condition` (or `null` for fallback).
   - For `AGENTIC_SWITCH`, `condition` is `null`.

4. `delete_entity(kind, id, parent_id=null)`
   - `kind="node"`: Deletes a node (`id="node_id"`).
   - `kind="variable"`: Deletes a state variable (`id="var_key"`).
   - `kind="switch_branch"`: Deletes a switch branch (`id="branch_label", parent_id="switch_node_id"`).

5. `rename_entity(kind, old_name, new_name)`
   - `kind="node"` or `kind="variable"`.

## Closed-Schema Expressions
- **Comparisons (LOGICAL_SWITCH conditions only)**:
  - `{"var": "score", "op": "equals", "literal_value": 10}` or `{"var": "parsed", "op": "equals", "compare_var": "correct"}`
  - Supported operators: `equals`, `not_equals`, `gt`, `gte`, `lt`, `lte`, `in`
- **Data Transformations (LOGICAL_ASSIGNER assignments only)**:
  - **Literals & Copies**: `{"value": 10}`, `{"value": "A"}`, `{"value": ["A", "B"]}`, `{"var": "source_var"}`
  - **Arithmetic**: `{"op": "add"|"subtract"|"multiply"|"divide"|"modulo", "left": 10, "right": {"var": "bonus"}}`
  - **Target Delta**: `{"op": "increment"|"decrement", "amount": 1}`
  - **Math**: `{"op": "round", "val": {"var": "score"}}`, `{"op": "min"|"max", "args": [...]}`
  - **Random Numbers**: `{"op": "random_int", "min": 1, "max": 6}`, `{"op": "random_float", "min": 0.0, "max": 1.0}`
  - **Strings**:
    - `{"op": "format", "template": "Question: {q}\\nOptions: {opts}", "vars": ["q", "opts"]}`
    - `{"op": "join", "list": {"var": "options"}, "sep": "\\n"}`
    - `{"op": "split", "str": {"var": "csv_text"}, "sep": ","}`
  - **Collections & Sampling**:
    - `{"op": "sample", "list": {"var": "options"}, "count": 2}`: Select 2 random elements.
    - `{"op": "choice", "list": {"var": "options"}}`: Select 1 random element.
    - `{"op": "remove", "list": {"var": "options"}, "item": {"var": "correct_answer"}}`: Remove item(s) from list.
    - `{"op": "append", "list": {"var": "options"}, "item": "New Choice"}`
    - `{"op": "length", "list": {"var": "options"}}`
    - `{"op": "slice", "list": {"var": "options"}, "start": 0, "end": 2}`

## Final Execution Checklist
- After completing your reasoning, emit the ENTIRE sequence of tool calls needed (variables, nodes, retargeting, switch branches) in this single turn. Never stop after emitting a single tool call.
"""


async def generate_plan(
    client: Any,
    trace_id: str,
    graph_id: str,
    messages: list[dict[str, Any]],
    initial_flow: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Invokes the LLM with granular tools to produce a sequence of operations."""
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
            description="Create or update a node (or set its target / entrypoint).",
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

    thinking_budget_str = os.environ.get("COPILOT_THINKING_BUDGET", "1024")
    thinking_config = None
    if thinking_budget_str and thinking_budget_str != "0":
        try:
            budget = int(thinking_budget_str)
            thinking_config = types.ThinkingConfig(
                include_thoughts=True,
                thinking_budget=budget,
            )
        except ValueError:
            thinking_config = types.ThinkingConfig(include_thoughts=True)

    config = types.GenerateContentConfig(
        system_instruction=PLANNER_SYSTEM_PROMPT,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.0,
        thinking_config=thinking_config,
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
