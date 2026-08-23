import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.graphs.engine.runner import _build_subprocess_script, compile_flow_with_langgraph
from app.modules.graphs.schemas import (
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    StartNode,
)


def test_build_subprocess_script() -> None:
    code = 'print("hello world")'
    script = _build_subprocess_script(code)
    assert "__GRAPHBOARD_OUTPUT__" in script
    assert '    print("hello world")' in script
    assert "class State" not in script or "workflow" in script


@pytest.mark.asyncio
async def test_compile_flow_with_langgraph_success() -> None:
    flow_data = GraphFlowData(
        nodes=[
            StartNode(id="start"),
            LogicalAssignerNode(
                id="init_val",
                assignments=[LogicalAssignmentSchema(id="asgn_1", target_var_key="count", expression={"set": 100})],
            ),
        ],
        edges=[
            EdgeRead(source="start", target="init_val"),
            EdgeRead(source="init_val", target="end"),
        ],
        state=[
            DefinerVariableSchema(id="v1", key="count", type="number", default_value=0),
        ],
    )

    result = await compile_flow_with_langgraph(flow_data)
    assert "error" not in result
    assert "variables" in result
    vars_map = {v["key"]: v["value"] for v in result["variables"]}
    assert vars_map.get("count") == 100


@pytest.mark.asyncio
async def test_compile_flow_with_langgraph_runtime_error() -> None:
    # A node assigning an invalid division by zero expression
    flow_data = GraphFlowData(
        nodes=[
            StartNode(id="start"),
            LogicalAssignerNode(
                id="divide_zero",
                assignments=[
                    LogicalAssignmentSchema(
                        id="asgn_1",
                        target_var_key="val",
                        expression={"op": "divide", "amount": 0},
                    )
                ],
            ),
        ],
        edges=[
            EdgeRead(source="start", target="divide_zero"),
            EdgeRead(source="divide_zero", target="end"),
        ],
        state=[
            DefinerVariableSchema(id="v1", key="val", type="number", default_value=10),
        ],
    )

    result = await compile_flow_with_langgraph(flow_data)
    assert "error" in result
    assert "division by zero" in result["error"].lower() or "runtime failed" in result["error"].lower()


@pytest.mark.asyncio
async def test_compile_flow_with_langgraph_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set runner timeout to very small duration
    from app.core.config import settings

    monkeypatch.setattr(settings, "runner_timeout_seconds", 0.05)

    # Subprocess execution taking longer than timeout
    async def mock_communicate(*args: Any, **kwargs: Any) -> tuple[bytes, bytes]:
        await asyncio.sleep(0.5)
        return b"", b""

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        from unittest.mock import Mock

        mock_process = AsyncMock()
        mock_process.communicate.side_effect = mock_communicate
        mock_process.kill = Mock()
        mock_process.wait = AsyncMock()
        mock_exec.return_value = mock_process

        flow_data = GraphFlowData(nodes=[], edges=[], state=[])
        result = await compile_flow_with_langgraph(flow_data)

        assert "error" in result
        assert "timed out" in result["error"].lower()
        mock_process.kill.assert_called_once()
