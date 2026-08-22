from __future__ import annotations

import uuid
from typing import Any, cast

from pydantic import BaseModel, Field

from app.core.constants import NodeType
from app.core.exceptions import ValidationError
from app.modules.graphs.expressions import get_expression_variables, rename_expression_variables
from app.modules.graphs.expressions.schemas import ComparisonExpression, Expression
from app.modules.graphs.nodes import NODE_CLASS_MAP, BaseNode, NodeRead, _make_slot_id
from app.modules.graphs.nodes.agentic_switch import AgenticBranch
from app.modules.graphs.nodes.logical_assigner import LogicalAssignmentSchema
from app.modules.graphs.nodes.logical_switch import Branch
from app.modules.graphs.schemas import DefinerVariableSchema, EdgeRead, ExpressionRecord, GraphFlowData, VariableType

# Snake-case identifier pattern: must start with a letter, only letters/digits/underscores.
_IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_]*$"


class AssignmentInput(BaseModel):
    target_var_key: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    expression: Expression


class BranchValueInput(BaseModel):
    expression: ComparisonExpression | None = None
    target: str | None = None


class AgenticOutputInput(BaseModel):
    key: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    type: VariableType


class VariableUpsertInput(BaseModel):
    key: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    type: VariableType
    default_value: Any = None
    description: str | None = None


class NodeUpsertInput(BaseModel):
    id: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    node_type: NodeType
    target: str | None = None

    # LOGICAL_ASSIGNER
    assignments: list[AssignmentInput] | None = None

    # AGENTIC_ASSIGNER
    agentic_inputs: list[str] | None = None
    agentic_outputs: list[AgenticOutputInput] | None = None
    prompt: str | None = None

    # LOGICAL_SWITCH / AGENTIC_SWITCH
    branches: dict[str, BranchValueInput] | None = Field(default=None, min_length=1)
    agentic_input: str | None = None

    # RAG_RETRIEVER
    query_var: str | None = None
    context_output_var: str | None = None
    knowledge_base: str | None = None
    top_k: int | None = None

    # INTERRUPT
    payload_vars: list[str] | None = None
    resume_var: str | None = None


class RenameInput(BaseModel):
    old_key: str
    new_key: str


class VariablesUpdate(BaseModel):
    upsert: list[VariableUpsertInput] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)


class NodesUpdate(BaseModel):
    upsert: list[NodeUpsertInput] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)


class GraphUpdateInput(BaseModel):
    start_target: str | None = None
    variables: VariablesUpdate | None = None
    nodes: NodesUpdate | None = None
    rename_nodes: list[RenameInput] | None = None
    rename_variables: list[RenameInput] | None = None


