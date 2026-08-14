from typing import Any

from app.copilot.tools import TOPOLOGY_TOOLS

TOPOLOGY_SYSTEM_PROMPT = """
You are the Topology Agent. Your only job is to create nodes and draw connections based on the checklist.
You CANNOT declare variables, write prompts, or bind logic. You only manage boxes and lines.

Tools available:
- create_node
- delete_node
- add_switch_branch
- remove_switch_branch
- connect
- disconnect
"""


async def execute_topology_tasks(
    client: Any, trace_id: str, graph_id: str, messages: list[dict[str, Any]], tasks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Executes topology-related tasks using LLM tool calling."""
    if not tasks:
        return []

    from app.copilot.logger import log_llm_call

    task_list_str = "\n".join(
        f"- Task: {t['op']} - {t['description']}" + (f" (Target ID: {t['node_id']})" if t.get("node_id") else "") for t in tasks
    )
    system_message = {"role": "system", "content": f"{TOPOLOGY_SYSTEM_PROMPT}\n\nTasks to execute:\n{task_list_str}"}
    req_messages = [system_message] + messages

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            tools=TOPOLOGY_TOOLS,
            tool_choice="auto",
            temperature=0.0,
        )
        log_llm_call(
            trace_id=trace_id,
            node_name="topology_agent",
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            response=response,
            graph_id=graph_id,
        )
    except Exception as e:
        log_llm_call(
            trace_id=trace_id,
            node_name="topology_agent",
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            error=str(e),
            graph_id=graph_id,
        )
        raise e

    choice = response.choices[0]
    return choice.message.tool_calls or []
