import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.constants import EventName, NodeType
from app.context import UnitOfWork
from app.graphs import service as graphs_service
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
    assert "nodes" in graph.flow_json
    assert "edges" in graph.flow_json
    assert "code" not in graph.flow_json

    # Check that events were emitted on UoW commit
    mock_broker.emit.assert_called_once_with(
        event=EventName.GRAPH_CREATED, graph_id=graph_id, payload={"graphId": graph_id}, sender_client_id=None
    )


@pytest.mark.asyncio
async def test_add_node(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Action: add a node of type STEP
    result = await graphs_service.add_node(uow=real_uow, graph_id=dummy_graph.id, node_type=NodeType.STEP)

    await real_uow.commit()

    # Assert response
    assert "nodes" in result
    # Check that a STEP node was created
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["node_type"] == "STEP"

    # Check database records
    await real_uow.session.refresh(dummy_graph)
    assert dummy_graph.current_history_sequence == 1
    assert len(dummy_graph.flow_json["nodes"]) == 1

    # Check snapshot
    res_snap = await real_uow.session.execute(
        select(GraphHistory).where(GraphHistory.graph_id == dummy_graph.id, GraphHistory.sequence_number == 1)
    )
    snapshot = res_snap.scalar_one_or_none()
    assert snapshot is not None
    assert snapshot.flow_json["nodes"][0]["node_type"] == "STEP"


@pytest.mark.asyncio
async def test_undo_redo_graph_flow(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Save baseline snapshot (sequence 0)
    await real_uow.graph_history.save_snapshot(dummy_graph.id, dummy_graph.flow_json, 0)
    await real_uow.session.commit()

    # Get initial node count
    initial_count = len(dummy_graph.flow_json["nodes"])

    # Mutation 1 -> Sequence 1 (Add node)
    await graphs_service.add_node(real_uow, dummy_graph.id, NodeType.STEP)
    # Mutation 2 -> Sequence 2 (Add another node)
    await graphs_service.add_node(real_uow, dummy_graph.id, NodeType.STEP)

    await real_uow.session.refresh(dummy_graph)
    assert dummy_graph.current_history_sequence == 2
    assert len(dummy_graph.flow_json["nodes"]) == initial_count + 2

    # Perform Undo -> Sequence 1 (1 node removed)
    undo_res = await graphs_service.undo_graph_flow(real_uow, dummy_graph.id)
    assert undo_res["can_undo"] is True
    assert undo_res["can_redo"] is True
    assert len(undo_res["nodes"]) == initial_count + 1

    # Perform Undo again -> Sequence 0 (back to initial default nodes)
    undo_res2 = await graphs_service.undo_graph_flow(real_uow, dummy_graph.id)
    assert undo_res2["can_undo"] is False
    assert undo_res2["can_redo"] is True
    assert len(undo_res2["nodes"]) == initial_count

    # Perform Redo -> Sequence 1
    redo_res = await graphs_service.redo_graph_flow(real_uow, dummy_graph.id)
    assert redo_res["can_undo"] is True
    assert redo_res["can_redo"] is True
    assert len(redo_res["nodes"]) == initial_count + 1


@pytest.mark.asyncio
async def test_run_graph_flow_success(
    real_uow: UnitOfWork,
    dummy_graph: Graph,
) -> None:
    # Setup workflow: START -> STEP (sets x to 42) -> END
    # Declares state variable x: number
    flow_payload: dict[str, Any] = {
        "nodes": [
            {
                "id": "step_1",
                "node_type": "STEP",
                "slots": [{"target_var_key": "x", "expression": {"kind": "literal", "value": 42}}],
            },
        ],
        "edges": [
            {"source_id": "start", "target_id": "step_1"},
            {"source_id": "step_1", "source_type": "node", "target_id": "end"},
        ],
        "state": [{"id": "v1", "key": "x", "type": "number", "default_value": 0}],
    }

    dummy_graph.flow_json = flow_payload
    real_uow.session.add(dummy_graph)
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
    # Test Scenario 1: x = 5 (default_value) -> routes to step_a -> y = 100
    flow_payload_a: dict[str, Any] = {
        "nodes": [
            {
                "id": "switch_1",
                "node_type": "SWITCH",
                "slots": [
                    {
                        "id": "slot_a",
                        "raw_string": "option_a",
                        "expression": {
                            "kind": "binaryOp",
                            "op": ">",
                            "left": {"kind": "stateRef", "varKey": "x"},
                            "right": {"kind": "literal", "value": 0},
                        },
                    },
                    {"id": "slot_b", "raw_string": "option_b", "expression": {"kind": "literal", "value": True}},
                ],
            },
            {
                "id": "step_a",
                "node_type": "STEP",
                "slots": [{"target_var_key": "y", "expression": {"kind": "literal", "value": 100}}],
            },
            {
                "id": "step_b",
                "node_type": "STEP",
                "slots": [{"target_var_key": "y", "expression": {"kind": "literal", "value": 200}}],
            },
        ],
        "edges": [
            {"source_id": "start", "target_id": "switch_1"},
            {"source_id": "slot_a", "source_type": "slot", "target_id": "step_a"},
            {"source_id": "slot_b", "source_type": "slot", "target_id": "step_b"},
            {"source_id": "step_a", "source_type": "node", "target_id": "end"},
            {"source_id": "step_b", "source_type": "node", "target_id": "end"},
        ],
        "state": [
            {"id": "v1", "key": "x", "type": "number", "default_value": 5},
            {"id": "v2", "key": "y", "type": "number", "default_value": 0},
        ],
    }

    dummy_graph.flow_json = flow_payload_a
    real_uow.session.add(dummy_graph)
    await real_uow.session.commit()

    exec_result_a = await graphs_service.run_graph_flow(real_uow, dummy_graph.id)
    assert "error" not in exec_result_a
    vars_dict_a = {v["key"]: v["value"] for v in exec_result_a["variables"]}
    assert vars_dict_a.get("y") == 100

    # Test Scenario 2: x = -5 (default_value) -> routes to step_b -> y = 200
    flow_payload_b = dict(flow_payload_a)
    flow_payload_b["state"] = [
        {"id": "v1", "key": "x", "type": "number", "default_value": -5},
        {"id": "v2", "key": "y", "type": "number", "default_value": 0},
    ]

    dummy_graph.flow_json = flow_payload_b
    real_uow.session.add(dummy_graph)
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
    # Step node attempts to mutate target "non_existent" not registered in state
    flow_payload: dict[str, Any] = {
        "nodes": [
            {
                "id": "step_1",
                "node_type": "STEP",
                "slots": [{"target_var_key": "non_existent", "expression": {"kind": "literal", "value": 42}}],
            },
        ],
        "edges": [
            {"source_id": "start", "target_id": "step_1"},
            {"source_id": "step_1", "source_type": "node", "target_id": "end"},
        ],
        "state": [{"id": "v1", "key": "x", "type": "number", "default_value": 0}],
    }

    dummy_graph.flow_json = flow_payload
    real_uow.session.add(dummy_graph)
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
    # Cyclic loop: START -> step_1 -> step_2 -> step_1 -> ...
    flow_payload: dict[str, Any] = {
        "nodes": [
            {"id": "step_1", "node_type": "STEP", "slots": []},
            {"id": "step_2", "node_type": "STEP", "slots": []},
        ],
        "edges": [
            {"source_id": "start", "target_id": "step_1"},
            {"source_id": "step_1", "source_type": "node", "target_id": "step_2"},
            {"source_id": "step_2", "source_type": "node", "target_id": "step_1"},
        ],
        "state": [{"id": "v1", "key": "x", "type": "number", "default_value": 0}],
    }

    dummy_graph.flow_json = flow_payload
    real_uow.session.add(dummy_graph)
    await real_uow.session.commit()

    exec_result = await graphs_service.run_graph_flow(real_uow, dummy_graph.id)

    # Execution should fail with recursion limit error caught
    assert "error" in exec_result
    assert "recursion limit" in exec_result["error"].lower() or "recursion" in exec_result["error"].lower()
