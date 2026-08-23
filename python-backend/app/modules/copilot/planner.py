from __future__ import annotations

import json
from typing import Any

from google.genai import types

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.modules.copilot import planner_schemas
from app.modules.copilot.logger import log_llm_call
from app.modules.copilot.schema_utils import dereference_schema, prune_json_schema

PLANNER_SYSTEM_PROMPT = """# GraphBoard Operations Planner

You are the AI Graph Operations Planner. Analyze the user's graph edit request, inspect the current graph state (state variables and node flow), and call `apply_graph_plan` with the complete, atomic batch of operations needed to fulfill the request.

## Atomic Single-Turn Generation Invariant
- IMPORTANT: You MUST emit your complete plan in a single `apply_graph_plan` call containing all variables, nodes, and switch branches.
- State variables must be declared in `variables` in the same plan before being referenced in node assignments or switch conditions.
- All linear nodes and switch branches must have explicit downstream targets connected to valid nodes or `end`.

## State Lifecycle & Flow Invariants
- **Complete Variable Lifecycle (Write & Read)**: When introducing new state variables (e.g. milestones, safety nets, flags, or modifiers), always complete both sides of the lifecycle: ensure the variable is not only updated on triggers, but also read and applied where its effect matters (e.g. falling back on loss/exit paths, applying multipliers, or rendering UI).
- **End-to-End Flow Tracing**: When altering mechanics or business logic, trace both the success path and the failure/exit path to ensure state mutations produce observable consequences before termination (`end`).
"""


async def generate_plan(
    client: Any,
    trace_id: str,
    graph_id: str,
    messages: list[dict[str, Any]],
    initial_flow: dict[str, Any] | None = None,
    model: str | None = None,
) -> planner_schemas.ApplyGraphPlan:
    """Invokes the LLM with the single atomic apply_graph_plan tool and returns the validated ApplyGraphPlan."""
    model_name = model or settings.copilot_model
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
    budget = settings.copilot_thinking_budget
    if "3.5" in model_name or "lite" in model_name:
        budget = settings.copilot_lite_thinking_budget

    if budget > 0:
        thinking_config = types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=budget,
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
        raise ValidationError("Planner failed to generate any tool calls.")

    plan_call = next((fc for fc in function_calls if fc.name == "apply_graph_plan"), None)
    if not plan_call:
        raise ValidationError(f"Expected tool call 'apply_graph_plan', found: {[fc.name for fc in function_calls]}")

    args = plan_call.args
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception as e:
            raise ValidationError(f"Failed to parse arguments JSON for 'apply_graph_plan': {str(e)}")
    elif not isinstance(args, dict):
        args = {}

    return planner_schemas.ApplyGraphPlan.model_validate(args)
