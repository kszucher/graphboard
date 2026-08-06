from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal, TypedDict

import anyio
from groq import AsyncGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.copilot.tools import (
    PATCH_GRAPH_TOOL,
    SUBMIT_PLAN_TOOL,
    sort_operations_by_dependency,
    translate_tool_call_to_operations,
)
from app.exceptions import ValidationError
from app.graphs import mutations
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
    planner_prompt_path = os.path.join(os.path.dirname(__file__), "planner_system_prompt.md")
    planner_system_prompt = await anyio.Path(planner_prompt_path).read_text(encoding="utf-8")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValidationError("GROQ_API_KEY environment variable is not set.")

    client = AsyncGroq(api_key=api_key)

    messages = [
        {"role": "system", "content": planner_system_prompt},
        {
            "role": "user",
            "content": f"## Current Graph State:\n{state['serialized_state']}\n\n## User Request:\n{state['user_prompt']}",
        },
    ]

    try:
        from typing import cast

        from groq.types.chat import ChatCompletionNamedToolChoiceParam

        planner_completion = await client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=messages,  # type: ignore
            tools=[SUBMIT_PLAN_TOOL],  # type: ignore
            tool_choice=cast(
                ChatCompletionNamedToolChoiceParam, {"type": "function", "function": {"name": "submit_plan"}}
            ),
            temperature=0.0,
        )
    except Exception as e:
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

    plan = planner_args.get("steps", [])
    return {"plan": plan}


def wait_for_plan_node(state: CopilotState) -> dict[str, Any]:
    """Pauses graph execution so the user can review and approve/reject the planner's checklist."""
    decision = interrupt(
        {
            "status": "pending_plan_approval",
            "plan": state.get("plan"),
        }
    )
    # The decision payload is passed during resume (e.g. Command(resume={"approved": True/False}))
    approved = decision.get("approved", False) if isinstance(decision, dict) else False
    return {"plan_approved": approved}


async def executor_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the Executor LLM to build exact mutation operations for the approved plan."""
    if not state.get("plan_approved"):
        return {}

    executor_prompt_path = os.path.join(os.path.dirname(__file__), "executor_system_prompt.md")
    executor_system_prompt = await anyio.Path(executor_prompt_path).read_text(encoding="utf-8")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValidationError("GROQ_API_KEY environment variable is not set.")

    client = AsyncGroq(api_key=api_key)
    steps_str = json.dumps(state.get("plan") or [], indent=2)

    messages = [
        {"role": "system", "content": executor_system_prompt},
        {
            "role": "user",
            "content": (
                f"## Current Graph State:\n{state['serialized_state']}\n\n"
                f"## High-Level Plan to Execute:\n{steps_str}\n\n"
                "Please generate the exact `patch_graph` tool call to implement this plan."
            ),
        },
    ]

    try:
        from typing import cast

        from groq.types.chat import ChatCompletionNamedToolChoiceParam

        executor_completion = await client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=messages,  # type: ignore
            tools=[PATCH_GRAPH_TOOL],  # type: ignore
            tool_choice=cast(
                ChatCompletionNamedToolChoiceParam, {"type": "function", "function": {"name": "patch_graph"}}
            ),
            temperature=0.0,
        )
    except Exception as e:
        logger.exception("Failed calling Executor Groq LLM")
        raise ValidationError(f"Executor execution failed: {str(e)}")

    executor_choice = executor_completion.choices[0]
    if not executor_choice.message.tool_calls:
        raise ValidationError("Executor failed to invoke patch_graph tool.")

    executor_tool_call = executor_choice.message.tool_calls[0]
    try:
        executor_args = json.loads(executor_tool_call.function.arguments)
    except Exception as e:
        raise ValidationError(f"Executor returned invalid JSON patch arguments: {str(e)}")

    ops = executor_args.get("operations", [])
    return {"operations": ops}


def validation_node(state: CopilotState) -> dict[str, Any]:
    """Validates generated operations by dry-running them against the backend mutations engine."""
    if not state.get("plan_approved") or not state.get("operations"):
        return {}

    try:
        flow_data = GraphFlowData.model_validate(state["initial_flow_data"])
        ops = translate_tool_call_to_operations({"operations": state["operations"]})
        sorted_ops = sort_operations_by_dependency(ops)

        # Dry-run patch application
        mutations.apply_patch(flow_data, sorted_ops)
        return {"validation_error": None}
    except Exception as e:
        logger.exception("Executor operation dry-run validation failed")
        return {"validation_error": str(e)}


def wait_for_apply_node(state: CopilotState) -> dict[str, Any]:
    """Pauses graph execution so the user can review operation validation and approve application."""
    decision = interrupt(
        {
            "status": "pending_apply_approval",
            "operations": state.get("operations"),
            "validation_error": state.get("validation_error"),
        }
    )
    approved = decision.get("approved", False) if isinstance(decision, dict) else False
    return {"apply_approved": approved}


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
