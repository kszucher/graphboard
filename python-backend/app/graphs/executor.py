from __future__ import annotations

import asyncio
import multiprocessing
from typing import Any

from app.graphs.compiler import generate_graph_code
from app.graphs.schemas import GraphFlowData


def _worker_execute_langgraph(code: str) -> dict[str, Any]:
    exec_globals: dict[str, Any] = {}
    try:
        exec(code, exec_globals)
    except Exception as e:
        return {"variables": [], "error": f"Compilation/Execution failed: {str(e)}"}

    app = exec_globals.get("app")
    if not app:
        return {"variables": [], "error": "Compiled workflow does not define 'app'"}

    try:
        final_state = app.invoke(exec_globals.get("initial_state", {}))
        return {"variables": [{"key": k, "value": v} for k, v in final_state.items()]}
    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}


def _process_target(code: str, queue: multiprocessing.Queue[Any]) -> None:
    result = _worker_execute_langgraph(code)
    queue.put(result)


async def compile_flow_with_langgraph(flow_data: GraphFlowData) -> dict[str, Any]:
    try:
        code = await generate_graph_code(flow_data)

        # Run compilation execution in a separate Process to allow explicit termination on timeout
        ctx = multiprocessing.get_context("spawn")
        queue: multiprocessing.Queue[Any] = ctx.Queue()
        process = ctx.Process(target=_process_target, args=(code, queue))
        process.start()

        loop = asyncio.get_running_loop()

        # Run process.join asynchronously inside an executor thread
        def join_with_timeout() -> None:
            process.join(timeout=5.0)

        await loop.run_in_executor(None, join_with_timeout)

        if process.is_alive():
            # Terminate immediately to free up CPU cores
            process.terminate()
            process.join()  # Clean up process resources
            return {"variables": [], "error": "LangGraph execution timed out (possible infinite loop in visual graph)"}

        if not queue.empty():
            res = queue.get()
            if isinstance(res, dict):
                return res
        return {"variables": [], "error": "LangGraph run did not return any result"}

    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}
