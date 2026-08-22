from __future__ import annotations

import uuid
from typing import cast

from app.core.constants import NodeType
from app.core.exceptions import ValidationError
from app.modules.graphs.expressions import (
    ComparisonExpression,
    Expression,
    rename_expression_variables,
)
from app.modules.graphs.nodes import (
    NODE_CLASS_MAP,
    BaseNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    NodeRead,
)
from app.modules.graphs.operations.handlers import NODE_HANDLERS
from app.modules.graphs.operations.schemas import (
    GraphUpdateInput,
    NodeUpsertInput,
    RenameInput,
    VariableUpsertInput,
)
from app.modules.graphs.schemas import DefinerVariableSchema, EdgeRead, GraphFlowData
from app.modules.graphs.variables import rename_node_variable_references


def apply_variable_renames(flow_data: GraphFlowData, renames: list[RenameInput]) -> None:
    for ru in renames:
        var_schema = next((v for v in flow_data.state if v.key == ru.old_key), None)
        if not var_schema:
            raise ValidationError(f"Variable '{ru.old_key}' not found in graph state.")
        if any(v.key == ru.new_key for v in flow_data.state):
            raise ValidationError(f"Variable '{ru.new_key}' already exists.")

        var_schema.key = ru.new_key

        # Rename in node expressions and references
        for n in flow_data.nodes:
            if isinstance(n, LogicalAssignerNode):
                for a in n.assignments:
                    if a.expression is not None:
                        a.expression = cast(
                            Expression, rename_expression_variables(a.expression, ru.old_key, ru.new_key)
                        )
            elif isinstance(n, LogicalSwitchNode):
                for b in n.branches:
                    if b.expression is not None:
                        b.expression = cast(
                            ComparisonExpression, rename_expression_variables(b.expression, ru.old_key, ru.new_key)
                        )

            rename_node_variable_references(n, ru.old_key, ru.new_key)


def apply_node_renames(flow_data: GraphFlowData, renames: list[RenameInput]) -> None:
    for rn in renames:
        node = next((n for n in flow_data.nodes if n.id == rn.old_key), None)
        if not node:
            raise ValidationError(f"Node '{rn.old_key}' not found.")
        if any(n.id == rn.new_key for n in flow_data.nodes):
            raise ValidationError(f"Node '{rn.new_key}' already exists.")

        node.handle_node_rename(rn.old_key, rn.new_key)

        # Update edges
        for edge in flow_data.edges:
            if edge.source == rn.old_key:
                edge.source = rn.new_key
                if edge.source_handle and edge.source_handle.startswith(f"{rn.old_key}_"):
                    edge.source_handle = edge.source_handle.replace(f"{rn.old_key}_", f"{rn.new_key}_", 1)
            if edge.target == rn.old_key:
                edge.target = rn.new_key
                if edge.target_handle and edge.target_handle.startswith(f"{rn.old_key}_"):
                    edge.target_handle = edge.target_handle.replace(f"{rn.old_key}_", f"{rn.new_key}_", 1)


def apply_variable_deletions(flow_data: GraphFlowData, deletes: list[str]) -> None:
    for d_var in deletes:
        var_schema = next((v for v in flow_data.state if v.key == d_var), None)
        if not var_schema:
            raise ValidationError(f"Variable '{d_var}' not found in state.")
        flow_data.state.remove(var_schema)


def apply_variable_upserts(flow_data: GraphFlowData, upserts: list[VariableUpsertInput]) -> None:
    for u_var in upserts:
        if not isinstance(u_var, VariableUpsertInput):
            u_var = VariableUpsertInput(**u_var)
        existing = next((v for v in flow_data.state if v.key == u_var.key), None)
        if existing:
            existing.type = u_var.type
            existing.default_value = u_var.default_value
            existing.description = u_var.description
        else:
            flow_data.state.append(
                DefinerVariableSchema(
                    id=str(uuid.uuid4()),
                    key=u_var.key,
                    type=u_var.type,
                    default_value=u_var.default_value,
                    description=u_var.description,
                )
            )


