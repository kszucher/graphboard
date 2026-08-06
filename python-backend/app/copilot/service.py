from __future__ import annotations

import logging
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.context import UnitOfWork
from app.copilot.tools import (
    serialize_graph_to_tool_calls,
    sort_operations_by_dependency,
    translate_tool_call_to_operations,
)
from app.copilot.workflow import copilot_graph, CopilotState
from app.exceptions import ValidationError
from app.graphs import mutations
from app.graphs.schemas import GraphFlowData

logger = logging.getLogger(__name__)


def format_copilot_response(values: dict[str, Any]) -> dict[str, Any]:
    """Helper to convert raw graph state values into a clean UI status layout."""
    status = "idle"
    if values.get("applied") is True:
        status = "applied"
    elif values.get("apply_approved") is False:
        status = "apply_rejected"
    elif values.get("apply_approved") is None and values.get("operations") is not None:
        status = "pending_apply_approval"
    elif values.get("plan_approved") is False:
        status = "plan_rejected"
    elif values.get("plan_approved") is None and values.get("plan") is not None:
        status = "pending_plan_approval"

    return {
        "graph_id": values.get("graph_id"),
        "status": status,
        "plan": values.get("plan"),
        "operations": values.get("operations"),
        "validation_error": values.get("validation_error"),
        "applied": values.get("applied") or False,
        "flow_data": None,
    }


async def initiate_copilot_workflow(
    uow: UnitOfWork,
    graph_id: Any,
    prompt: str,
) -> dict[str, Any]:
    """Starts the LangGraph Copilot workflow and runs until the plan review interrupt."""
    latest_snapshot = await uow.graph_history.get_latest_snapshot(graph_id)
    if not latest_snapshot:
        raise ValidationError(f"No version found for Graph {graph_id}")

    flow_data = GraphFlowData.model_validate(latest_snapshot.flow_json or {})
    serialized_state = serialize_graph_to_tool_calls(flow_data)

    config = cast(RunnableConfig, {"configurable": {"thread_id": str(graph_id)}})

    # Reset/initialize graph state
    initial_state = {
        "graph_id": str(graph_id),
        "user_prompt": prompt,
        "serialized_state": serialized_state,
        "initial_flow_data": flow_data.model_dump(mode="json"),
        "plan": None,
        "plan_approved": None,
        "operations": None,
        "validation_error": None,
        "apply_approved": None,
        "applied": None,
    }

    # Run up to the first wait interrupt
    await copilot_graph.ainvoke(cast(Any, initial_state), config)

    graph_state = await copilot_graph.aget_state(config)
    return format_copilot_response(graph_state.values)


async def approve_copilot_plan(
    uow: UnitOfWork,
    graph_id: Any,
    approved: bool,
) -> dict[str, Any]:
    """Resumes graph from plan review interrupt, running executor + validator up to apply interrupt."""
    config = cast(RunnableConfig, {"configurable": {"thread_id": str(graph_id)}})

    await copilot_graph.ainvoke(Command(resume={"approved": approved}), config)

    graph_state = await copilot_graph.aget_state(config)
    return format_copilot_response(graph_state.values)


async def apply_copilot_patch(
    uow: UnitOfWork,
    graph_id: Any,
    approved: bool,
) -> dict[str, Any]:
    """Resumes graph from apply review interrupt. If approved, writes mutations transaction to DB."""
    config = cast(RunnableConfig, {"configurable": {"thread_id": str(graph_id)}})

    await copilot_graph.ainvoke(Command(resume={"approved": approved}), config)

    graph_state = await copilot_graph.aget_state(config)
    state_values = graph_state.values

    # If the user approved applying and validation passed, commit the mutations
    if approved and state_values.get("applied") and not state_values.get("validation_error"):
        latest_snapshot = await uow.graph_history.get_latest_snapshot(graph_id)
        if not latest_snapshot:
            raise ValidationError(f"No version found for Graph {graph_id}")

        flow_data = GraphFlowData.model_validate(latest_snapshot.flow_json or {})

        ops = translate_tool_call_to_operations({"operations": state_values.get("operations") or []})
        sorted_ops = sort_operations_by_dependency(ops)

        mutated = mutations.apply_patch(flow_data, sorted_ops)

        next_seq = latest_snapshot.sequence_number + 1
        updated_flow_dict = mutated.model_dump(mode="json")
        await uow.graph_history.save_snapshot(graph_id, updated_flow_dict, next_seq)
        await uow.session.flush()

        from app.graphs.service import _prepare_response_flow

        flow_response = await _prepare_response_flow(uow, graph_id, mutated, next_seq)

        response = format_copilot_response(state_values)
        response["flow_data"] = flow_response
        return response

    return format_copilot_response(state_values)
