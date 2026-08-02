from __future__ import annotations

import copy
import uuid

from app.constants import NodeType
from app.graphs.canonical import (
    CanonicalComputation,
    CanonicalNode,
    CanonicalRetry,
    CanonicalRouter,
    CanonicalSentinel,
    ComputationKind,
    ConditionalEdgeAssembly,
    ResolvedGraph,
    RouterKind,
    SentinelKind,
)
from app.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    ConfirmNode,
    DefinerVariableSchema,
    EdgeRead,
    ExtractNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    RetryNode,
    ReviewNode,
    SlotRead,
    SwitchNode,
    ValidateNode,
)


class SemanticResolver:
    """Layer 1 Compiler: Maps semantic user nodes to canonical execution forms.

    Guarantees:
      - Exhaustive match over all 12 NodeTypes (raises ValueError on unhandled type).
      - Expands composite primitives (CONFIRM -> Interrupt + Router).
      - Injects synthetic state variables (__retry_{id}_count) for RETRY.
    """

    def resolve(self, flow_data: GraphFlowData) -> ResolvedGraph:
        canonical_nodes: list[CanonicalNode] = []
        canonical_edges: list[EdgeRead] = copy.deepcopy(flow_data.edges)
        canonical_state: list[DefinerVariableSchema] = copy.deepcopy(flow_data.state)

        for node in flow_data.nodes:
            match node.node_type:
                case NodeType.START:
                    canonical_nodes.append(CanonicalSentinel(id=node.id, kind=SentinelKind.START))
                case NodeType.END:
                    canonical_nodes.append(CanonicalSentinel(id=node.id, kind=SentinelKind.END))
                case NodeType.LOGICAL_ASSIGNER:
                    assert isinstance(node, LogicalAssignerNode)
                    canonical_nodes.append(
                        CanonicalComputation(
                            id=node.id,
                            body=ComputationKind.LOGICAL,
                            assignments=copy.deepcopy(node.assignments),
                        )
                    )
                case NodeType.EXTRACT | NodeType.VALIDATE:
                    assert isinstance(node, (ExtractNode, ValidateNode))
                    canonical_nodes.append(
                        CanonicalComputation(
                            id=node.id,
                            body=ComputationKind.LOGICAL,
                            assignments=copy.deepcopy(node.assignments),
                        )
                    )
                case NodeType.REVIEW:
                    assert isinstance(node, ReviewNode)
                    canonical_nodes.append(
                        CanonicalComputation(
                            id=node.id,
                            body=ComputationKind.PASSTHROUGH,
                        )
                    )
                case NodeType.AGENTIC_ASSIGNER:
                    assert isinstance(node, AgenticAssignerNode)
                    canonical_nodes.append(
                        CanonicalComputation(
                            id=node.id,
                            body=ComputationKind.AGENTIC,
                            prompt=node.prompt,
                            agentic_inputs=list(node.agentic_inputs),
                            agentic_outputs=list(node.agentic_outputs),
                        )
                    )
                case NodeType.INTERRUPT:
                    assert isinstance(node, InterruptNode)
                    canonical_nodes.append(
                        CanonicalComputation(
                            id=node.id,
                            body=ComputationKind.INTERRUPT,
                            payload_vars=list(node.payload_vars),
                            resume_var=node.resume_var,
                        )
                    )
                case NodeType.CONFIRM:
                    assert isinstance(node, ConfirmNode)
                    # Expand CONFIRM into an Interrupt node + an expression Router node
                    clean_id = node.id[8:] if node.id.startswith("confirm_") else node.id
                    var_key = f"__confirm_{clean_id}_decision"
                    canonical_nodes.append(
                        CanonicalComputation(
                            id=node.id,
                            body=ComputationKind.INTERRUPT,
                            payload_vars=list(node.payload_vars),
                            resume_var=var_key,
                        )
                    )
                    # Inject confirm decision var into state schema if missing
                    if not any(v.key == var_key for v in canonical_state):
                        canonical_state.append(
                            DefinerVariableSchema(
                                id=str(uuid.uuid4()),
                                key=var_key,
                                type="string",
                                default_value="",
                                description="Synthetic decision var for confirm node",
                            )
                        )
                    # 2. Router part
                    route_node_id = f"__{node.id}_route"
                    router_slots = [
                        SlotRead(
                            id=f"{node.id}_confirmed",
                            raw_string="confirmed",
                            expression={
                                "kind": "binaryOp",
                                "op": "==",
                                "left": {"kind": "stateRef", "varKey": var_key},
                                "right": {"kind": "literal", "value": "confirmed"},
                            },
                        ),
                        SlotRead(
                            id=f"{node.id}_rejected",
                            raw_string="rejected",
                            expression={
                                "kind": "binaryOp",
                                "op": "==",
                                "left": {"kind": "stateRef", "varKey": var_key},
                                "right": {"kind": "literal", "value": "rejected"},
                            },
                        ),
                        SlotRead(
                            id=f"{node.id}_unclear",
                            raw_string="unclear",
                            expression={"kind": "literal", "value": True},
                        ),
                    ]
                    canonical_nodes.append(
                        CanonicalRouter(
                            id=route_node_id,
                            body=RouterKind.LOGICAL_SWITCH,
                            slots=router_slots,
                        )
                    )
                case NodeType.SWITCH:
                    assert isinstance(node, SwitchNode)
                    canonical_nodes.append(
                        CanonicalRouter(
                            id=node.id,
                            body=RouterKind.LOGICAL_SWITCH,
                            slots=copy.deepcopy(node.slots),
                        )
                    )
                case NodeType.AGENTIC_SWITCH:
                    assert isinstance(node, AgenticSwitchNode)
                    canonical_nodes.append(
                        CanonicalRouter(
                            id=node.id,
                            body=RouterKind.AGENTIC_SWITCH,
                            slots=copy.deepcopy(node.slots),
                            prompt=node.prompt,
                            agentic_inputs=list(node.agentic_inputs),
                        )
                    )
                case NodeType.RETRY:
                    assert isinstance(node, RetryNode)
                    counter_var_key = f"__retry_{node.id}_count"
                    if not any(v.key == counter_var_key for v in canonical_state):
                        canonical_state.append(
                            DefinerVariableSchema(
                                id=str(uuid.uuid4()),
                                key=counter_var_key,
                                type="number",
                                default_value=0,
                                description=f"Retry counter for node {node.id}",
                            )
                        )
                    inc_node_id = f"__{node.id}_inc"
                    # 1. Pure increment computation node
                    canonical_nodes.append(
                        CanonicalComputation(
                            id=inc_node_id,
                            body=ComputationKind.LOGICAL,
                            assignments=[
                                LogicalAssignmentSchema(
                                    id=str(uuid.uuid4()),
                                    target_var_key=counter_var_key,
                                    value_type="number",
                                    expression={
                                        "kind": "binaryOp",
                                        "op": "+",
                                        "left": {"kind": "stateRef", "varKey": counter_var_key},
                                        "right": {"kind": "literal", "value": 1},
                                    },
                                )
                            ],
                        )
                    )
                    # 2. Pure router condition node
                    canonical_nodes.append(
                        CanonicalRetry(
                            id=node.id,
                            max_attempts=node.max_attempts,
                            valid_expression=copy.deepcopy(node.valid_expression),
                            slots=copy.deepcopy(node.slots),
                        )
                    )
                    # 3. Remap outgoing edge for 'retry' slot to go through inc_node_id
                    retry_slot = next((s for s in node.slots if s.raw_string == "retry"), None)
                    if retry_slot:
                        for edge in canonical_edges:
                            if edge.source_id == retry_slot.id:
                                # Rewire: retry_slot -> inc_node_id -> original target
                                original_target = edge.target_id
                                edge.target_id = inc_node_id
                                edge.target_type = "node"
                                canonical_edges.append(
                                    EdgeRead(
                                        id=uuid.uuid4(),
                                        source_id=inc_node_id,
                                        source_type="node",
                                        target_id=original_target,
                                        target_type="node",
                                    )
                                )
                case _:
                    raise ValueError(f"Unhandled NodeType in SemanticResolver: {node.node_type}")

        # Pre-assemble direct and conditional graph edges in Layer 1
        executable_nodes = [n for n in canonical_nodes if not isinstance(n, CanonicalSentinel)]
        router_nodes = {n.id: n for n in executable_nodes if isinstance(n, (CanonicalRouter, CanonicalRetry))}

        all_slot_ids: set[str] = set()
        for r in router_nodes.values():
            for s in r.slots:
                all_slot_ids.add(s.id)

        def resolve_target(tid: str) -> str:
            if tid == "start":
                return "START"
            if tid == "end":
                return "END"
            for n in executable_nodes:
                if isinstance(n, (CanonicalRouter, CanonicalRetry)):
                    if any(s.id == tid for s in n.slots):
                        return n.id
            return tid

        slot_targets: dict[str, str] = {}
        for e in canonical_edges:
            if e.source_type == "slot" or e.source_id in all_slot_ids:
                slot_targets[e.source_id] = resolve_target(e.target_id)

        direct_edges: list[tuple[str, str]] = []
        edges_to_routers: set[uuid.UUID] = set()
        router_sources: dict[str, list[str]] = {sid: [] for sid in router_nodes}

        for e in canonical_edges:
            target_node = next((rn for rn in executable_nodes if rn.id == e.target_id), None)
            if isinstance(target_node, (CanonicalRouter, CanonicalRetry)):
                edges_to_routers.add(e.id)
                resolved_src = resolve_target(e.source_id)
                router_sources[target_node.id].append(resolved_src)

        for e in canonical_edges:
            if (
                e.id in edges_to_routers
                or e.source_type == "slot"
                or e.source_id in all_slot_ids
                or e.target_id == "start"
            ):
                continue
            src = "START" if e.source_id == "start" else e.source_id
            tgt = resolve_target(e.target_id)
            direct_edges.append((src, tgt))

        conditional_edges: list[ConditionalEdgeAssembly] = []
        for r_id, router in router_nodes.items():
            slot_map: dict[str, str] = {}
            for s in router.slots:
                if s.id in slot_targets:
                    slot_map[s.raw_string] = slot_targets[s.id]

            if not slot_map:
                continue

            router_fn_name = r_id
            if isinstance(router, CanonicalRouter) and router.body == RouterKind.AGENTIC_SWITCH:
                sources = [r_id]
                router_fn_name = f"__{r_id}_route"
            elif r_id.startswith("__") and r_id.endswith("_route"):
                parent_id = r_id[2:-6]
                sources = [parent_id]
                router_fn_name = r_id
            else:
                raw_srcs = router_sources[r_id]
                if not raw_srcs:
                    sources = [r_id]
                else:
                    sources = []
                    for src in raw_srcs:
                        if src in router_nodes and not any(n.id == src for n in executable_nodes):
                            sources.append(r_id)
                        elif src.startswith("__") and src.endswith("_route"):
                            sources.append(r_id)
                        else:
                            sources.append(src)

            final_sources = [s[2:-6] if (s.startswith("__") and s.endswith("_route")) else s for s in sources]
            for source_node_id in final_sources:
                conditional_edges.append(
                    ConditionalEdgeAssembly(
                        source_node_id=source_node_id,
                        router_fn_name=router_fn_name,
                        slot_mapping=slot_map,
                    )
                )

        return ResolvedGraph(
            nodes=canonical_nodes,
            edges=canonical_edges,
            state=canonical_state,
            direct_edges=direct_edges,
            conditional_edges=conditional_edges,
        )
