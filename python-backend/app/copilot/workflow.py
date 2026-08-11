from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal, TypedDict, cast

from groq import AsyncGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.copilot.executor_prompts import EXECUTOR_SYSTEM_PROMPT
from app.copilot.logger import log_llm_call
from app.copilot.planner_prompts import PLANNER_SYSTEM_PROMPT
from app.copilot.tools import (
    ALL_FLAT_TOOLS,
    SUBMIT_PLAN_TOOL,
    SubmitPlanArgsSchema,
    translate_tool_calls_to_operations,
)
from app.exceptions import ValidationError
from app.graphs import mutations
from app.graphs.mutations import sort_operations_by_dependency
from app.graphs.schemas import GraphFlowData

logger = logging.getLogger(__name__)


class CopilotState(TypedDict):
    graph_id: str
    user_prompt: str
    serialized_state: str
    initial_flow_data: dict[str, Any]

    plan: list[dict[str, Any]] | None
    plan_approved: bool | None

    operations: list[dict[str, Any]] | None
    validation_error: str | None

    apply_approved: bool | None
    applied: bool | None


async def planner_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the Planner LLM to generate a high-level list of tasks."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValidationError("GROQ_API_KEY environment variable is not set.")

    client = AsyncGroq(api_key=api_key)

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"## Current Graph State:\n{state['serialized_state']}\n\n## User Request:\n{state['user_prompt']}",
        },
    ]

    from groq import RateLimitError
    from groq.types.chat import ChatCompletionNamedToolChoiceParam

    try:
        planner_completion = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,  # type: ignore
            tools=[SUBMIT_PLAN_TOOL],  # type: ignore
            tool_choice=cast(
                ChatCompletionNamedToolChoiceParam, {"type": "function", "function": {"name": "submit_plan"}}
            ),
            max_tokens=1000,
            temperature=0.0,
        )
        log_llm_call(
            node_name="planner_node",
            model="llama-3.3-70b-versatile",
            messages=messages,
            response=planner_completion,
            graph_id=state.get("graph_id"),
        )
    except RateLimitError as e:
        log_llm_call(
            node_name="planner_node",
            model="llama-3.3-70b-versatile",
            messages=messages,
            error=str(e),
            graph_id=state.get("graph_id"),
        )
        logger.warning("Groq rate limit exceeded in Planner")
        raise ValidationError("Groq LLM rate limit exceeded. Please wait a moment before trying again.")
    except Exception as e:
        log_llm_call(
            node_name="planner_node",
            model="llama-3.3-70b-versatile",
            messages=messages,
            error=str(e),
            graph_id=state.get("graph_id"),
        )
        logger.exception("Failed calling Planner Groq LLM")
        raise ValidationError(f"Planner execution failed: {str(e)}")

    planner_choice = planner_completion.choices[0]
    if not planner_choice.message.tool_calls:
        raise ValidationError("Planner failed to submit a plan.")

    planner_tool_call = planner_choice.message.tool_calls[0]
    try:
        planner_args = json.loads(planner_tool_call.function.arguments)
    except Exception as e:
        raise ValidationError(f"Planner returned invalid JSON plan arguments: {str(e)}")

    try:
        plan_schema = SubmitPlanArgsSchema.model_validate(planner_args)
    except Exception as e:
        raise ValidationError(f"Planner returned invalid plan structure: {str(e)}")

    logger.info("Planner graph_analysis: %s", plan_schema.graph_analysis)
    return {"plan": [step.model_dump() for step in plan_schema.steps]}


def wait_for_plan_node(state: CopilotState) -> dict[str, Any]:
    """Automatically approves the plan to continue workflow execution."""
    return {"plan_approved": True}