def apply_graph_update(flow_data: GraphFlowData, update: GraphUpdateInput) -> GraphFlowData:
    """Applies a Prisma-style declarative transaction update to the Graph Flow Data."""

    # 1. Rename Variables
    if update.rename_variables:
        for ru in update.rename_variables:
            var_schema = next((v for v in flow_data.state if v.key == ru.old_key), None)
            if not var_schema:
                raise ValidationError(f"Variable '{ru.old_key}' not found in graph state.")
            if any(v.key == ru.new_key for v in flow_data.state):
                raise ValidationError(f"Variable '{ru.new_key}' already exists.")

            var_schema.key = ru.new_key

            # Rename in expressions
            for record in flow_data.expressions.values():
                record.expr = rename_expression_variables(record.expr, ru.old_key, ru.new_key) or ""

            # Rename in nodes
            for n in flow_data.nodes:
                if hasattr(n, "assignments"):
                    for a in getattr(n, "assignments", []):
                        if a.target_var_key == ru.old_key:
                            a.target_var_key = ru.new_key
                if hasattr(n, "agentic_inputs"):
                    n.agentic_inputs = [ru.new_key if x == ru.old_key else x for x in getattr(n, "agentic_inputs", [])]
                if hasattr(n, "agentic_outputs"):
                    for out in getattr(n, "agentic_outputs", []):
                        if out.key == ru.old_key:
                            out.key = ru.new_key
                if hasattr(n, "query_var") and n.query_var == ru.old_key:
                    n.query_var = ru.new_key
                if hasattr(n, "context_output_var") and n.context_output_var == ru.old_key:
                    n.context_output_var = ru.new_key
                if hasattr(n, "agentic_input") and n.agentic_input == ru.old_key:
                    n.agentic_input = ru.new_key
                if hasattr(n, "payload_vars"):
                    n.payload_vars = [ru.new_key if x == ru.old_key else x for x in getattr(n, "payload_vars", [])]
                if hasattr(n, "resume_var") and n.resume_var == ru.old_key:
                    n.resume_var = ru.new_key

    # 2. Rename Nodes
    if update.rename_nodes:
        for rn in update.rename_nodes:
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

    # 3. Delete Variables
    if update.variables and update.variables.delete:
        for d_var in update.variables.delete:
            var_schema = next((v for v in flow_data.state if v.key == d_var), None)
            if not var_schema:
                raise ValidationError(f"Variable '{d_var}' not found in state.")
            flow_data.state.remove(var_schema)

    # 4. Upsert Variables
    if update.variables and update.variables.upsert:
        for u_var in update.variables.upsert:
            if not isinstance(u_var, VariableUpsertInput):
                u_var = VariableUpsertInput(**u_var)
            existing = next((v for v in flow_data.state if v.key == u_var.key), None)

            # Normalize type to standard frontend representations
            norm_type = u_var.type
            if norm_type in {"int", "integer"}:
                norm_type = "number"
            elif norm_type == "bool":
                norm_type = "boolean"

            if existing:
                existing.type = cast(VariableType, norm_type)
                existing.default_value = u_var.default_value
                existing.description = u_var.description
            else:
                flow_data.state.append(
                    DefinerVariableSchema(
                        id=str(uuid.uuid4()),
                        key=u_var.key,
                        type=cast(VariableType, norm_type),
                        default_value=u_var.default_value,
                        description=u_var.description,
                    )
                )

    # 5. Delete Nodes
    if update.nodes and update.nodes.delete:
        for d_node in update.nodes.delete:
            node = next((n for n in flow_data.nodes if n.id == d_node), None)
            if not node:
                raise ValidationError(f"Node '{d_node}' not found.")
            flow_data.nodes.remove(node)
            # Delete associated edges
            flow_data.edges = [e for e in flow_data.edges if e.source != d_node and e.target != d_node]

    # 6. Upsert Nodes
    if update.nodes and update.nodes.upsert:
        valid_keys = {v.key for v in flow_data.state}
        for u_node in update.nodes.upsert:
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

            # Configure specific node types
            if u_node.node_type == NodeType.LOGICAL_ASSIGNER:
                from app.modules.graphs.nodes import LogicalAssignerNode

                assert isinstance(upserted_node, LogicalAssignerNode)

                if u_node.assignments is None:
                    raise ValidationError(f"Node '{u_node.id}' of type LOGICAL_ASSIGNER must specify 'assignments'.")
                assignments = []
                for a in u_node.assignments:
                    if a.target_var_key not in valid_keys:
                        raise ValidationError(f"Variable '{a.target_var_key}' is not defined in the graph state.")

                    # Verify referenced variables in the expression exist
                    referenced = get_expression_variables(a.expression)
                    for ref in referenced:
                        if ref not in valid_keys:
                            raise ValidationError(
                                f"Variable '{ref}' referenced in expression is not defined in the graph state."
                            )

                    expr_id = f"expr_{u_node.id}_{a.target_var_key}"
                    flow_data.expressions[expr_id] = ExpressionRecord(id=expr_id, expr=a.expression)
                    assignments.append(LogicalAssignmentSchema(target_var_key=a.target_var_key, expr_id=expr_id))
                upserted_node.assignments = assignments

            elif u_node.node_type == NodeType.AGENTIC_ASSIGNER:
                from app.modules.graphs.nodes import AgenticAssignerNode

                assert isinstance(upserted_node, AgenticAssignerNode)

                if u_node.prompt is None:
                    raise ValidationError(f"Node '{u_node.id}' of type AGENTIC_ASSIGNER must specify 'prompt'.")
                upserted_node.prompt = u_node.prompt

                if u_node.agentic_inputs is not None:
                    for inp in u_node.agentic_inputs:
                        if inp not in valid_keys:
                            raise ValidationError(f"Variable '{inp}' is not defined in graph state.")
                    upserted_node.agentic_inputs = u_node.agentic_inputs

                if u_node.agentic_outputs is not None:
                    outputs = []
                    for out in u_node.agentic_outputs:
                        if out.key not in valid_keys:
                            raise ValidationError(f"Output variable '{out.key}' is not defined in graph state.")
                        outputs.append(out.key)
                    upserted_node.agentic_outputs = outputs

            elif u_node.node_type == NodeType.RAG_RETRIEVER:
                from app.modules.graphs.nodes import RagRetrieverNode

                assert isinstance(upserted_node, RagRetrieverNode)

                if u_node.query_var not in valid_keys:
                    raise ValidationError(f"Query variable '{u_node.query_var}' is not defined in graph state.")
                if u_node.context_output_var not in valid_keys:
                    raise ValidationError(
                        f"Context output variable '{u_node.context_output_var}' is not defined in graph state."
                    )
                upserted_node.query_var = u_node.query_var
                upserted_node.context_output_var = u_node.context_output_var
                if u_node.knowledge_base is not None:
                    upserted_node.knowledge_base = u_node.knowledge_base
                if u_node.top_k is not None:
                    upserted_node.top_k = u_node.top_k

            elif u_node.node_type == NodeType.LOGICAL_SWITCH:
                from app.modules.graphs.nodes import LogicalSwitchNode

                assert isinstance(upserted_node, LogicalSwitchNode)

                if u_node.branches is None:
                    raise ValidationError(f"Node '{u_node.id}' of type LOGICAL_SWITCH must specify 'branches'.")
                logical_branches = []
                for label, br in u_node.branches.items():
                    branch_id = _make_slot_id(u_node.id, label)
                    expr_id = f"expr_{u_node.id}_{branch_id}"

                    expr_val = br.expression if br.expression is not None else True

                    referenced = get_expression_variables(expr_val)
                    for ref in referenced:
                        if ref not in valid_keys:
                            raise ValidationError(
                                f"Variable '{ref}' referenced in branch expression is not defined in the graph state."
                            )

                    flow_data.expressions[expr_id] = ExpressionRecord(id=expr_id, expr=expr_val)
                    logical_branches.append(Branch(id=branch_id, label=label, expr_id=expr_id))

                    # Update branch target edge
                    if br.target is not None:
                        flow_data.edges = [
                            e for e in flow_data.edges if not (e.source == u_node.id and e.source_handle == branch_id)
                        ]
                        if br.target:
                            flow_data.edges.append(
                                EdgeRead(source=u_node.id, source_handle=branch_id, target=br.target)
                            )
                upserted_node.branches = logical_branches

            elif u_node.node_type == NodeType.AGENTIC_SWITCH:
                from app.modules.graphs.nodes import AgenticSwitchNode

                assert isinstance(upserted_node, AgenticSwitchNode)

                if u_node.branches is None:
                    raise ValidationError(f"Node '{u_node.id}' of type AGENTIC_SWITCH must specify 'branches'.")
                if u_node.agentic_input is not None:
                    if u_node.agentic_input not in valid_keys:
                        raise ValidationError(
                            f"Agentic switch input variable '{u_node.agentic_input}' is not defined in graph state."
                        )
                    upserted_node.agentic_input = u_node.agentic_input
                elif not upserted_node.agentic_input:
                    raise ValidationError(f"Node '{u_node.id}' of type AGENTIC_SWITCH must specify 'agentic_input'.")
                agentic_branches = []
                for label, br in u_node.branches.items():
                    branch_id = _make_slot_id(u_node.id, label)
                    agentic_branches.append(AgenticBranch(id=branch_id, label=label))

                    if br.target is not None:
                        flow_data.edges = [
                            e for e in flow_data.edges if not (e.source == u_node.id and e.source_handle == branch_id)
                        ]
                        if br.target:
                            flow_data.edges.append(
                                EdgeRead(source=u_node.id, source_handle=branch_id, target=br.target)
                            )
                upserted_node.branches = agentic_branches

            elif u_node.node_type == NodeType.INTERRUPT:
                from app.modules.graphs.nodes import InterruptNode

                assert isinstance(upserted_node, InterruptNode)

                if u_node.resume_var not in valid_keys:
                    raise ValidationError(f"Resume variable '{u_node.resume_var}' is not defined in graph state.")
                upserted_node.resume_var = u_node.resume_var
                if u_node.payload_vars is not None:
                    for pv in u_node.payload_vars:
                        if pv not in valid_keys:
                            raise ValidationError(f"Payload variable '{pv}' is not defined in graph state.")
                    upserted_node.payload_vars = u_node.payload_vars

    # 7. Set Start Target
    if update.start_target is not None:
        flow_data.edges = [e for e in flow_data.edges if e.source != "start"]
        if update.start_target:
            flow_data.edges.append(EdgeRead(source="start", target=update.start_target))

    # 8. Garbage Collect Expressions
    referenced_exprs = set()
    for n in flow_data.nodes:
        if hasattr(n, "assignments"):
            for a in getattr(n, "assignments", []):
                if a.expr_id:
                    referenced_exprs.add(a.expr_id)
        if hasattr(n, "branches"):
            for br in getattr(n, "branches", []):
                br_expr_id = getattr(br, "expr_id", None)
                if br_expr_id:
                    referenced_exprs.add(br_expr_id)

    flow_data.expressions = {k: v for k, v in flow_data.expressions.items() if k in referenced_exprs}

    return flow_data
