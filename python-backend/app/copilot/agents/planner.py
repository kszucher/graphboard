from typing import Any

from pydantic import BaseModel, Field

PLANNER_SYSTEM_PROMPT = """
# GraphBoard Multi-Agent Planner

Your job is to analyze the user's graph edit request and break it down into a granular checklist for three specialized sub-agents.
You DO NOT execute the changes yourself. You only create the plan.

## The Sub-Agents

1. **State Agent**: Manages variables and AST expressions.
   - Declares/deletes variables.
   - Defines logical/mathematical expressions.

2. **Topology Agent**: Manages boxes and lines.
   - Creates/deletes empty node shells.
   - Adds/removes empty branches on switch nodes.
   - Connects/disconnects nodes using case labels.
   - *Cannot write prompts or bind expressions.*

3. **Config Agent**: Injects logic into the boxes.
   - Binds formulas to logical assigners.
   - Binds conditions to switch branches.
   - Configures LLM prompts and I/O for agentic assigners.
   - Configures RAG search variables.

## Instructions
Analyze the current graph state and the user request.
Write out human-readable tasks for each agent in the order they must be executed (State -> Topology -> Config).
Leave the list empty if an agent has no work to do.
"""

class AgentPlan(BaseModel):
    """The master checklist for the multi-agent copilot."""
    state_tasks: list[str] = Field(description="Tasks for the State Agent (variables & logic formulas)")
    topology_tasks: list[str] = Field(description="Tasks for the Topology Agent (creating nodes & wiring connections)")
    config_tasks: list[str] = Field(description="Tasks for the Config Agent (binding prompts, RAG, and logical assignments to nodes)")


async def generate_plan(client: Any, trace_id: str, graph_id: str, messages: list[dict[str, Any]]) -> AgentPlan:
    """Invokes the LLM to generate the checklist."""
    import json
    from app.copilot.logger import log_llm_call

    req_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}] + messages
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            response_format={"type": "json_schema", "json_schema": {"name": "AgentPlan", "schema": AgentPlan.model_json_schema()}},
            temperature=0.0
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

    return AgentPlan.model_validate(json.loads(response.choices[0].message.content))
