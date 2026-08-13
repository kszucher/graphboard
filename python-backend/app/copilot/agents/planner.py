from typing import Any

from pydantic import BaseModel, Field

PLANNER_SYSTEM_PROMPT = """
# GraphBoard Multi-Agent Planner

Your job is to analyze the user's graph edit request and break it down into a granular checklist for three specialized sub-agents.
You DO NOT execute the changes yourself. You only create the plan.

## Node Taxonomy

- **START**: The entry point of the graph.
- **LOGICAL_ASSIGNER**: Deterministic variable state updates (assigning values or expressions to variables).
- **AGENTIC_ASSIGNER**: LLM state updates (`prompt`, `agentic_inputs`, `agentic_outputs`).
- **LOGICAL_SWITCH**: Conditional branching via evaluation expressions.
- **AGENTIC_SWITCH**: LLM-driven routing across labeled output branches.
- **INTERRUPT**: Halts execution for user input (`payload` variable → `resume` variable).
- **RAG_RETRIEVER**: Performs semantic search using a query variable and stores results.
- **END**: The exit point of the graph.

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

**CRITICAL**: You MUST use exact, identical string identifiers for variables and `node_id`s across all your task descriptions. For example, if you tell the Topology Agent to create node 'my_node', you must refer to it as exactly 'my_node' when telling the Config Agent to configure it. Do not use fuzzy names.
"""


class AgentPlan(BaseModel):
    """The master checklist for the multi-agent copilot."""

    state_tasks: list[str] = Field(description="Tasks for the State Agent (variables & logic formulas)")
    topology_tasks: list[str] = Field(description="Tasks for the Topology Agent (creating nodes & wiring connections)")
    config_tasks: list[str] = Field(
        description="Tasks for the Config Agent (binding prompts, RAG, and logical assignments to nodes)"
    )


async def generate_plan(client: Any, trace_id: str, graph_id: str, messages: list[dict[str, Any]]) -> AgentPlan:
    """Invokes the LLM to generate the checklist."""
    import json
    from app.copilot.logger import log_llm_call

    req_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}] + messages

    tool_schema = {
        "type": "function",
        "function": {
            "name": "submit_agent_plan",
            "description": "Submits the master checklist for the multi-agent copilot.",
            "parameters": AgentPlan.model_json_schema(),
        },
    }

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            tools=[tool_schema],
            tool_choice={"type": "function", "function": {"name": "submit_agent_plan"}},
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

    return AgentPlan.model_validate(json.loads(tool_calls[0].function.arguments))
