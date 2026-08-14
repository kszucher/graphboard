from __future__ import annotations

import asyncio
from typing import Any

from app.modules.graphs.compiler import generate_graph_code
from app.modules.graphs.schemas import GraphFlowData


def _execute_langgraph_in_thread(code: str) -> dict[str, Any]:
    exec_globals: dict[str, Any] = {}
    try:
        exec(code, exec_globals)
    except Exception as e:
        return {"variables": [], "error": f"Compilation/Execution failed: {str(e)}"}

    app = exec_globals.get("app")
    if not app:
        return {"variables": [], "error": "Compiled workflow does not define 'app'"}

    try:
        # Pass a recursion limit to invoke to natively prevent infinite loops
        config = {"recursion_limit": 50}
        final_state = app.invoke(exec_globals.get("initial_state", {}), config=config)
        return {"variables": [{"key": k, "value": v} for k, v in final_state.items()]}
    except Exception as e:
        from langgraph.errors import GraphRecursionError

        if isinstance(e, GraphRecursionError):
            return {
                "variables": [],
                "error": "LangGraph execution exceeded recursion limit (possible infinite loop)",
            }
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}


async def compile_flow_with_langgraph(flow_data: GraphFlowData) -> dict[str, Any]:
    try:
        code = await generate_graph_code(flow_data)

        # Offload synchronous execution to a thread to keep FastAPI event loop unblocked
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _execute_langgraph_in_thread, code)

    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}
