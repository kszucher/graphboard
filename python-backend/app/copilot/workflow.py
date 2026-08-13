from __future__ import annotations

import logging
import os
from typing import Any, Literal

from groq import AsyncGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.copilot.agents.config_agent import execute_config_tasks
from app.copilot.agents.planner import generate_plan
from app.copilot.agents.state_agent import execute_state_tasks
from app.copilot.agents.topology_agent import execute_topology_tasks
from app.copilot.logger import log_validation_error
from app.copilot.models import CopilotState
from app.copilot.tools import translate_tool_calls_to_operations
from app.exceptions import ValidationError
from app.graphs import operations
from app.graphs.schemas import GraphFlowData

logger = logging.getLogger(__name__)


async def planner_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the Planner LLM to generate the checklist of agent tasks."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValidationError("GROQ_API_KEY environment variable is not set.")

    client = AsyncGroq(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": f"## Current Graph State:\n{state['serialized_state']}\n\n## User Request:\n{state['user_prompt']}",
        },
    ]

    plan = await generate_plan(client, state["trace_id"], state.get("graph_id", ""), messages)
    checklist = plan.model_dump()

    return {
        "agent_checklist": checklist,
        "operations": [],
        "plan": [],  # We will populate this in the aggregation node for the UI
    }


async def state_agent_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the State Agent to execute variable and expression tasks."""
    checklist = state.get("agent_checklist") or {}
    tasks = checklist.get("state_tasks", [])
    if not tasks:
        return {}

    api_key = os.environ.get("GROQ_API_KEY")
    client = AsyncGroq(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": f"## Current Graph State:\n{state['serialized_state']}\n\n## User Request:\n{state['user_prompt']}",
        },
    ]

    tool_calls = await execute_state_tasks(client, state["trace_id"], state.get("graph_id", ""), messages, tasks)
    ops = translate_tool_calls_to_operations(tool_calls)

    current_ops = state.get("operations") or []
    return {"operations": current_ops + [op.model_dump(mode="json") for op in ops]}


async def topology_agent_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the Topology Agent to execute node creation and wiring tasks."""
    checklist = state.get("agent_checklist") or {}
    tasks = checklist.get("topology_tasks", [])
    if not tasks:
        return {}

    api_key = os.environ.get("GROQ_API_KEY")
    client = AsyncGroq(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": f"## Current Graph State:\n{state['serialized_state']}\n\n## User Request:\n{state['user_prompt']}",
        },
    ]

    tool_calls = await execute_topology_tasks(client, state["trace_id"], state.get("graph_id", ""), messages, tasks)
    ops = translate_tool_calls_to_operations(tool_calls)

    current_ops = state.get("operations") or []
    return {"operations": current_ops + [op.model_dump(mode="json") for op in ops]}


async def config_agent_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the Config Agent to execute logic and prompt injection tasks."""
    checklist = state.get("agent_checklist") or {}
    tasks = checklist.get("config_tasks", [])
    if not tasks:
        return {}

    api_key = os.environ.get("GROQ_API_KEY")
    client = AsyncGroq(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": f"## Current Graph State:\n{state['serialized_state']}\n\n## User Request:\n{state['user_prompt']}",
        },
    ]

    tool_calls = await execute_config_tasks(client, state["trace_id"], state.get("graph_id", ""), messages, tasks)
    ops = translate_tool_calls_to_operations(tool_calls)

    current_ops = state.get("operations") or []
    return {"operations": current_ops + [op.model_dump(mode="json") for op in ops]}


def aggregation_node(state: CopilotState) -> dict[str, Any]:
    """Aggregates all operations into a human-readable plan for the UI."""
    from pydantic import TypeAdapter
    from app.graphs.operations import GraphOperation

    state_ops = state.get("operations") or []
    try:
        validated_ops: list[GraphOperation] = [TypeAdapter(GraphOperation).validate_python(op) for op in state_ops]
    except Exception as e:
        raise ValidationError(f"Agents generated invalid mutations: {str(e)}")

    plan_steps = []
    for op in validated_ops:
        plan_steps.append(
            {
                "action": op.op,
                "description": f"Apply {op.op} operation",
                "details": op.model_dump(exclude={"op"}),
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
        from pydantic import TypeAdapter
        from app.graphs.operations import GraphOperation

        flow_data = GraphFlowData.model_validate(state["initial_flow_data"])
        state_ops = state.get("operations") or []
        ops: list[GraphOperation] = [TypeAdapter(GraphOperation).validate_python(op) for op in state_ops]
        sorted_ops = operations.sort_operations_by_dependency(ops)

        # Dry-run patch application
        operations.apply_patch(flow_data, sorted_ops)
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
workflow.add_node("state_agent_node", state_agent_node)
workflow.add_node("topology_agent_node", topology_agent_node)
workflow.add_node("config_agent_node", config_agent_node)
workflow.add_node("aggregation_node", aggregation_node)
workflow.add_node("wait_for_plan_node", wait_for_plan_node)
workflow.add_node("validation_node", validation_node)
workflow.add_node("wait_for_apply_node", wait_for_apply_node)
workflow.add_node("apply_node", apply_node)

workflow.add_edge(START, "planner_node")
workflow.add_edge("planner_node", "state_agent_node")
workflow.add_edge("state_agent_node", "topology_agent_node")
workflow.add_edge("topology_agent_node", "config_agent_node")
workflow.add_edge("config_agent_node", "aggregation_node")
workflow.add_edge("aggregation_node", "wait_for_plan_node")
workflow.add_conditional_edges("wait_for_plan_node", route_after_plan)
workflow.add_edge("validation_node", "wait_for_apply_node")
workflow.add_conditional_edges("wait_for_apply_node", route_after_apply)
workflow.add_edge("apply_node", END)

# In-memory saver to persist threads across HTTP cycles
memory_saver = MemorySaver()
copilot_graph = workflow.compile(checkpointer=memory_saver)
