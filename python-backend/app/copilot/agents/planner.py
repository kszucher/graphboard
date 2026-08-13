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

**CRITICAL**: Every new node created in the Topology tasks MUST have a corresponding configuration task in the Config tasks (e.g., binding LLM prompts, input/output variables, or branching conditions). Do not leave new nodes unconfigured.

**CRITICAL**: You MUST use exact, identical string identifiers for variables and `node_id`s across all your task descriptions. 
For example, if you tell the Topology Agent to create node 'my_node', you must refer to it as exactly 'my_node' when telling the Config Agent to configure it.
DO NOT use fuzzy names or natural language references for IDs.

**CRITICAL RULES FOR ASSIGNERS & STATE**:
- **State Tasks (Expressions)**: When planning to define an expression, you MUST specify the exact unique expression identifier (e.g., `expr_<node_id>_<variable_name>`) and the exact logic or formula (e.g. `expr_check_correct_is_correct: parsed_answer == correct_answer`) inside the description so the State Agent knows what formula to define.
- **Agentic vs Logical Assigners**:
  - `AGENTIC_ASSIGNER` nodes (like LLM prompts) use `configure_agentic_prompt` to map inputs, outputs, and prompts. **NEVER** map expressions or logical assignments (`bind_logical_assignment`) to them.
  - `LOGICAL_ASSIGNER` nodes use `bind_logical_assignment` to assign expression formulas to variables.

**OUTPUT FORMAT CRITICAL INSTRUCTION**:
You must return an array of objects for each task list. DO NOT return lists of strings.
Each object must have a `description` string and a `node_id` string. If a task does not involve a specific node, set `node_id` to `""`.

"""


class AgentTask(BaseModel):
    description: str = Field(description="The natural language instruction for the sub-agent")
    node_id: str = Field(description="The exact node_id this task targets. Use an empty string '' if not applicable.")


class AgentPlan(BaseModel):
    """The master checklist for the multi-agent copilot."""

    state_tasks: list[AgentTask] = Field(description="Tasks for the State Agent (variables & logic formulas)")
    topology_tasks: list[AgentTask] = Field(
        description="Tasks for the Topology Agent (creating nodes & wiring connections)"
    )
    config_tasks: list[AgentTask] = Field(
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
