from __future__ import annotations

import logging
import os
from typing import Any, Literal

from google import genai
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.exceptions import ValidationError
from app.modules.copilot.agents.planner import generate_plan
from app.modules.copilot.logger import log_validation_error
from app.modules.copilot.models import CopilotState
from app.modules.copilot.translator import translate_plan_node
from app.modules.graphs.operations import GraphUpdateInput, apply_graph_update
from app.modules.graphs.schemas import GraphFlowData

logger = logging.getLogger(__name__)


async def planner_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the Planner LLM to generate the checklist of operations."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValidationError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)

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
    checklist = {"tool_calls": plan}

    return {
        "agent_checklist": checklist,
        "operations": None,
        "plan": [],
    }


def aggregation_node(state: CopilotState) -> dict[str, Any]:
    """Aggregates the transaction update into a list of human-readable plan steps for the UI."""
    state_ops = state.get("operations") or {}
    try:
        update = GraphUpdateInput.model_validate(state_ops)
    except Exception as e:
        raise ValidationError(f"Agents generated invalid updates: {str(e)}")

    plan_steps = []
    if update.start_target:
        plan_steps.append(
            {
                "action": "set_start_target",
                "description": f"Set starting node to '{update.start_target}'",
                "details": {},
            }
        )
    if update.rename_variables:
        for ru in update.rename_variables:
            plan_steps.append(
                {
                    "action": "rename_variable",
                    "description": f"Rename variable '{ru.old_key}' to '{ru.new_key}'",
                    "details": {},
                }
            )
    if update.rename_nodes:
        for rn in update.rename_nodes:
            plan_steps.append(
                {"action": "rename_node", "description": f"Rename node '{rn.old_key}' to '{rn.new_key}'", "details": {}}
            )
    if update.variables:
        if update.variables.delete:
            for d in update.variables.delete:
                plan_steps.append({"action": "delete_variable", "description": f"Delete variable '{d}'", "details": {}})
        if update.variables.upsert:
            for u in update.variables.upsert:
                plan_steps.append(
                    {
                        "action": "upsert_variable",
                        "description": f"Upsert variable '{u.key}' (type: {u.type})",
                        "details": u.model_dump(),
                    }
                )
    if update.nodes:
        if update.nodes.delete:
            for dn in update.nodes.delete:
                plan_steps.append({"action": "delete_node", "description": f"Delete node '{dn}'", "details": {}})
        if update.nodes.upsert:
            for un in update.nodes.upsert:
                plan_steps.append(
                    {
                        "action": "upsert_node",
                        "description": f"Upsert node '{un.id}' (type: {un.node_type})",
                        "details": un.model_dump(),
                    }
                )

    return {"plan": plan_steps}


def wait_for_plan_node(state: CopilotState) -> dict[str, Any]:
    """Automatically approves the plan to continue workflow execution."""
    return {"plan_approved": True}


def validation_node(state: CopilotState) -> dict[str, Any]:
    """Validates generated operations by dry-running them against the backend mutations engine."""
    if not state.get("plan_approved") or not state.get("operations"):
        return {}

    try:
        flow_data = GraphFlowData.model_validate(state["initial_flow_data"])
        state_ops = state.get("operations") or {}
        update = GraphUpdateInput.model_validate(state_ops)

        # Dry-run patch application
        apply_graph_update(flow_data, update)
        return {"validation_error": None}
    except Exception as e:
        logger.warning("Agent operation dry-run failed: %s", str(e))
        log_validation_error(state["trace_id"], state.get("graph_id"), str(e))
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


def route_after_plan(state: CopilotState) -> Literal["validation_node", "__end__"]:
    if state.get("plan_approved"):
        return "validation_node"
    return "__end__"


def route_after_apply(state: CopilotState) -> Literal["apply_node", "__end__"]:
    if state.get("apply_approved") and not state.get("validation_error"):
        return "apply_node"
    return "__end__"


# --- Build StateGraph ---

workflow = StateGraph(CopilotState)

workflow.add_node("planner_node", planner_node)
workflow.add_node("translate_plan_node", translate_plan_node)
workflow.add_node("aggregation_node", aggregation_node)
workflow.add_node("wait_for_plan_node", wait_for_plan_node)
workflow.add_node("validation_node", validation_node)
workflow.add_node("wait_for_apply_node", wait_for_apply_node)
workflow.add_node("apply_node", apply_node)

workflow.add_edge(START, "planner_node")
workflow.add_edge("planner_node", "translate_plan_node")
workflow.add_edge("translate_plan_node", "aggregation_node")
workflow.add_edge("aggregation_node", "wait_for_plan_node")
workflow.add_conditional_edges("wait_for_plan_node", route_after_plan)
workflow.add_edge("validation_node", "wait_for_apply_node")
workflow.add_conditional_edges("wait_for_apply_node", route_after_apply)
workflow.add_edge("apply_node", END)

# In-memory saver to persist threads across HTTP cycles
memory_saver = MemorySaver()
copilot_graph = workflow.compile(checkpointer=memory_saver)
