from typing import Any, Literal

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

## The Sub-Agents and their Operations

1. **State Agent**: Manages variables and AST expressions.
   Allowed operations:
   - `declare_variable`: Declare a new state variable.
   - `delete_variable`: Remove an existing state variable.
   - `define_expression`: Define a mathematical or logical evaluation formula.

2. **Topology Agent**: Manages boxes and lines.
   Allowed operations:
   - `create_node`: Create an empty node shell of a specific type.
   - `delete_node`: Delete a node and its connections.
   - `add_switch_branch`: Add a new routing option to a switch node.
   - `remove_switch_branch`: Remove a routing option from a switch node.
   - `connect`: Draw a connection edge between a source node/branch and target node.
   - `disconnect`: Remove a connection edge.

3. **Config Agent**: Injects logic into the boxes.
   Allowed operations:
   - `bind_logical_assignment`: Bind a formula to a logical assigner.
   - `bind_branch_condition`: Bind a boolean expression to a logical switch branch.
   - `configure_agentic_prompt`: Configure LLM prompt and I/O variables.
   - `configure_agentic_switch`: Configure input routing variable for an agentic switch.
   - `configure_rag_search`: Configure query and target context variables for RAG.
   - `configure_interrupt`: Configure payload and resume variables for an interrupt.

## Instructions
1. Analyze the current graph state and the user request.
2. Outline tasks for the State Agent, Topology Agent, and Config Agent in that order.
3. For each task, you must match it to the correct operation (`op`) the sub-agent will run.
4. Ensure all identifiers (variables, node IDs, branches) are exact and match across all tasks.
"""

StateOpType = Literal["declare_variable", "delete_variable", "define_expression"]
TopologyOpType = Literal["create_node", "delete_node", "add_switch_branch", "remove_switch_branch", "connect", "disconnect"]
ConfigOpType = Literal[
    "bind_logical_assignment",
    "bind_branch_condition",
    "configure_agentic_prompt",
    "configure_agentic_switch",
    "configure_rag_search",
    "configure_interrupt",
]


class StateAgentTask(BaseModel):
    op: StateOpType = Field(description="The exact operation name this task requires.")
    description: str = Field(description="The semantic details and values needed to execute the operation.")
    node_id: str = Field(description="Target node_id, use '' if not applicable.")


class TopologyAgentTask(BaseModel):
    op: TopologyOpType = Field(description="The exact operation name this task requires.")
    description: str = Field(description="The semantic details and values needed to execute the operation.")
    node_id: str = Field(description="Target node_id, use '' if not applicable.")


class ConfigAgentTask(BaseModel):
    op: ConfigOpType = Field(description="The exact operation name this task requires.")
    description: str = Field(description="The semantic details and values needed to execute the operation.")
    node_id: str = Field(description="Target node_id, use '' if not applicable.")


class AgentPlan(BaseModel):
    """The master checklist for the multi-agent copilot."""

    state_tasks: list[StateAgentTask] = Field(description="Tasks for the State Agent (variables & logic formulas)")
    topology_tasks: list[TopologyAgentTask] = Field(
        description="Tasks for the Topology Agent (creating nodes & wiring connections)"
    )
    config_tasks: list[ConfigAgentTask] = Field(
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

    state_tasks = []
    topology_tasks = []
    config_tasks = []

    for call in tool_calls:
        try:
            args = json.loads(call.function.arguments)
            if "state_tasks" in args and isinstance(args["state_tasks"], list):
                state_tasks.extend(args["state_tasks"])
            if "topology_tasks" in args and isinstance(args["topology_tasks"], list):
                topology_tasks.extend(args["topology_tasks"])
            if "config_tasks" in args and isinstance(args["config_tasks"], list):
                config_tasks.extend(args["config_tasks"])
        except Exception:
            continue

    return AgentPlan(
        state_tasks=state_tasks,
        topology_tasks=topology_tasks,
        config_tasks=config_tasks,
    )
