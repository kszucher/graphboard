from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from app.constants import EventName, NodeType
from app.graphs import operations as graph_operations
from app.graphs import topology as graph_topology
from app.graphs.compiler import generate_graph_code, run_ruff_diagnostics
from app.graphs.schemas import EdgeRead, GraphFlowData, GraphSyncPayload, NodeRead, SlotRead
from app.graphs.validation import validate_flow_data

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

    default_nodes = [
        NodeRead(id="start", node_type=NodeType.START, is_input=False, is_output=True, slots=[]),
        NodeRead(
            id="definer", node_type=NodeType.DEFINER, ref_id="op_def_main", is_input=True, is_output=True, slots=[]
        ),
        NodeRead(
            id="switch_step",
            node_type=NodeType.SWITCH,
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
        NodeRead(
            id="logical_assigner",
            node_type=NodeType.LOGICAL_ASSIGNER,
            ref_id="op_log_main",
            is_input=True,
            is_output=True,
            slots=[],
        ),
        NodeRead(
            id="agentic_assigner",
            node_type=NodeType.AGENTIC_ASSIGNER,
            ref_id="op_agent_main",
            is_input=True,
            is_output=True,
            slots=[],
        ),
        NodeRead(id="end", node_type=NodeType.END, is_input=True, is_output=False, slots=[]),
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
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "switch_step_option_a->logical_assigner"),
            source_id="switch_step_option_a",
            source_type="slot",
            target_id="logical_assigner",
            target_type="node",
        ),
        EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "switch_step_option_b->agentic_assigner"),
            source_id="switch_step_option_b",
            source_type="slot",
            target_id="agentic_assigner",
            target_type="node",
        ),
        EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "logical_assigner->end"),
            source_id="logical_assigner",
            source_type="node",
            target_id="end",
            target_type="node",
        ),
        EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, "agentic_assigner->end"),
            source_id="agentic_assigner",
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
        "logical": [
            {
                "id": "op_log_main",
                "assignments": [],
            }
        ],
        "agentic": [
            {
                "id": "op_agent_main",
                "prompt": "",
            }
        ],
        "switch": [],
    }

    flow_data = GraphFlowData.model_validate(
        {
            "nodes": default_nodes,
            "edges": default_edges,
            "operations": operations_container,
        }
    )
    compiled_code = await generate_graph_code(flow_data)
    flow_data.code = compiled_code
    initial_flow = flow_data.model_dump(mode="json")

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

    flow_data = GraphFlowData(
        nodes=payload.nodes,
        edges=payload.edges,
        operations=payload.operations,
    )
    return await _commit_state_snapshot(uow, graph, flow_data)


async def run_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    from app.graphs.compiler import compile_flow_with_langgraph

    flow_data = GraphFlowData.model_validate(graph.flow_json or {})
    exec_result = await compile_flow_with_langgraph(flow_data)

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return exec_result


async def reset_graph_history(uow: UnitOfWork, graph_id: uuid.UUID) -> None:
    graph = await uow.graphs.get(graph_id)
    if graph:
        flow_data = graph.flow_json or {}
        await uow.graph_history.clear_by_graph(graph_id)
        graph.current_history_sequence = 0
        await uow.graph_history.save_snapshot(graph_id, flow_data, 0)
        await uow.session.flush()


async def get_and_reset_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    flow_data = GraphFlowData.model_validate(graph.flow_json or {})

    existing_snapshot = await uow.graph_history.get_by_sequence(graph_id, 0)
    if not existing_snapshot:
        await reset_graph_history(uow, graph_id)

    return await _prepare_response_flow(uow, graph, flow_data)


async def _prepare_response_flow(uow: UnitOfWork, graph: models.Graph, flow_data: GraphFlowData) -> dict:
    next_snap = await uow.graph_history.get_by_sequence(graph.id, graph.current_history_sequence + 1)

    # 1. Run semantic validation
    semantic_diagnostics = validate_flow_data(flow_data)

    # 2. Run Ruff diagnostics
    ruff_diagnostics = await run_ruff_diagnostics(flow_data.code)

    # 3. Merge diagnostics
    all_diagnostics = []
    all_diagnostics.extend(semantic_diagnostics)
    all_diagnostics.extend(ruff_diagnostics)

    diag_dicts = [d.model_dump(mode="json") for d in all_diagnostics]

    res = flow_data.model_dump(mode="json")
    res.update(
        {
            "diagnostics": diag_dicts,
            "can_undo": graph.current_history_sequence > 0,
            "can_redo": next_snap is not None,
        }
    )
    return res


async def _commit_state_snapshot(uow: UnitOfWork, graph: models.Graph, flow_data: GraphFlowData) -> dict:
    # Clear future history branches
    await uow.graph_history.delete_future_snapshots(graph.id, graph.current_history_sequence)

    # Reformat/Compile Python code based on visual topology & operations
    generated_code = await generate_graph_code(flow_data)
    flow_data.code = generated_code

    # Convert to standard dict for database persistence
    updated_flow_dict = flow_data.model_dump(mode="json")

    # Increment sequence and save snapshot
    next_seq = graph.current_history_sequence + 1
    await uow.graph_history.save_snapshot(graph.id, updated_flow_dict, next_seq)

    # Update graph row
    graph.flow_json = updated_flow_dict
    graph.current_history_sequence = next_seq
    await uow.session.flush()

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return await _prepare_response_flow(uow, graph, flow_data)


