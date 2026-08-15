from typing import Any

PLANNER_SYSTEM_PROMPT = """
# GraphBoard Graph Operations Planner

Analyze the user's graph edit request, view the current graph state (variables and nodes), and call the appropriate operations tools to apply the requested changes.

## Graph Database Architecture:
The graph has state variables and nodes.
- Edges define the control flow transitions (routing) from node to node.
- Decoupled Edge Routing: Nodes themselves do NOT contain routing targets. Routing is defined explicitly by calling edge tools:
  - **Linear Nodes** (logical_assigner, agentic_assigner, rag_retriever, interrupt) only have a single transition. Connect them using:
    `upsert_linear_edge(source, target)`
  - **Switch Nodes** (logical_switch, agentic_switch) have multiple conditional branch paths. Connect them using:
    `upsert_switch_edge(source, branch_label, target)` (where branch_label is strictly required, e.g. "Yes", "No", "correct", "wrong").
- Every node in the flow MUST be reachable; do NOT create orphan nodes (nodes that are not targeted by any other node or the entrypoint). If you create a new node, you MUST call `upsert_*_edge` to point to it from a preceding node.
- Variable Declarations: You MUST call `upsert_variable` to define any new state variable (with type and default value) before referencing it in assignments, increment/decrement instructions, or switch comparison expressions.
- Unique Nodes: Do NOT create duplicate nodes or define multiple IDs to perform the same task. Ensure every created node is uniquely named and fully connected.
- Logical Milestones: If the request depends on tracking occurrence thresholds (e.g. "every 5th event"), ensure you define and read from a dedicated counter variable (e.g. `request_count`) rather than comparing against other state variables (e.g. payload data).
- Threshold Logic: When securing a baseline/safety floor upon reaching a milestone, verify if the tracking variable is greater than or equal to (`gte`) the milestone threshold (do not check if it is less than/`lt`).


## Available Node Types:
1. `LOGICAL_ASSIGNER`: Sets state variables based on expressions, e.g. `assignments: [{"target_var_key": "x", "expression": ...}]`.
2. `LOGICAL_SWITCH`: Conditional routing using branches, e.g. `branches: {"LabelA": ComparisonExpression, "LabelB": null}` (where LabelB is fallback). Does not contain targets inline.
3. `AGENTIC_ASSIGNER`: LLM instruction prompt to populate variables.
4. `AGENTIC_SWITCH`: LLM decision routing using branches, e.g. `branches: ["LabelA", "LabelB"]`.
5. `RAG_RETRIEVER`: Knowledge base context retrieval.
6. `INTERRUPT`: Pauses execution for human input.


## Expression Formats:
- Switch branches use Prisma-style nested query objects for comparisons:
  - Standard comparison: `{"error_count": {"gt": 5}}` or `{"is_active": {"equals": false}}`
  - Reference another variable: `{"received_token": {"equals": {"var": "valid_token"}}}`
  - Operators: `equals`, `not`, `in`, `lt`, `lte`, `gt`, `gte`
  - Logic composition: `{"AND": [{"error_count": {"gt": 5}}, {"is_active": {"equals": false}}]}`
- Assigners use atomic update structures:
  - Set: `{"set": 10}` or `{"set": {"var": "user_input"}}` or scalar `10` / `"topic"`
  - Numeric: `{"increment": 1}`, `{"decrement": 5}`, `{"multiply": 2}`, `{"divide": 3}`

## Examples of Flow Modification:

### Example 1: Inserting a node between linear nodes
Request: "Add a log_payload node after start_session but before process_data"
Current Flow:
  start_session() -> process_data
  process_data -> end_session
Tool Calls:
1. upsert_agentic_assigner(id="log_payload", agentic_inputs=["session_id"], agentic_outputs=[], prompt="Write session metadata log.")
2. upsert_linear_edge(source="start_session", target="log_payload")
3. upsert_linear_edge(source="log_payload", target="process_data")

### Example 2: Inserting a node inside a switch branch
Request: "Increment error counter inside the error branch of validate_router before return_to_start"
Current Flow:
  validate_router: LOGICAL_SWITCH(success=cond -> process_data, error=!cond -> return_to_start)
Tool Calls:
1. upsert_logical_assigner(id="error_incrementer", assignments=[{"target_var_key": "error_count", "expression": {"increment": 1}}])
2. upsert_switch_edge(source="validate_router", branch_label="error", target="error_incrementer")
3. upsert_linear_edge(source="error_incrementer", target="return_to_start")
"""


