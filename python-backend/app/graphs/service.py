from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.constants import EventName
from app.graphs.schemas import GraphSyncPayload

if TYPE_CHECKING:
    from app import models
    from app.context import UnitOfWork


async def create_graph(
    uow: UnitOfWork,
    user_id: uuid.UUID,
    graph_name: str,
) -> uuid.UUID:
    graph = await uow.graphs.create(user_id=user_id, name=graph_name)

    import uuid as py_uuid

    from app.graphs.langgraph_sync import generate_graph_code
    from app.graphs.schemas import EdgeRead, NodeRead, SlotRead

    default_nodes = [
        NodeRead(id="start", node_type="START", is_input=False, is_output=True, slots=[]),
        NodeRead(id="definer", node_type="DEFINER", ref_id="op_def_main", is_input=True, is_output=True, slots=[]),
        NodeRead(
            id="switch_step",
            node_type="SWITCH",
            is_input=True,
            is_output=False,
            slots=[
                SlotRead(
                    id="switch_step_option_a",
                    raw_string="option_a",
                    expression={
                        "kind": "binaryOp",
                        "op": ">",
                        "left": {"kind": "stateRef", "varKey": "x"},
                        "right": {"kind": "literal", "value": 0},
                    },
                ),
                SlotRead(
                    id="switch_step_option_b",
                    raw_string="option_b",
                    expression={"kind": "literal", "value": True},
                ),
            ],
        ),
        NodeRead(id="step_a", node_type="STEP", is_input=True, is_output=True, slots=[]),
        NodeRead(id="step_b", node_type="STEP", is_input=True, is_output=True, slots=[]),
        NodeRead(id="end", node_type="END", is_input=True, is_output=False, slots=[]),
    ]
    default_edges = [
        EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "start->definer"),
            source_id="start",
            source_type="node",
            target_id="definer",
            target_type="node",
        ),
        EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "definer->switch_step"),
            source_id="definer",
            source_type="node",
            target_id="switch_step",
            target_type="node",
        ),
        EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "switch_step_option_a->step_a"),
            source_id="switch_step_option_a",
            source_type="slot",
            target_id="step_a",
            target_type="node",
        ),
        EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "switch_step_option_b->step_b"),
            source_id="switch_step_option_b",
            source_type="slot",
            target_id="step_b",
            target_type="node",
        ),
        EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "step_a->end"),
            source_id="step_a",
            source_type="node",
            target_id="end",
            target_type="node",
        ),
        EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "step_b->end"),
            source_id="step_b",
            source_type="node",
            target_id="end",
            target_type="node",
        ),
    ]
    operations_container = {
        "definer": [
            {
                "id": "op_def_main",
                "variables": [{"id": "v1", "key": "x", "type": "number", "default_value": 0}],
            }
        ],
        "agentic": [],
        "logical": [],
        "switch": [],
    }

    payload = {
        "nodes": [n.model_dump(mode="json") for n in default_nodes],
        "edges": [e.model_dump(mode="json") for e in default_edges],
        "operations": operations_container,
    }
    compiled_code = generate_graph_code(payload)

    initial_flow = {
        "code": compiled_code,
        "nodes": payload["nodes"],
        "edges": payload["edges"],
        "operations": payload["operations"],
    }
    graph.flow_json = initial_flow
    await uow.session.flush()

    await uow.users.set_active_graph(user_id, graph.id)

    uow.emit(
        event=EventName.GRAPH_CREATED,
        graph_id=graph.id,
        payload={"graphId": graph.id},
    )
    return graph.id


async def list_graphs_by_user(uow: UnitOfWork, user_id: uuid.UUID) -> list:
    return await uow.graphs.list_by_user(user_id)


async def sync_graph_flow(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    payload: GraphSyncPayload,
) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    payload_dict = payload.model_dump(mode="json")
    return await _commit_state_snapshot(uow, graph, payload_dict)


async def run_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    """
    Compiles and executes the graph, updating state variables in the database.
    """
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Graph not found")

    from fastapi import HTTPException

    from app.graphs.compiler import compile_flow_with_langgraph
    from app.graphs.schemas import GraphFlowRead

    flow_json = dict(graph.flow_json) if graph.flow_json else {"nodes": [], "edges": [], "state_schema": []}
    flow = GraphFlowRead.model_validate(flow_json)

    try:
        app = compile_flow_with_langgraph(flow)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Compilation Error: {str(e)}")

    initial_input = {v.key: v.default_value for v in flow.state_schema}

    try:
        final_state = await app.ainvoke(initial_input)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Execution Error: {str(e)}")

    return {"state": final_state}


async def get_and_reset_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    flow_data = graph.flow_json or {}

    # Reset/clear history snapshots on graph load only if snapshot 0 doesn't exist
    existing_snapshot = await uow.graph_history.get_by_sequence(graph_id, 0)
    if not existing_snapshot:
        await uow.graph_history.clear_by_graph(graph_id)
        graph.current_history_sequence = 0
        await uow.graph_history.save_snapshot(graph_id, flow_data, 0)
        await uow.session.flush()

    return await _prepare_response_flow(uow, graph, flow_data)


async def _prepare_response_flow(uow: UnitOfWork, graph: models.Graph, flow_data: dict) -> dict:
    from app.graphs.langgraph_sync import run_ruff_diagnostics

    next_snap = await uow.graph_history.get_by_sequence(graph.id, graph.current_history_sequence + 1)
    code = flow_data.get("code", "")
    diagnostics = run_ruff_diagnostics(code)
    diag_dicts = [d.model_dump(mode="json") for d in diagnostics]

    return {
        **flow_data,
        "diagnostics": diag_dicts,
        "can_undo": graph.current_history_sequence > 0,
        "can_redo": next_snap is not None,
    }


