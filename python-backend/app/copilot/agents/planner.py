from typing import Any

from pydantic import BaseModel, Field

from app.graphs.operations import GraphOperation

PLANNER_SYSTEM_PROMPT = """
# GraphBoard Operation Planner

Analyze the user's graph edit request and produce a precise, flat list of graph operations to apply by calling the `submit_plan` tool.
"""


class OperationPlan(BaseModel):
    """The plan containing the list of graph operations."""

    operations: list[GraphOperation] = Field(
        default_factory=list, description="The flat list of graph operations to apply."
    )


async def generate_plan(client: Any, trace_id: str, graph_id: str, messages: list[dict[str, Any]]) -> OperationPlan:
    """Invokes the LLM to produce a structured operation plan."""
    import json

    from app.copilot.logger import log_llm_call

    req_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}] + messages

    tool_schema = {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": "Submits the flat list of graph operations.",
            "parameters": OperationPlan.model_json_schema(),
        },
    }

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            tools=[tool_schema],
            tool_choice={"type": "function", "function": {"name": "submit_plan"}},
            temperature=0.0,
        )
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            response=response,
            graph_id=graph_id,
        )
    except Exception as e:
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            error=str(e),
            graph_id=graph_id,
        )
        raise e

    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise Exception("Planner failed to generate a plan tool call.")

    try:
        args = json.loads(tool_calls[0].function.arguments)
        return OperationPlan.model_validate(args)
    except Exception as e:
        raise Exception(f"Failed to validate planner tool call arguments: {str(e)}")
