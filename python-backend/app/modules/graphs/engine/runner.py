from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, cast

from app.core.config import settings
from app.modules.graphs.engine.compiler import generate_graph_code
from app.modules.graphs.schemas import GraphFlowData

logger = logging.getLogger(__name__)


def _build_subprocess_script(code: str) -> str:
    # Harness executes the LangGraph workflow and prints JSON output with a sentinel prefix
    harness = """
import json
import sys

try:
{indented_code}
except Exception as e:
    err_out = {{"variables": [], "error": f"Compilation/Execution failed: {{str(e)}}"}}
    print("__GRAPHBOARD_OUTPUT__" + json.dumps(err_out))
    sys.exit(0)

try:
    if "app" not in locals():
        err_out = {{"variables": [], "error": "Compiled workflow does not define 'app'"}}
        print("__GRAPHBOARD_OUTPUT__" + json.dumps(err_out))
        sys.exit(0)

    config = {{"recursion_limit": 50}}
    init_state = locals().get("initial_state", {{}})
    final_state = app.invoke(init_state, config=config)
    output = {{"variables": [{{"key": k, "value": v}} for k, v in final_state.items()]}}
    print("__GRAPHBOARD_OUTPUT__" + json.dumps(output))
except Exception as e:
    from langgraph.errors import GraphRecursionError
    if isinstance(e, GraphRecursionError):
        msg = "LangGraph execution exceeded recursion limit (possible infinite loop)"
    else:
        msg = f"LangGraph runtime failed: {{str(e)}}"
    err_out = {{"variables": [], "error": msg}}
    print("__GRAPHBOARD_OUTPUT__" + json.dumps(err_out))
"""
    indented_code = "\n".join("    " + line if line else "" for line in code.split("\n"))
    return harness.format(indented_code=indented_code)


async def compile_flow_with_langgraph(flow_data: GraphFlowData) -> dict[str, Any]:
    """Compiles and executes the visual graph in an isolated subprocess with a hard timeout."""
    timeout_sec = settings.runner_timeout_seconds
    try:
        code = await generate_graph_code(flow_data)
        script = _build_subprocess_script(code)

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=script.encode("utf-8")),
                timeout=timeout_sec,
            )
        except TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return {
                "variables": [],
                "error": f"Execution timed out (exceeded {timeout_sec}s hard limit).",
            }

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        for line in stdout_text.splitlines():
            if line.startswith("__GRAPHBOARD_OUTPUT__"):
                payload_str = line[len("__GRAPHBOARD_OUTPUT__") :]
                try:
                    return cast(dict[str, Any], json.loads(payload_str))
                except Exception:
                    pass

        if process.returncode != 0:
            error_msg = stderr_text.strip() or stdout_text.strip() or f"Process exited with code {process.returncode}"
            return {"variables": [], "error": f"Execution failed: {error_msg}"}

        return {"variables": []}

    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}