def prune_json_schema(schema: Any) -> Any:
    """Recursively removes title metadata from the JSON schema to save token overhead."""
    if isinstance(schema, dict):
        return {k: prune_json_schema(v) for k, v in schema.items() if k != "title"}
    elif isinstance(schema, list):
        return [prune_json_schema(item) for item in schema]
    return schema


async def generate_plan(
    client: Any,
    trace_id: str,
    graph_id: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Invokes the LLM with granular tools to produce a sequence of operations."""
    import os

    from app.modules.copilot.agents import planner_schemas
    from app.modules.copilot.logger import log_llm_call

    model_name = os.environ.get("COPILOT_MODEL", "llama-3.3-70b-versatile")
    req_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}] + messages

    # Define the 16 granular tools dynamically from planner_schemas
    tools = [
        {
            "type": "function",
            "function": {
                "name": "upsert_variable",
                "description": "Create or update a state variable definition.",
                "parameters": prune_json_schema(planner_schemas.UpsertVariable.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_variable",
                "description": "Delete a state variable definition.",
                "parameters": prune_json_schema(planner_schemas.DeleteVariable.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rename_variable",
                "description": "Rename an existing state variable and update all node references.",
                "parameters": prune_json_schema(planner_schemas.RenameVariable.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upsert_logical_assigner",
                "description": "Create or update a logical assignment node. Routing MUST be set via upsert_linear_edge.",
                "parameters": prune_json_schema(planner_schemas.UpsertLogicalAssigner.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upsert_agentic_assigner",
                "description": "Create or update an agentic assignment prompt node. Routing MUST be set via upsert_linear_edge.",
                "parameters": prune_json_schema(planner_schemas.UpsertAgenticAssigner.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upsert_logical_switch",
                "description": "Create or update a conditional switch node. Defines branches with conditional logic. Routing MUST be set via upsert_switch_edge.",
                "parameters": prune_json_schema(planner_schemas.UpsertLogicalSwitch.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upsert_agentic_switch",
                "description": "Create or update an agentic routing switch node. Defines case labels. Routing MUST be set via upsert_switch_edge.",
                "parameters": prune_json_schema(planner_schemas.UpsertAgenticSwitch.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upsert_rag_retriever",
                "description": "Create or update a RAG context retrieval node. Routing MUST be set via upsert_linear_edge.",
                "parameters": prune_json_schema(planner_schemas.UpsertRagRetriever.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upsert_interrupt",
                "description": "Create or update a human input interrupt checkpoint node. Routing MUST be set via upsert_linear_edge.",
                "parameters": prune_json_schema(planner_schemas.UpsertInterrupt.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_node",
                "description": "Delete a node from the graph.",
                "parameters": prune_json_schema(planner_schemas.DeleteNode.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rename_node",
                "description": "Rename a node ID and update all transition targets.",
                "parameters": prune_json_schema(planner_schemas.RenameNode.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_start_target",
                "description": "Set the starting entrypoint node ID of the graph flow.",
                "parameters": prune_json_schema(planner_schemas.SetStartTarget.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upsert_linear_edge",
                "description": "Create or update a connection edge from a linear node to a target node.",
                "parameters": prune_json_schema(planner_schemas.UpsertLinearEdge.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upsert_switch_edge",
                "description": "Create or update a connection edge from a switch node's branch to a target node.",
                "parameters": prune_json_schema(planner_schemas.UpsertSwitchEdge.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_linear_edge",
                "description": "Disconnect the edge exiting from a linear node.",
                "parameters": prune_json_schema(planner_schemas.DeleteLinearEdge.model_json_schema()),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_switch_edge",
                "description": "Disconnect the edge exiting from a switch node's branch.",
                "parameters": prune_json_schema(planner_schemas.DeleteSwitchEdge.model_json_schema()),
            },
        },
    ]

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=req_messages,
            tools=tools,
            temperature=0.0,
        )
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model=model_name,
            messages=req_messages,
            response=response,
            graph_id=graph_id,
            tools=tools,
        )
    except Exception as e:
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model=model_name,
            messages=req_messages,
            error=str(e),
            graph_id=graph_id,
            tools=tools,
        )
        raise e

    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise Exception("Planner failed to generate any tool calls.")

    # Return serialized tool calls lists
    return [
        {
            "name": tc.function.name,
            "arguments": tc.function.arguments,
        }
        for tc in tool_calls
    ]