async def _commit_state_snapshot(uow: UnitOfWork, graph: models.Graph, flow_data: dict) -> dict:
    from app.constants import EventName
    from app.graphs.langgraph_sync import generate_graph_code

    # Clear future history branches
    await uow.graph_history.delete_future_snapshots(graph.id, graph.current_history_sequence)

    # Reformat/Compile Python code based on the new visual elements
    generated_code = generate_graph_code(flow_data)

    # Prepare final flow structure
    updated_flow = {
        "code": generated_code,
        "nodes": flow_data.get("nodes", []),
        "edges": flow_data.get("edges", []),
        "operations": flow_data.get("operations", {"definer": [], "agentic": [], "logical": [], "switch": []}),
    }

    # Increment sequence and save snapshot
    next_seq = graph.current_history_sequence + 1
    await uow.graph_history.save_snapshot(graph.id, updated_flow, next_seq)

    # Update graph row
    graph.flow_json = updated_flow
    graph.current_history_sequence = next_seq
    await uow.session.flush()

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return await _prepare_response_flow(uow, graph, updated_flow)


async def undo_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    if graph.current_history_sequence <= 0:
        return graph.flow_json

    prev_seq = graph.current_history_sequence - 1
    snapshot = await uow.graph_history.get_by_sequence(graph_id, prev_seq)
    if snapshot:
        graph.flow_json = snapshot.flow_json
        graph.current_history_sequence = prev_seq
        await uow.session.flush()

        from app.constants import EventName

        uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph_id, payload={})

    return await _prepare_response_flow(uow, graph, graph.flow_json)


async def redo_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    next_seq = graph.current_history_sequence + 1
    snapshot = await uow.graph_history.get_by_sequence(graph_id, next_seq)
    if snapshot:
        graph.flow_json = snapshot.flow_json
        graph.current_history_sequence = next_seq
        await uow.session.flush()

        from app.constants import EventName

        uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph_id, payload={})

    return await _prepare_response_flow(uow, graph, graph.flow_json)


async def add_node(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    node_type: str,
    connector_id: str | None = None,
    direction: str | None = None,
) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.add_node(graph.flow_json, node_type, connector_id, direction)
    return await _commit_state_snapshot(uow, graph, mutated)


async def update_node(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str, updates: dict) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    flow_data = graph.flow_json or {}

    new_id = updates.get("new_id")
    if new_id:
        from app.graphs.ast_editor import CodeASTEditor

        editor = CodeASTEditor(flow_data.get("code", ""))
        if editor.rename_function(node_id, new_id):
            flow_data["code"] = editor.get_code()

    from app.graphs import graph_mutations

    mutated = graph_mutations.update_node(flow_data, node_id, updates)

    return await _commit_state_snapshot(uow, graph, mutated)


async def delete_node(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.delete_node(graph.flow_json, node_id)
    return await _commit_state_snapshot(uow, graph, mutated)


async def shortcircuit_node(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.shortcircuit_node(graph.flow_json, node_id)
    return await _commit_state_snapshot(uow, graph, mutated)


async def create_slot(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str, index: int) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.create_slot(graph.flow_json, node_id, index)
    return await _commit_state_snapshot(uow, graph, mutated)


async def update_slot(uow: UnitOfWork, graph_id: uuid.UUID, slot_id: str, raw_string: str) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.update_slot(graph.flow_json, slot_id, raw_string)
    return await _commit_state_snapshot(uow, graph, mutated)


async def delete_slot(uow: UnitOfWork, graph_id: uuid.UUID, slot_id: str) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.delete_slot(graph.flow_json, slot_id)
    return await _commit_state_snapshot(uow, graph, mutated)


async def move_slot(uow: UnitOfWork, graph_id: uuid.UUID, slot_id: str, direction: str) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.move_slot(graph.flow_json, slot_id, direction)
    return await _commit_state_snapshot(uow, graph, mutated)


async def delete_edge(uow: UnitOfWork, graph_id: uuid.UUID, edge_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.delete_edge(graph.flow_json, edge_id)
    return await _commit_state_snapshot(uow, graph, mutated)


async def create_edge(
    uow: UnitOfWork, graph_id: uuid.UUID, source: str, target: str, source_handle: str, target_handle: str
) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.create_edge(graph.flow_json, source, target, source_handle, target_handle)
    return await _commit_state_snapshot(uow, graph, mutated)


async def reconnect_edge(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    edge_id: uuid.UUID,
    source: str,
    target: str,
    source_handle: str,
    target_handle: str,
) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.reconnect_edge(graph.flow_json, edge_id, source, target, source_handle, target_handle)
    return await _commit_state_snapshot(uow, graph, mutated)


async def create_definer_variable(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    node_id: str,
    key: str,
    var_type: str = "string",
    default_value: Any = None,
    description: str | None = None,
) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.create_definer_variable(
        graph.flow_json, node_id, key, var_type, default_value, description
    )
    return await _commit_state_snapshot(uow, graph, mutated)


async def update_definer_variable(uow: UnitOfWork, graph_id: uuid.UUID, var_id: str, updates: dict) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.update_definer_variable(graph.flow_json, var_id, updates)
    return await _commit_state_snapshot(uow, graph, mutated)


async def delete_definer_variable(uow: UnitOfWork, graph_id: uuid.UUID, var_id: str) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs import graph_mutations

    mutated = graph_mutations.delete_definer_variable(graph.flow_json, var_id)
    return await _commit_state_snapshot(uow, graph, mutated)
