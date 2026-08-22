from typing import Any, cast

PLANNER_SYSTEM_PROMPT = """# GraphBoard Operations Planner

You are the AI Graph Operations Planner. Analyze the user's graph edit request, view the current graph state (state variables and node flow), and call the appropriate operations tools to modify the graph.

## Single-Turn Execution Invariant
- IMPORTANT: You MUST generate ALL necessary tool calls to completely fulfill the user's request in a SINGLE turn.
- When creating a node: declare any new variables with `upsert_variable`, create the node with `upsert_<type>`, and connect predecessor/successor transitions with `connect(...)` in the SAME turn.

## Graph Database & Routing Model
- **Variables**: State variables must be defined with `upsert_variable` before being referenced in node assignments or switch conditions. Use `rename_variable` to rename a variable without losing references.
- **Node Definitions**: Nodes define computation or routing logic but do NOT contain downstream routing targets.
- **Routing Transitions**:
  - `connect(source="start", target="<first_node>")`: Sets the graph entrypoint.
  - `connect(source="<linear_node>", target="<target_node>")`: Connects linear nodes (logical_assigner, agentic_assigner, rag_retriever, interrupt).
  - `connect(source="<switch_node>", branch="<branch_label>", target="<target_node>")`: Connects switch branches (logical_switch, agentic_switch).
  - `disconnect(source="<node_id>", branch="<branch_label_or_null>")`: Disconnects an existing outgoing edge.
- **Topological Invariant**: Every node in the flow must be reachable from `start` or a predecessor node. Do NOT leave orphan nodes.

## Available Node Types
1. `LOGICAL_ASSIGNER`: Deterministic state variable assignments.
   - Example: `assignments=[{"target_var_key": "score", "expression": 0}]`
2. `LOGICAL_SWITCH`: Conditional branching based on expressions.
   - Example: `branches={"High": {"score": {"gt": 10}}, "Default": null}` (use `null` for fallback).
3. `AGENTIC_ASSIGNER`: LLM-driven structured state updates.
   - Example: `prompt="Analyze sentiment...", agentic_inputs=["user_comment"], agentic_outputs=[{"key": "sentiment", "type": "str"}]`
4. `AGENTIC_SWITCH`: LLM-driven classification routing.
   - Example: `agentic_input="user_choice", branches=["OptionA", "OptionB"]`
5. `RAG_RETRIEVER`: Knowledge base context retrieval.
   - Example: `query_var="user_query", context_output_var="docs", knowledge_base="kb", top_k=3`
6. `INTERRUPT`: Pauses execution for human input.
   - Example: `payload_vars=["question"], resume_var="user_reply"`

## Expression Formats
- **Switch Comparison Expressions** (Prisma-style nested query objects):
  - Standard comparison: `{"error_count": {"gt": 5}}` or `{"is_active": {"equals": false}}`
  - Reference another variable: `{"received_token": {"equals": {"var": "valid_token"}}}`
  - Supported operators: `equals`, `not`, `in`, `lt`, `lte`, `gt`, `gte`
  - Logic composition: `{"AND": [{"score": {"gt": 10}}, {"retries": {"lt": 3}}]}`
  - Note: Use plain keys directly, e.g. `{"score": {"gt": 10}}` (do NOT wrap keys in escaped quotes).
- **Assigner Expressions**:
  - Direct value: `10` or `"value"` or `{"var": "other_var"}`
  - Numeric delta: `{"increment": 1}`, `{"decrement": 1}`, `{"multiply": 2}`, `{"divide": 3}`

## Examples of Flow Modification

### Example 1: Inserting a node between linear nodes
Request: "Add a log_payload node after start_session but before process_data"
Current Flow:
  start() -> start_session
  start_session -> process_data
  process_data -> end()
Tool Calls:
1. upsert_agentic_assigner(id="log_payload", prompt="Write session metadata log.", agentic_inputs=["session_id"], agentic_outputs=[])
2. connect(source="start_session", target="log_payload")
3. connect(source="log_payload", target="process_data")

### Example 2: Inserting a node inside a switch branch
Request: "Increment error counter inside the error branch of validate_router before return_to_start"
Current Flow:
  validate_router: LOGICAL_SWITCH(success=cond -> process_data, error=!cond -> return_to_start)
Tool Calls:
1. upsert_logical_assigner(id="error_incrementer", assignments=[{"target_var_key": "error_count", "expression": {"increment": 1}}])
2. connect(source="validate_router", branch="error", target="error_incrementer")
3. connect(source="error_incrementer", target="return_to_start")
"""


