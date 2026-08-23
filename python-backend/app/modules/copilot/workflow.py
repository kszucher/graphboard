from __future__ import annotations

import logging
import os
from typing import Any

from google import genai
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.exceptions import ValidationError
from app.modules.copilot.planner import generate_plan
from app.modules.copilot.state import CopilotState
from app.modules.copilot.translator import translate_plan_node
from app.modules.graphs.engine import DirectLangGraphCompiler
from app.modules.graphs.operations import (
    GraphUpdateInput,
    apply_graph_update,
    assert_flow_is_complete,
)
from app.modules.graphs.schemas import GraphFlowData

logger = logging.getLogger(__name__)

MAX_RETRIES = 1


async def planner_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the Planner LLM to generate the checklist of operations."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValidationError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)

    messages = list(state.get("messages") or [])
    if not messages:
        messages = [
            {
                "role": "user",
                "content": f"## Current Graph State:\n{state['serialized_state']}\n\n## User Request:\n{state['user_prompt']}",
            },
        ]

    plan = await generate_plan(
        client,
        state["trace_id"],
        state.get("graph_id", ""),
        messages,
        initial_flow=state.get("initial_flow_data"),
    )

    return {
        "tool_calls": plan,
        "operations": None,
        "messages": messages,
    }


def _format_error_feedback(err_msg: str) -> str:
    """Classifies validation error into structured diagnostic hints for LLM self-correction."""
    tag = "[VALIDATION_ERROR]"
    lower_err = err_msg.lower()
    if "does not exist" in lower_err and ("target" in lower_err or "edge" in lower_err):
        tag = "[DANGLING_TARGET]"
    elif "never referenced by any node" in lower_err or "orphan variable" in lower_err:
        tag = "[DEAD_VARIABLE]"
    elif "incompatible default value" in lower_err or "incompatible type" in lower_err:
        tag = "[TYPE_MISMATCH]"
    elif "orphan node" in lower_err:
        tag = "[ORPHAN_NODE]"
    elif "variable" in lower_err and (
        "not defined" in lower_err
        or "missing" in lower_err
        or "invalid variable" in lower_err
        or "undefined" in lower_err
    ):
        tag = "[UNDEFINED_VARIABLE]"
    elif "unreachable" in lower_err:
        tag = "[UNREACHABLE_NODE]"
    elif (
        "unconnected" in lower_err
        or "not connected" in lower_err
        or "outgoing target" in lower_err
        or "outgoing edge" in lower_err
    ):
        tag = "[UNCONNECTED_SLOT]"
    elif "syntax" in lower_err or "compilation" in lower_err:
        tag = "[COMPILATION_ERROR]"
    elif (
        "must specify" in lower_err
        or "required" in lower_err
        or "empty prompt" in lower_err
        or "at least one output" in lower_err
        or "must have at least" in lower_err
    ):
        tag = "[MISSING_CONFIGURATION]"

    return (
        f"{tag} Your previous operations failed validation:\n"
        f"{err_msg}\n\n"
        "Please analyze the diagnostic above and generate a complete, corrected sequence of tool calls."
    )


def validation_node(state: CopilotState) -> dict[str, Any]:
    """Validates generated operations by dry-running them against the backend mutations engine, topological integrity, and compiler."""
    current_retries = state.get("retry_count") or 0

    if state.get("validation_error"):
        err_msg = str(state["validation_error"])
        logger.warning(
            "Agent plan translation failed (attempt %d/%d): %s",
            current_retries + 1,
            MAX_RETRIES,
            err_msg,
        )

        messages = list(state.get("messages") or [])
        messages.append(
            {
                "role": "user",
                "content": _format_error_feedback(err_msg),
            }
        )

        return {
            "validation_error": err_msg,
            "applied": False,
            "retry_count": current_retries + 1,
            "messages": messages,
        }

    if not state.get("operations"):
        return {"validation_error": "No operations generated.", "applied": False}

    try:
        flow_data = GraphFlowData.model_validate(state["initial_flow_data"])
        state_ops = state.get("operations") or {}
        update = GraphUpdateInput.model_validate(state_ops)

        # 1. Dry-run patch application
        apply_graph_update(flow_data, update)

        # 2. Topological graph completeness & integrity verification
        assert_flow_is_complete(flow_data)

        # 3. Direct LangGraph Compiler AST compilation verification
        DirectLangGraphCompiler(flow_data).compile()

        return {"validation_error": None, "applied": True}
    except Exception as e:
        err_msg = str(e)
        logger.warning(
            "Agent operation dry-run failed (attempt %d/%d): %s",
            current_retries + 1,
            MAX_RETRIES,
            err_msg,
        )

        messages = list(state.get("messages") or [])
        messages.append(
            {
                "role": "user",
                "content": _format_error_feedback(err_msg),
            }
        )

        return {
            "validation_error": err_msg,
            "applied": False,
            "retry_count": current_retries + 1,
            "messages": messages,
        }


def route_after_validation(state: CopilotState) -> str:
    if state.get("applied") or not state.get("validation_error"):
        return END
    current_retries = state.get("retry_count") or 0
    if current_retries <= MAX_RETRIES:
        return "planner_node"
    return END


# --- Build StateGraph with Self-Correction Retry Loop ---

workflow = StateGraph(CopilotState)

workflow.add_node("planner_node", planner_node)
workflow.add_node("translate_plan_node", translate_plan_node)
workflow.add_node("validation_node", validation_node)

workflow.add_edge(START, "planner_node")
workflow.add_edge("planner_node", "translate_plan_node")
workflow.add_edge("translate_plan_node", "validation_node")
workflow.add_conditional_edges("validation_node", route_after_validation)

# In-memory saver to persist threads across runs
memory_saver = MemorySaver()
copilot_graph = workflow.compile(checkpointer=memory_saver)
