import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.constants import EventName
from app.context import UnitOfWork
from app.graphs import service as graphs_service
from app.graphs.schemas import UpsertLogicalAssignerOp
from app.models import Graph, GraphHistory, User


@pytest.mark.asyncio
async def test_create_graph(
    real_uow: UnitOfWork,
    dummy_user: User,
    mock_broker: AsyncMock,
) -> None:
    # Call service to create graph
    graph_id = await graphs_service.create_graph(uow=real_uow, user_id=dummy_user.id, graph_name="New Test Graph")

    # Check returned ID
    assert isinstance(graph_id, uuid.UUID)

    # Commit UoW transaction
    await real_uow.commit()

    # Check database Graph record
    result = await real_uow.session.execute(select(Graph).where(Graph.id == graph_id))
    graph = result.scalar_one_or_none()
    assert graph is not None
    assert graph.name == "New Test Graph"
    assert graph.user_id == dummy_user.id

    # Check snapshot at sequence 0
    snapshot = await real_uow.graph_history.get_by_sequence(graph_id, 0)
    assert snapshot is not None
    assert "nodes" in snapshot.flow_json
    assert "edges" in snapshot.flow_json

    # Check that events were emitted on UoW commit
    mock_broker.emit.assert_called_once_with(
        event=EventName.GRAPH_CREATED, graph_id=graph_id, payload={"graphId": graph_id}, sender_client_id=None
    )


