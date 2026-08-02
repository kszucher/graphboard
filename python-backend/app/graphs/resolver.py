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
    RetryNode,
    ReviewNode,
    SlotRead,
    StartNode,
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
                    # 1. Interrupt part
                    canonical_nodes.append(
                        CanonicalComputation(
                            id=node.id,
                            body=ComputationKind.INTERRUPT,
                            payload_vars=list(node.payload_vars),
                            resume_var=f"__confirm_{node.id}_decision",
                        )
                    )
                    # Inject confirm decision var into state schema if missing
                    var_key = f"__confirm_{node.id}_decision"
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
                    # Edge connecting interrupt -> router
                    canonical_edges.append(
                        EdgeRead(
                            id=uuid.uuid4(),
                            source_id=node.id,
                            target_id=route_node_id,
                            source_type="node",
                            target_type="node",
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
                    canonical_nodes.append(
                        CanonicalRetry(
                            id=node.id,
                            max_attempts=node.max_attempts,
                            valid_expression=copy.deepcopy(node.valid_expression),
                            slots=copy.deepcopy(node.slots),
                        )
                    )
                case _:
                    raise ValueError(f"Unhandled NodeType in SemanticResolver: {node.node_type}")

        return ResolvedGraph(
            nodes=canonical_nodes,
            edges=canonical_edges,
            state=canonical_state,
        )