def apply_node_deletions(flow_data: GraphFlowData, deletes: list[str]) -> None:
    for d_node in deletes:
        node = next((n for n in flow_data.nodes if n.id == d_node), None)
        if not node:
            raise ValidationError(f"Node '{d_node}' not found.")
        flow_data.nodes.remove(node)
        # Delete associated edges
        flow_data.edges = [e for e in flow_data.edges if e.source != d_node and e.target != d_node]


def apply_node_upserts(flow_data: GraphFlowData, upserts: list[NodeUpsertInput]) -> None:
    valid_keys = {v.key for v in flow_data.state}
    for u_node in upserts:
        if not isinstance(u_node, NodeUpsertInput):
            u_node = NodeUpsertInput(**u_node)

        existing_node = next((n for n in flow_data.nodes if n.id == u_node.id), None)
        upserted_node: BaseNode

        if existing_node:
            if existing_node.node_type != u_node.node_type:
                node_cls = NODE_CLASS_MAP.get(u_node.node_type)
                if not node_cls:
                    raise ValidationError(f"Unsupported node type '{u_node.node_type}'.")
                upserted_node = node_cls(id=u_node.id)
                idx = flow_data.nodes.index(existing_node)
                flow_data.nodes[idx] = cast(NodeRead, upserted_node)

                # Clean up outdated outgoing edges if transitioning between switch and linear
                is_old_switch = existing_node.node_type in {NodeType.LOGICAL_SWITCH, NodeType.AGENTIC_SWITCH}
                is_new_switch = u_node.node_type in {NodeType.LOGICAL_SWITCH, NodeType.AGENTIC_SWITCH}
                if is_old_switch and not is_new_switch:
                    flow_data.edges = [
                        e for e in flow_data.edges if not (e.source == u_node.id and e.source_handle is not None)
                    ]
                elif not is_old_switch and is_new_switch:
                    flow_data.edges = [
                        e for e in flow_data.edges if not (e.source == u_node.id and e.source_handle is None)
                    ]
            else:
                upserted_node = existing_node
        else:
            node_cls = NODE_CLASS_MAP.get(u_node.node_type)
            if not node_cls:
                raise ValidationError(f"Unsupported node type '{u_node.node_type}'.")
            upserted_node = node_cls(id=u_node.id)
            flow_data.nodes.append(cast(NodeRead, upserted_node))

        # Update linear targets
        if u_node.node_type in {
            NodeType.LOGICAL_ASSIGNER,
            NodeType.AGENTIC_ASSIGNER,
            NodeType.RAG_RETRIEVER,
            NodeType.INTERRUPT,
        }:
            if u_node.target is not None:
                flow_data.edges = [
                    e for e in flow_data.edges if not (e.source == u_node.id and e.source_handle is None)
                ]
                if u_node.target:
                    flow_data.edges.append(EdgeRead(source=u_node.id, target=u_node.target))

        # Delegate configuration & validation to polymorphic node handler
        handler = NODE_HANDLERS.get(u_node.node_type)
        if handler:
            handler(upserted_node, u_node, flow_data, valid_keys)


def apply_start_target(flow_data: GraphFlowData, start_target: str | None) -> None:
    if start_target is not None:
        flow_data.edges = [e for e in flow_data.edges if e.source != "start"]
        if start_target:
            flow_data.edges.append(EdgeRead(source="start", target=start_target))


def apply_graph_update(flow_data: GraphFlowData, update: GraphUpdateInput) -> GraphFlowData:
    """Applies a declarative transaction update to the Graph Flow Data."""
    # 1. Rename Variables
    if update.rename_variables:
        apply_variable_renames(flow_data, update.rename_variables)

    # 2. Rename Nodes
    if update.rename_nodes:
        apply_node_renames(flow_data, update.rename_nodes)

    # 3. Delete Variables
    if update.variables and update.variables.delete:
        apply_variable_deletions(flow_data, update.variables.delete)

    # 4. Upsert Variables
    if update.variables and update.variables.upsert:
        apply_variable_upserts(flow_data, update.variables.upsert)

    # 5. Delete Nodes
    if update.nodes and update.nodes.delete:
        apply_node_deletions(flow_data, update.nodes.delete)

    # 6. Upsert Nodes
    if update.nodes and update.nodes.upsert:
        apply_node_upserts(flow_data, update.nodes.upsert)

    # 7. Set Start Target
    apply_start_target(flow_data, update.start_target)

    return flow_data