@pytest.mark.asyncio
async def test_add_node(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Action: add a node of type LOGICAL_ASSIGNER using apply_patch
    patch = [
        UpsertLogicalAssignerOp(
            op="upsert_logical_assigner",
            node_id="logical_assigner_1",
            assignments=[],
        )
    ]
    result = await graphs_service.apply_patch(uow=real_uow, graph_id=dummy_graph.id, patch=patch)

    await real_uow.commit()

    # Assert response
    assert "nodes" in result
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["node_type"] == "LOGICAL_ASSIGNER"

    # Check snapshot
    res_snap = await real_uow.session.execute(
        select(GraphHistory).where(GraphHistory.graph_id == dummy_graph.id, GraphHistory.sequence_number == 1)
    )
    snapshot = res_snap.scalar_one_or_none()
    assert snapshot is not None
    assert snapshot.flow_json["nodes"][0]["node_type"] == "LOGICAL_ASSIGNER"


@pytest.mark.asyncio
async def test_versions_graph_flow(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Get initial snapshot count
    init_snap = await real_uow.graph_history.get_by_sequence(dummy_graph.id, 0)
    assert init_snap is not None
    initial_count = len(init_snap.flow_json["nodes"])

    # Mutation 1 -> Sequence 1 (Add node)
    patch1 = [
        UpsertLogicalAssignerOp(
            op="upsert_logical_assigner",
            node_id="la_1",
            assignments=[],
        )
    ]
    await graphs_service.apply_patch(real_uow, dummy_graph.id, patch1)
    # Mutation 2 -> Sequence 2 (Add another node)
    patch2 = [
        UpsertLogicalAssignerOp(
            op="upsert_logical_assigner",
            node_id="la_2",
            assignments=[],
        )
    ]
    await graphs_service.apply_patch(real_uow, dummy_graph.id, patch2)

    await real_uow.session.commit()

    # Verify latest sequence is 2
    latest = await real_uow.graph_history.get_latest_snapshot(dummy_graph.id)
    assert latest is not None
    assert latest.sequence_number == 2
    assert len(latest.flow_json["nodes"]) == initial_count + 2

    # Get flow for version 1
    flow_v1 = await graphs_service.get_graph_flow(real_uow, dummy_graph.id, version=1)
    assert flow_v1["current_version"] == 1
    assert len(flow_v1["nodes"]) == initial_count + 1

    # Get flow for version 0
    flow_v0 = await graphs_service.get_graph_flow(real_uow, dummy_graph.id, version=0)
    assert flow_v0["current_version"] == 0
    assert len(flow_v0["nodes"]) == initial_count


@pytest.mark.asyncio
async def test_get_graph_flow_returns_versions(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Mutation -> Sequence 1
    patch = [UpsertLogicalAssignerOp(op="upsert_logical_assigner", node_id="la_1", assignments=[])]
    await graphs_service.apply_patch(real_uow, dummy_graph.id, patch)
    await real_uow.session.commit()

    # Fetching flow should return versions list and current_version
    flow = await graphs_service.get_graph_flow(real_uow, dummy_graph.id)
    assert flow["current_version"] == 1
    assert len(flow["versions"]) == 2


@pytest.mark.asyncio
async def test_run_graph_flow_success(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Setup workflow: START -> LOGICAL_ASSIGNER (sets x to 42) -> END
    # Declares state variable x: number
    flow_payload: dict[str, Any] = {
        "nodes": [
            {
                "id": "assigner_1",
                "node_type": "LOGICAL_ASSIGNER",
                "assignments": [
                    {
                        "id": "asgn_1",
                        "target_var_key": "x",
                        "expression": {"type": "literal", "value": 42},
                    }
                ],
            },
        ],
        "edges": [
            {"source": "start", "target": "assigner_1"},
            {"source": "assigner_1", "target": "end"},
        ],
        "state": [{"id": "v1", "key": "x", "type": "number", "default_value": 0}],
    }

    await real_uow.graph_history.clear_by_graph(dummy_graph.id)
    await real_uow.graph_history.save_snapshot(dummy_graph.id, flow_payload, 0)
    await real_uow.session.commit()

    # Action: Run graph
    exec_result = await graphs_service.run_graph_flow(real_uow, dummy_graph.id)

    # Assert
    assert "error" not in exec_result
    assert "variables" in exec_result

    # Check variable x value is updated to 42
    vars_dict = {v["key"]: v["value"] for v in exec_result["variables"]}
    assert vars_dict.get("x") == 42


@pytest.mark.asyncio
async def test_run_graph_flow_switch_routing(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Test Scenario 1: x = 5 (default_value) -> routes to assigner_a -> y = 100
    flow_payload_a: dict[str, Any] = {
        "nodes": [
            {
                "id": "switch_1",
                "node_type": "LOGICAL_SWITCH",
                "branches": [
                    {
                        "id": "switch_1_option_a",
                        "label": "option_a",
                        "expression": {
                            "type": "binary",
                            "left": {"type": "variable", "name": "x"},
                            "op": ">",
                            "right": {"type": "literal", "value": 0},
                        },
                    },
                    {
                        "id": "switch_1_option_b",
                        "label": "option_b",
                        "expression": {
                            "type": "literal",
                            "value": True,
                        },
                    },
                ],
            },
            {
                "id": "assigner_a",
                "node_type": "LOGICAL_ASSIGNER",
                "assignments": [
                    {
                        "id": "asgn_a",
                        "target_var_key": "y",
                        "expression": {
                            "type": "literal",
                            "value": 100,
                        },
                    }
                ],
            },
            {
                "id": "assigner_b",
                "node_type": "LOGICAL_ASSIGNER",
                "assignments": [
                    {
                        "id": "asgn_b",
                        "target_var_key": "y",
                        "expression": {
                            "type": "literal",
                            "value": 200,
                        },
                    }
                ],
            },
        ],
        "edges": [
            {"source": "start", "target": "switch_1"},
            {"source": "switch_1", "source_handle": "switch_1_option_a", "target": "assigner_a"},
            {"source": "switch_1", "source_handle": "switch_1_option_b", "target": "assigner_b"},
            {"source": "assigner_a", "target": "end"},
            {"source": "assigner_b", "target": "end"},
        ],
        "state": [
            {"id": "v1", "key": "x", "type": "number", "default_value": 5},
            {"id": "v2", "key": "y", "type": "number", "default_value": 0},
        ],
    }

    await real_uow.graph_history.clear_by_graph(dummy_graph.id)
    await real_uow.graph_history.save_snapshot(dummy_graph.id, flow_payload_a, 0)
    await real_uow.session.commit()

    exec_result_a = await graphs_service.run_graph_flow(real_uow, dummy_graph.id)
    assert "error" not in exec_result_a
    vars_dict_a = {v["key"]: v["value"] for v in exec_result_a["variables"]}
    assert vars_dict_a.get("y") == 100

    # Test Scenario 2: x = -5 (default_value) -> routes to assigner_b -> y = 200
    flow_payload_b = dict(flow_payload_a)
    flow_payload_b["state"] = [
        {"id": "v1", "key": "x", "type": "number", "default_value": -5},
        {"id": "v2", "key": "y", "type": "number", "default_value": 0},
    ]

    await real_uow.graph_history.clear_by_graph(dummy_graph.id)
    await real_uow.graph_history.save_snapshot(dummy_graph.id, flow_payload_b, 0)
    await real_uow.session.commit()

    exec_result_b = await graphs_service.run_graph_flow(real_uow, dummy_graph.id)
    assert "error" not in exec_result_b
    vars_dict_b = {v["key"]: v["value"] for v in exec_result_b["variables"]}
    assert vars_dict_b.get("y") == 200


@pytest.mark.asyncio
async def test_run_graph_flow_invalid_state_ref(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Assigner node attempts to mutate target "non_existent" not registered in state
    flow_payload: dict[str, Any] = {
        "nodes": [
            {
                "id": "assigner_1",
                "node_type": "LOGICAL_ASSIGNER",
                "assignments": [
                    {
                        "id": "asgn_1",
                        "target_var_key": "non_existent",
                        "expression": {"type": "literal", "value": 42},
                    }
                ],
            },
        ],
        "edges": [
            {"source": "start", "target": "assigner_1"},
            {"source": "assigner_1", "target": "end"},
        ],
        "state": [{"id": "v1", "key": "x", "type": "number", "default_value": 0}],
    }

    await real_uow.graph_history.clear_by_graph(dummy_graph.id)
    await real_uow.graph_history.save_snapshot(dummy_graph.id, flow_payload, 0)
    await real_uow.session.commit()

    exec_result = await graphs_service.run_graph_flow(real_uow, dummy_graph.id)

    # Compilation should fail due to invalid mutation target
    assert "error" in exec_result
    assert "Compilation/Execution failed" in exec_result["error"]
    assert "non_existent" in exec_result["error"]


@pytest.mark.asyncio
async def test_run_graph_flow_cycle_limit(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Cyclic loop: START -> assigner_1 -> assigner_2 -> assigner_1 -> ...
    flow_payload: dict[str, Any] = {
        "nodes": [
            {"id": "assigner_1", "node_type": "LOGICAL_ASSIGNER", "assignments": []},
            {"id": "assigner_2", "node_type": "LOGICAL_ASSIGNER", "assignments": []},
        ],
        "edges": [
            {"source": "start", "target": "assigner_1"},
            {"source": "assigner_1", "target": "assigner_2"},
            {"source": "assigner_2", "target": "assigner_1"},
        ],
        "state": [{"id": "v1", "key": "x", "type": "number", "default_value": 0}],
    }

    await real_uow.graph_history.clear_by_graph(dummy_graph.id)
    await real_uow.graph_history.save_snapshot(dummy_graph.id, flow_payload, 0)
    await real_uow.session.commit()

    exec_result = await graphs_service.run_graph_flow(real_uow, dummy_graph.id)

    # Execution should fail with recursion limit error or timeout caught
    assert "error" in exec_result
    assert (
        "recursion limit" in exec_result["error"].lower()
        or "recursion" in exec_result["error"].lower()
        or "time out" in exec_result["error"].lower()
        or "timed out" in exec_result["error"].lower()
        or "timeout" in exec_result["error"].lower()
    )