def get_tools_for_plan(plan: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Exposes base tools and selectively enables upsert tools based on planned actions."""
    # Base tools always allowed
    allowed_tool_names = {
        "upsert_state_var",
        "delete_state_var",
        "connect",
        "disconnect",
        "delete_node",
    }

    if plan:
        for step in plan:
            details = step.get("details") or {}
            node_type = details.get("node_type")
            if node_type == "LOGICAL_ASSIGNER":
                allowed_tool_names.add("upsert_logical_assigner")
            elif node_type == "AGENTIC_ASSIGNER":
                allowed_tool_names.add("upsert_agentic_assigner")
            elif node_type == "LOGICAL_SWITCH":
                allowed_tool_names.add("upsert_logical_switch")
            elif node_type == "AGENTIC_SWITCH":
                allowed_tool_names.add("upsert_agentic_switch")
            elif node_type == "INTERRUPT":
                allowed_tool_names.add("upsert_interrupt")

    return [ALL_FLAT_TOOLS[name] for name in allowed_tool_names if name in ALL_FLAT_TOOLS]


async def executor_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the Executor LLM to build exact mutation operations for the approved plan."""
    if not state.get("plan_approved"):
        return {}

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValidationError("GROQ_API_KEY environment variable is not set.")

    client = AsyncGroq(api_key=api_key)
    steps_str = json.dumps(state.get("plan") or [], indent=2)

    messages = [
        {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"## Current Graph State:\n{state['serialized_state']}\n\n"
                f"## High-Level Plan to Execute:\n{steps_str}\n\n"
                "Please invoke the appropriate tools to implement this plan."
            ),
        },
    ]

    from groq import RateLimitError

    tools = get_tools_for_plan(state.get("plan"))

    try:
        executor_completion = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tools,  # type: ignore
            tool_choice="auto",
            max_tokens=1500,
            temperature=0.0,
        )
        log_llm_call(
            node_name="executor_node",
            model="llama-3.3-70b-versatile",
            messages=messages,
            response=executor_completion,
            graph_id=state.get("graph_id"),
        )
    except RateLimitError as e:
        log_llm_call(
            node_name="executor_node",
            model="llama-3.3-70b-versatile",
            messages=messages,
            error=str(e),
            graph_id=state.get("graph_id"),
        )
        logger.warning("Groq rate limit exceeded in Executor")
        raise ValidationError("Groq LLM rate limit exceeded. Please wait a moment before trying again.")
    except Exception as e:
        log_llm_call(
            node_name="executor_node",
            model="llama-3.3-70b-versatile",
            messages=messages,
            error=str(e),
            graph_id=state.get("graph_id"),
        )
        logger.exception("Failed calling Executor Groq LLM")
        raise ValidationError(f"Executor execution failed: {str(e)}")

    executor_choice = executor_completion.choices[0]
    tool_calls = executor_choice.message.tool_calls
    if not tool_calls:
        raise ValidationError("Executor failed to invoke any tools.")

    try:
        validated_ops = translate_tool_calls_to_operations(tool_calls)
    except Exception as e:
        raise ValidationError(f"Executor produced invalid operations: {str(e)}")

    return {"operations": [op.model_dump(mode="json") for op in validated_ops]}


def validation_node(state: CopilotState) -> dict[str, Any]:
    """Validates generated operations by dry-running them against the backend mutations engine."""
    if not state.get("plan_approved") or not state.get("operations"):
        return {}

    try:
        from pydantic import TypeAdapter

        from app.graphs.schemas import GraphOperation

        flow_data = GraphFlowData.model_validate(state["initial_flow_data"])
        state_ops = state.get("operations") or []
        ops: list[GraphOperation] = [TypeAdapter(GraphOperation).validate_python(op) for op in state_ops]
        sorted_ops = sort_operations_by_dependency(ops)

        # Dry-run patch application
        mutations.apply_patch(flow_data, sorted_ops)
        return {"validation_error": None}
    except Exception as e:
        logger.warning("Executor operation dry-run failed: %s", str(e))
        return {"validation_error": str(e)}


def wait_for_apply_node(state: CopilotState) -> dict[str, Any]:
    """Automatically approves applying the patch if validation succeeded."""
    has_error = bool(state.get("validation_error"))
    return {"apply_approved": not has_error}


def apply_node(state: CopilotState) -> dict[str, Any]:
    """Marks the state as applied so the service can persist changes."""
    if not state.get("apply_approved") or state.get("validation_error"):
        return {"applied": False}
    return {"applied": True}


# --- Graph Routing Logic ---


def route_after_plan(state: CopilotState) -> Literal["executor_node", "__end__"]:
    if state.get("plan_approved"):
        return "executor_node"
    return "__end__"


def route_after_apply(state: CopilotState) -> Literal["apply_node", "__end__"]:
    if state.get("apply_approved") and not state.get("validation_error"):
        return "apply_node"
    return "__end__"


# --- Build StateGraph ---

workflow = StateGraph(CopilotState)

workflow.add_node("planner_node", planner_node)
workflow.add_node("wait_for_plan_node", wait_for_plan_node)
workflow.add_node("executor_node", executor_node)
workflow.add_node("validation_node", validation_node)
workflow.add_node("wait_for_apply_node", wait_for_apply_node)
workflow.add_node("apply_node", apply_node)

workflow.add_edge(START, "planner_node")
workflow.add_edge("planner_node", "wait_for_plan_node")
workflow.add_conditional_edges("wait_for_plan_node", route_after_plan)
workflow.add_edge("executor_node", "validation_node")
workflow.add_edge("validation_node", "wait_for_apply_node")
workflow.add_conditional_edges("wait_for_apply_node", route_after_apply)
workflow.add_edge("apply_node", END)

# In-memory saver to persist threads across HTTP cycles
memory_saver = MemorySaver()
copilot_graph = workflow.compile(checkpointer=memory_saver)