async def undo_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    if graph.current_history_sequence <= 0:
        flow_data = GraphFlowData.model_validate(graph.flow_json or {})
        return await _prepare_response_flow(uow, graph, flow_data)

    prev_seq = graph.current_history_sequence - 1
    prev_snapshot = await uow.graph_history.get_by_sequence(graph.id, prev_seq)
    if not prev_snapshot:
        flow_data = GraphFlowData.model_validate(graph.flow_json or {})
        return await _prepare_response_flow(uow, graph, flow_data)

    flow_data = GraphFlowData.model_validate(prev_snapshot.flow_json)
    graph.flow_json = prev_snapshot.flow_json
    graph.current_history_sequence = prev_seq
    await uow.session.flush()

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return await _prepare_response_flow(uow, graph, flow_data)


async def redo_graph_flow(uow: UnitOfWork, graph_id: uuid.UUID) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    next_seq = graph.current_history_sequence + 1
    next_snapshot = await uow.graph_history.get_by_sequence(graph.id, next_seq)
    if not next_snapshot:
        flow_data = GraphFlowData.model_validate(graph.flow_json or {})
        return await _prepare_response_flow(uow, graph, flow_data)

    flow_data = GraphFlowData.model_validate(next_snapshot.flow_json)
    graph.flow_json = next_snapshot.flow_json
    graph.current_history_sequence = next_seq
    await uow.session.flush()

    uow.emit(event=EventName.GRAPH_UPDATED, graph_id=graph.id, payload={})
    return await _prepare_response_flow(uow, graph, flow_data)


# Helper orchestrator for mutations
async def _mutate_flow(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    mutate_fn: Callable[[GraphFlowData, *Any], GraphFlowData],
    *args: Any,
    **kwargs: Any,
) -> dict:
    graph = await uow.graphs.get(graph_id)
    if not graph:
        from app.exceptions import ValidationError

        raise ValidationError(f"Graph {graph_id} not found")

    flow_data = GraphFlowData.model_validate(graph.flow_json or {})
    mutated = mutate_fn(flow_data, *args, **kwargs)
    return await _commit_state_snapshot(uow, graph, mutated)


# Node Mutations Service Layer
async def add_node(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    node_type: NodeType | str,
    connector_id: str | None = None,
    direction: str | None = None,
) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.add_node, node_type, connector_id, direction)


async def delete_node(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.delete_node, node_id)


async def shortcircuit_node(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.shortcircuit_node, node_id)


async def update_node(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    node_id: str,
    new_id: str | None = None,
    is_input: bool | None = None,
    is_output: bool | None = None,
    ref_id: str | None = None,
) -> dict:
    return await _mutate_flow(
        uow,
        graph_id,
        graph_topology.update_node,
        node_id,
        new_id=new_id,
        is_input=is_input,
        is_output=is_output,
        ref_id=ref_id,
    )


# Slot Mutations Service Layer
async def create_slot(uow: UnitOfWork, graph_id: uuid.UUID, node_id: str, index: int) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.create_slot, node_id, index)


async def update_slot(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    slot_id: str,
    raw_string: str | None = None,
    expression: dict[str, Any] | None = None,
) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.update_slot, slot_id, raw_string, expression)


async def delete_slot(uow: UnitOfWork, graph_id: uuid.UUID, slot_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.delete_slot, slot_id)


async def move_slot(uow: UnitOfWork, graph_id: uuid.UUID, slot_id: str, direction: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.move_slot, slot_id, direction)


# Edge Mutations Service Layer
async def delete_edge(uow: UnitOfWork, graph_id: uuid.UUID, edge_id: uuid.UUID) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.delete_edge, edge_id)


async def create_edge(
    uow: UnitOfWork, graph_id: uuid.UUID, source: str, target: str, source_handle: str, target_handle: str
) -> dict:
    return await _mutate_flow(uow, graph_id, graph_topology.create_edge, source, target, source_handle, target_handle)


async def reconnect_edge(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    edge_id: uuid.UUID,
    source: str,
    target: str,
    source_handle: str,
    target_handle: str,
) -> dict:
    return await _mutate_flow(
        uow,
        graph_id,
        graph_topology.reconnect_edge,
        edge_id,
        source,
        target,
        source_handle,
        target_handle,
    )


# Definer Operations Service Layer
async def create_definer_variable(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    node_id: str,
    key: str,
    var_type: Literal["boolean", "string", "number", "float"] = "string",
    default_value: Any = None,
    description: str | None = None,
) -> dict:
    return await _mutate_flow(
        uow,
        graph_id,
        graph_operations.create_definer_variable,
        node_id,
        key,
        var_type,
        default_value,
        description,
    )


async def update_definer_variable(uow: UnitOfWork, graph_id: uuid.UUID, var_id: str, updates: dict) -> dict:
    return await _mutate_flow(uow, graph_id, graph_operations.update_definer_variable, var_id, updates)


async def delete_definer_variable(uow: UnitOfWork, graph_id: uuid.UUID, var_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_operations.delete_definer_variable, var_id)


# Logical Assigner Operations Service Layer
async def create_logical_assignment(
    uow: UnitOfWork,
    graph_id: uuid.UUID,
    node_id: str,
    target_var_key: str,
    value_type: Literal["boolean", "string", "number", "float"] = "string",
    value: Any = None,
    expression: dict[str, Any] | None = None,
) -> dict:
    return await _mutate_flow(
        uow,
        graph_id,
        graph_operations.create_logical_assignment,
        node_id,
        target_var_key,
        value_type,
        value,
        expression,
    )


async def update_logical_assignment(uow: UnitOfWork, graph_id: uuid.UUID, assignment_id: str, updates: dict) -> dict:
    return await _mutate_flow(uow, graph_id, graph_operations.update_logical_assignment, assignment_id, updates)


async def delete_logical_assignment(uow: UnitOfWork, graph_id: uuid.UUID, assignment_id: str) -> dict:
    return await _mutate_flow(uow, graph_id, graph_operations.delete_logical_assignment, assignment_id)
