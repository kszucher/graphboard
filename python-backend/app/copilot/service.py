from __future__ import annotations

from typing import Any, cast

from langchain_core.runnables import RunnableConfig

from app.context import UnitOfWork
from app.copilot.workflow import copilot_graph
from app.exceptions import ValidationError
from app.graphs.schemas import GraphFlowData
from app.graphs.serializer import serialize_flow_to_code


def format_copilot_response(values: dict[str, Any]) -> dict[str, Any]:
    """Helper to convert raw graph state values into a clean UI status layout."""
    status = "idle"
    if values.get("applied") is True:
        status = "applied"
    elif values.get("apply_approved") is True and not values.get("applied"):
        status = "apply_failed"
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
    """Starts the LangGraph Copilot workflow, runs to completion, and auto-commits on success."""
    from datetime import datetime

    from app.copilot.logger import flow_run_id

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    flow_run_id.set(f"{timestamp}_{graph_id}")

    latest_snapshot = await uow.graph_history.get_latest_snapshot(graph_id)
    if not latest_snapshot:
        raise ValidationError(f"No version found for Graph {graph_id}")

    flow_data = GraphFlowData.model_validate(latest_snapshot.flow_json or {})
    serialized_state = serialize_flow_to_code(flow_data)

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

    # Run the automated pipeline fully
    await copilot_graph.ainvoke(cast(Any, initial_state), config)

    graph_state = await copilot_graph.aget_state(config)
    state_values = graph_state.values

    # If the workflow approved applying and validation passed, commit the mutations immediately
    if state_values.get("applied") and not state_values.get("validation_error"):
        import uuid

        from pydantic import TypeAdapter

        from app.graphs import service as graphs_service
        from app.graphs.schemas import GraphOperation

        ops: list[GraphOperation] = [
            TypeAdapter(GraphOperation).validate_python(op) for op in state_values.get("operations") or []
        ]
        flow_response = await graphs_service.apply_patch(uow, uuid.UUID(str(graph_id)), ops)

        response = format_copilot_response(state_values)
        response["flow_data"] = flow_response
        return response

    return format_copilot_response(state_values)


async def approve_copilot_plan(
    uow: UnitOfWork,
    graph_id: Any,
    approved: bool,
) -> dict[str, Any]:
    """Obsolete. Returns the current graph execution state."""
    config = cast(RunnableConfig, {"configurable": {"thread_id": str(graph_id)}})
    graph_state = await copilot_graph.aget_state(config)
    return format_copilot_response(graph_state.values)


async def apply_copilot_patch(
    uow: UnitOfWork,
    graph_id: Any,
    approved: bool,
) -> dict[str, Any]:
    """Obsolete. Returns the current graph execution state."""
    config = cast(RunnableConfig, {"configurable": {"thread_id": str(graph_id)}})
    graph_state = await copilot_graph.aget_state(config)
    return format_copilot_response(graph_state.values)
