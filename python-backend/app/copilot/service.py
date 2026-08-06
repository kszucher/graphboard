from __future__ import annotations

import json
import logging
import os
from typing import Any
from groq import AsyncGroq

from app.context import UnitOfWork
from app.exceptions import ValidationError
from app.graphs.schemas import GraphFlowData
from app.graphs import mutations
from app.copilot.tools import (
    PATCH_GRAPH_TOOL,
    serialize_graph_to_tool_calls,
    translate_tool_call_to_operations,
    sort_operations_by_dependency,
)

logger = logging.getLogger(__name__)


async def generate_and_apply_copilot_patch(
    uow: UnitOfWork,
    graph_id: Any,
    prompt: str,
) -> dict:
    """Invokes Groq LLM with patch_graph tool choice, parses, sorts operations, and applies mutation."""
    # 1. Fetch latest graph snapshot
    latest_snapshot = await uow.graph_history.get_latest_snapshot(graph_id)
    if not latest_snapshot:
        raise ValidationError(f"No version found for Graph {graph_id}")

    flow_data = GraphFlowData.model_validate(latest_snapshot.flow_json or {})

    # 2. Serialize current state to Format C
    serialized_state = serialize_graph_to_tool_calls(flow_data)

    # 3. Read System Prompt
    prompt_path = os.path.join(os.path.dirname(__file__), "copilot_system_prompt.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # 4. Initialize Groq Client
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValidationError("GROQ_API_KEY environment variable is not set.")

    client = AsyncGroq(api_key=api_key)

    # 5. Call LLM with required tool choice
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"## Current Graph State:\n{serialized_state}\n\n## User Request:\n{prompt}",
        },
    ]

    try:
        from typing import cast
        from groq.types.chat import ChatCompletionNamedToolChoiceParam

        completion = await client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=messages,  # type: ignore
            tools=[PATCH_GRAPH_TOOL],  # type: ignore
            tool_choice=cast(
                ChatCompletionNamedToolChoiceParam, {"type": "function", "function": {"name": "patch_graph"}}
            ),
            temperature=0.0,
        )
    except Exception as e:
        logger.exception("Failed calling Groq LLM")
        raise ValidationError(f"Copilot model execution failed: {str(e)}")

    choice = completion.choices[0]
    if not choice.message.tool_calls:
        raise ValidationError("Model failed to invoke patch_graph tool.")

    # 6. Parse and translate operations
    tool_call = choice.message.tool_calls[0]
    try:
        args = json.loads(tool_call.function.arguments)
    except Exception as e:
        raise ValidationError(f"Model returned invalid JSON arguments: {str(e)}")

    ops = translate_tool_call_to_operations(args)

    # 7. Sort operations
    sorted_ops = sort_operations_by_dependency(ops)

    # 8. Apply patch
    mutated = mutations.apply_patch(flow_data, sorted_ops)

    # 9. Save Snapshot
    next_seq = latest_snapshot.sequence_number + 1
    updated_flow_dict = mutated.model_dump(mode="json")
    await uow.graph_history.save_snapshot(graph_id, updated_flow_dict, next_seq)
    await uow.session.flush()

    # Import prepare response helper from graph service to return consistent response layout
    from app.graphs.service import _prepare_response_flow

    return await _prepare_response_flow(uow, graph_id, mutated, next_seq)