def prune_json_schema(schema: Any) -> Any:
    """Recursively removes title metadata from the JSON schema to save token overhead."""
    if isinstance(schema, dict):
        return {k: prune_json_schema(v) for k, v in schema.items() if k != "title"}
    elif isinstance(schema, list):
        return [prune_json_schema(item) for item in schema]
    return schema


def dereference_schema(schema: dict) -> dict:
    """Recursively resolves $ref keys in a JSON schema using definitions from $defs."""
    if not isinstance(schema, dict):
        return schema

    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]
                parts = ref_path.split("/")
                def_name = parts[-1]
                if def_name in defs:
                    return resolve(defs[def_name])
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        elif isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return cast(dict[str, Any], resolve(schema))


async def generate_plan(
    client: Any,
    trace_id: str,
    graph_id: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Invokes the LLM with granular tools to produce a sequence of operations."""
    import json
    import os

    from google.genai import types

    from app.modules.copilot.agents import planner_schemas
    from app.modules.copilot.logger import log_llm_call

    model_name = os.environ.get("COPILOT_MODEL", "gemini-3.6-flash")
    req_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}] + messages

    # Define the 13 consolidated tools dynamically from planner_schemas
    tools_declarations = [
        types.FunctionDeclaration(
            name="upsert_variable",
            description="Create or update a state variable definition.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertVariable.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="delete_variable",
            description="Delete a state variable definition.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.DeleteVariable.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="rename_variable",
            description="Rename an existing state variable and update all node references.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.RenameVariable.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="upsert_logical_assigner",
            description="Create or update a logical assignment node. Routing MUST be set via connect.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertLogicalAssigner.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="upsert_agentic_assigner",
            description="Create or update an agentic assignment prompt node. Routing MUST be set via connect.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertAgenticAssigner.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="upsert_logical_switch",
            description="Create or update a conditional switch node. Defines branches with conditional logic. Routing MUST be set via connect with branch.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertLogicalSwitch.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="upsert_agentic_switch",
            description="Create or update an agentic routing switch node. Defines case labels. Routing MUST be set via connect with branch.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertAgenticSwitch.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="upsert_rag_retriever",
            description="Create or update a RAG context retrieval node. Routing MUST be set via connect.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertRagRetriever.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="upsert_interrupt",
            description="Create or update a human input interrupt checkpoint node. Routing MUST be set via connect.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.UpsertInterrupt.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="delete_node",
            description="Delete a node from the graph.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.DeleteNode.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="rename_node",
            description="Rename a node ID and update all transition targets.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.RenameNode.model_json_schema())
            ),
        ),
        types.FunctionDeclaration(
            name="connect",
            description="Connect an edge from source to target. Specify branch for switch nodes. Use source='start' for entrypoint.",
            parameters_json_schema=prune_json_schema(dereference_schema(planner_schemas.Connect.model_json_schema())),
        ),
        types.FunctionDeclaration(
            name="disconnect",
            description="Disconnect an outgoing edge from source. Specify branch for switch nodes.",
            parameters_json_schema=prune_json_schema(
                dereference_schema(planner_schemas.Disconnect.model_json_schema())
            ),
        ),
    ]

    tools: list[Any] = [types.Tool(function_declarations=tools_declarations)]

    # Map messages to types.Content structure
    gemini_contents = []
    for msg in messages:
        role = msg["role"]
        gemini_contents.append(
            types.Content(role="user" if role == "user" else "model", parts=[types.Part.from_text(text=msg["content"])])
        )

    config = types.GenerateContentConfig(
        system_instruction=PLANNER_SYSTEM_PROMPT,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.0,
    )

    tools_info = [
        {"name": td.name, "description": td.description, "parameters": td.parameters_json_schema}
        for td in tools_declarations
    ]

    try:
        async with client.aio as aclient:
            response = await aclient.models.generate_content(
                model=model_name,
                contents=gemini_contents,
                config=config,
            )
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model=model_name,
            messages=req_messages,
            response=response,
            graph_id=graph_id,
            tools=tools_info,
        )
    except Exception as e:
        log_llm_call(
            trace_id=trace_id,
            node_name="planner_node",
            model=model_name,
            messages=req_messages,
            error=str(e),
            graph_id=graph_id,
            tools=tools_info,
        )
        raise e

    function_calls = getattr(response, "function_calls", None)
    if not function_calls:
        raise Exception("Planner failed to generate any tool calls.")

    # Return serialized tool calls lists
    return [
        {
            "name": fc.name,
            "arguments": json.dumps(fc.args) if isinstance(fc.args, dict) else (fc.args or "{}"),
        }
        for fc in function_calls
    ]
