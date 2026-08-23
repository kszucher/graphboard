import uuid
from datetime import UTC, datetime
from typing import Any, cast

from langchain_core.runnables import RunnableConfig

from app.core.context import UnitOfWork
from app.core.exceptions import ValidationError
from app.modules.copilot.workflow import copilot_graph
from app.modules.graphs import service as graphs_service
from app.modules.graphs.engine import serialize_flow_to_code
from app.modules.graphs.operations import GraphUpdateInput
from app.modules.graphs.schemas import GraphFlowData


def format_copilot_response(values: dict[str, Any]) -> dict[str, Any]:
    """Helper to convert raw graph state values into a minimal status response."""
    return {
        "graph_id": values.get("graph_id"),
        "applied": values.get("applied") or False,
        "validation_error": values.get("validation_error"),
    }


async def initiate_copilot_workflow(
    uow: UnitOfWork,
    graph_id: Any,
    prompt: str,
) -> dict[str, Any]:
    """Starts the LangGraph Copilot workflow, runs to completion, and auto-commits on success."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    trace_id = f"{timestamp}_{graph_id}"

    latest_snapshot = await uow.graph_history.get_latest_snapshot(graph_id)
    if not latest_snapshot:
        raise ValidationError(f"No version found for Graph {graph_id}")

    flow_data = GraphFlowData.model_validate(latest_snapshot.flow_json or {})
    serialized_state = serialize_flow_to_code(flow_data)

    config = cast(RunnableConfig, {"configurable": {"thread_id": str(graph_id)}})

    # Reset/initialize graph state
    initial_state = {
        "trace_id": trace_id,
        "graph_id": str(graph_id),
        "user_prompt": prompt,
        "serialized_state": serialized_state,
        "initial_flow_data": flow_data.model_dump(mode="json"),
        "plan": None,
        "operations": None,
        "validation_error": None,
        "applied": None,
        "retry_count": 0,
        "messages": None,
    }

    # Run the automated pipeline fully
    await copilot_graph.ainvoke(cast(Any, initial_state), config)

    graph_state = await copilot_graph.aget_state(config)
    state_values = graph_state.values

    # If the workflow approved applying and validation passed, commit the mutations immediately
    if state_values.get("applied") and not state_values.get("validation_error"):
        update = state_values.get("operations")
        if isinstance(update, GraphUpdateInput):
            await graphs_service.apply_graph_update(uow, uuid.UUID(str(graph_id)), update)
        elif isinstance(update, dict):
            await graphs_service.apply_graph_update(
                uow, uuid.UUID(str(graph_id)), GraphUpdateInput.model_validate(update)
            )

    return format_copilot_response(state_values)
