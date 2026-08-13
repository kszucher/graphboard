from typing import Any

from app.copilot.tools import CONFIG_TOOLS

CONFIG_SYSTEM_PROMPT = """
You are the Config Agent. Your only job is to bind logic and prompts into nodes based on the checklist.
You CANNOT create nodes or declare state variables. You only configure existing nodes.

Tools available:
- bind_logical_assignment
- bind_branch_condition
- configure_agentic_prompt
- configure_agentic_switch
- configure_rag_search
- configure_interrupt
"""


async def execute_config_tasks(client: Any, trace_id: str, graph_id: str, messages: list[dict[str, Any]], tasks: list[str]) -> list[dict[str, Any]]:
    """Executes config-related tasks using LLM tool calling."""
    if not tasks:
        return []

    from app.copilot.logger import log_llm_call

    task_list_str = "\n".join(f"- {task}" for task in tasks)
    system_message = {"role": "system", "content": f"{CONFIG_SYSTEM_PROMPT}\n\nTasks to execute:\n{task_list_str}"}
    req_messages = [system_message] + messages
    
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            tools=CONFIG_TOOLS,
            tool_choice="auto",
            temperature=0.0
        )
        log_llm_call(
            trace_id=trace_id,
            node_name="config_agent",
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            response=response,
            graph_id=graph_id,
            tools=CONFIG_TOOLS,
        )
    except Exception as e:
        log_llm_call(
            trace_id=trace_id,
            node_name="config_agent",
            model="llama-3.3-70b-versatile",
            messages=req_messages,
            error=str(e),
            graph_id=graph_id,
            tools=CONFIG_TOOLS,
        )
        raise e
    
    choice = response.choices[0]
    return choice.message.tool_calls or []
