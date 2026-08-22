from __future__ import annotations

from datetime import UTC
from typing import Any, cast

from langchain_core.runnables import RunnableConfig

from app.core.context import UnitOfWork
from app.core.exceptions import ValidationError
from app.modules.copilot.workflow import copilot_graph
from app.modules.graphs.schemas import GraphFlowData
from app.modules.graphs.serializer import serialize_flow_to_code


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
    from datetime import datetime

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
        "tool_calls": None,
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
        import uuid

        from app.modules.graphs import service as graphs_service
        from app.modules.graphs.operations import GraphUpdateInput

        update = GraphUpdateInput.model_validate(state_values.get("operations") or {})
        await graphs_service.apply_graph_update(uow, uuid.UUID(str(graph_id)), update)

    return format_copilot_response(state_values)
