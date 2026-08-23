from __future__ import annotations

import json
from typing import Any

from google.genai import types

from app.core.config import settings
from app.modules.copilot import planner_schemas
from app.modules.copilot.logger import log_llm_call
from app.modules.copilot.schema_utils import dereference_schema, prune_json_schema

PLANNER_SYSTEM_PROMPT = """# GraphBoard Operations Planner

You are the AI Graph Operations Planner. Analyze the user's graph edit request, view the current graph state (state variables and node flow), and call `apply_graph_plan` with the complete, atomic batch of operations needed to fulfill the request.

## Atomic Single-Turn Generation Invariant
- IMPORTANT: You MUST emit your complete plan in a single `apply_graph_plan` call containing all variables, nodes, and switch branches.
- State variables must be declared in `variables` in the same plan before being referenced in node assignments or switch conditions.
- All linear nodes and switch branches must have explicit downstream targets connected to valid nodes or `end`.

## State Lifecycle & Flow Invariants
- **Complete Variable Lifecycle (Write & Read)**: When introducing new state variables (e.g. milestones, safety nets, flags, or modifiers), always complete both sides of the lifecycle: ensure the variable is not only updated on triggers, but also read and applied where its effect matters (e.g. falling back on loss/exit paths, applying multipliers, or rendering UI).
- **End-to-End Flow Tracing**: When altering mechanics or business logic, trace both the success path and the failure/exit path to ensure state mutations produce observable consequences before termination (`end`).

## Core Operation Schema (`apply_graph_plan`)

1. `variables`: List of state variables to create or update.
   - `{"key": "score", "type": "number", "default_value": 0, "description": "Player score"}`
   - Supported types: `string`, `number`, `boolean`, `array`, `object`

2. `nodes`: List of nodes to create, update, or retarget.
   - **Creating new nodes**: Provide `id`, `node_type`, `config`, and downstream `target="<node_id_or_end>"` (for linear nodes).
   - **Retargeting existing nodes**: Simply provide `{"id": "existing_node", "target": "new_dest"}` without repeating config.
   - **Setting graph entrypoint**: `{"id": "start", "target": "first_step"}`.
   - Node Configurations:
     - `LOGICAL_ASSIGNER`: `config={"assignments": [{"target_var_key": "score", "assignment": {"value": 10}}]}`
     - `AGENTIC_ASSIGNER`: `config={"prompt": "...", "agentic_inputs": ["topic"], "agentic_outputs": [{"key": "out", "type": "string"}]}`
     - `RAG_RETRIEVER`: `config={"query_var": "q", "context_output_var": "docs", "knowledge_base": "kb", "top_k": 3}`
     - `INTERRUPT`: `config={"resume_var": "ans", "payload_vars": ["question_text", "options"]}`
     - `LOGICAL_SWITCH`: `config={"branches": [{"label": "Yes", "condition": {"logic": "ALL", "conditions": [{"var": "score", "op": "gte", "literal_value": 10}]}, "target": "node_a"}, {"label": "Default", "condition": null, "target": "node_b"}]}`
     - `AGENTIC_SWITCH`: `config={"agentic_input": "user_choice", "branches": [{"label": "Audience", "target": "poll_audience"}, {"label": "Phone", "target": "call_phone"}]}`

3. `switch_branches`: List of surgical switch branches to add or update on existing switches without reconstructing other branches.
   - `{"node_id": "choose_lifeline", "label": "FiftyFifty", "target": "fifty_fifty", "condition": null}`

4. `deletions`: List of entities to delete.
   - `{"kind": "node"|"variable"|"switch_branch", "id": "entity_id", "parent_id": null|"switch_node_id"}`

5. `renames`: List of entities to rename.
   - `{"kind": "node"|"variable", "old_name": "old_key", "new_name": "new_key"}`

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
"""


async def generate_plan(
    client: Any,
    trace_id: str,
    graph_id: str,
    messages: list[dict[str, Any]],
    initial_flow: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Invokes the LLM with the single atomic apply_graph_plan tool."""
    model_name = settings.copilot_model
    req_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}] + messages

    tools_declarations = [
        types.FunctionDeclaration(
            name="apply_graph_plan",
            description="Apply an atomic batch of graph operations (variables, nodes, switch branches, renames, deletions) to modify the graph.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.ApplyGraphPlan.model_json_schema())
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

    thinking_config = None
    if settings.copilot_thinking_budget > 0:
        thinking_config = types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=settings.copilot_thinking_budget,
        )

    config = types.GenerateContentConfig(
        system_instruction=PLANNER_SYSTEM_PROMPT,
        tools=tools,
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
                allowed_function_names=["apply_graph_plan"],
            )
        ),
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
