from typing import Any

from app.copilot.tools import STATE_TOOLS

STATE_SYSTEM_PROMPT = """
You are the State Agent. Your only job is to declare variables and define formulas based on the checklist.
You CANNOT create nodes or wire connections. 

Tools available:
- declare_variable
- delete_variable
- define_expression
"""


async def execute_state_tasks(
    client: Any, trace_id: str, graph_id: str, messages: list[dict[str, Any]], tasks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Executes state-related tasks using LLM tool calling."""
    if not tasks:
        return []

    from app.copilot.logger import log_llm_call

    task_list_str = "\n".join(
        f"- Task: {t['description']}" + (f" (Target ID: {t['node_id']})" if t.get("node_id") else "") for t in tasks
    )
    system_message = {"role": "system", "content": f"{STATE_SYSTEM_PROMPT}\n\nTasks to execute:\n{task_list_str}"}
    req_messages = [system_message] + messages

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            tools=STATE_TOOLS,
            tool_choice="auto",
            temperature=0.0,
        )
        log_llm_call(
            trace_id=trace_id,
            node_name="state_agent",
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            response=response,
            graph_id=graph_id,
        )
    except Exception as e:
        log_llm_call(
            trace_id=trace_id,
            node_name="state_agent",
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            error=str(e),
            graph_id=graph_id,
        )
        raise e

    choice = response.choices[0]
    return choice.message.tool_calls or []
