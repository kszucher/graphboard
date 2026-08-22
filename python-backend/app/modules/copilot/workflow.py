from __future__ import annotations

import logging
import os
from typing import Any

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

    return {
        "tool_calls": plan,
        "operations": None,
    }


def validation_node(state: CopilotState) -> dict[str, Any]:
    """Validates generated operations by dry-running them against the backend mutations engine."""
    if not state.get("operations"):
        return {"validation_error": "No operations generated.", "applied": False}

    try:
        flow_data = GraphFlowData.model_validate(state["initial_flow_data"])
        state_ops = state.get("operations") or {}
        update = GraphUpdateInput.model_validate(state_ops)

        # Dry-run patch application
        apply_graph_update(flow_data, update)
        return {"validation_error": None, "applied": True}
    except Exception as e:
        logger.warning("Agent operation dry-run failed: %s", str(e))
        log_validation_error(state["trace_id"], state.get("graph_id"), str(e))
        return {"validation_error": str(e), "applied": False}


# --- Build StateGraph ---

workflow = StateGraph(CopilotState)

workflow.add_node("planner_node", planner_node)
workflow.add_node("translate_plan_node", translate_plan_node)
workflow.add_node("validation_node", validation_node)

workflow.add_edge(START, "planner_node")
workflow.add_edge("planner_node", "translate_plan_node")
workflow.add_edge("translate_plan_node", "validation_node")
workflow.add_edge("validation_node", END)

# In-memory saver to persist threads across runs
memory_saver = MemorySaver()
copilot_graph = workflow.compile(checkpointer=memory_saver)
