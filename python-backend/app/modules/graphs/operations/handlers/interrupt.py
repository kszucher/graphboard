from __future__ import annotations

from app.core.exceptions import ValidationError
from app.modules.graphs.nodes import BaseNode, InterruptNode
from app.modules.graphs.operations.schemas import NodeUpsertInput
from app.modules.graphs.schemas import GraphFlowData


class InterruptHandler:
    def apply(
        self,
        node: BaseNode,
        u_node: NodeUpsertInput,
        flow_data: GraphFlowData,
        valid_keys: set[str],
    ) -> None:
        if not isinstance(node, InterruptNode):
            raise ValidationError(f"Node '{u_node.id}' is not an instance of InterruptNode.")

        if u_node.resume_var not in valid_keys:
            raise ValidationError(f"Resume variable '{u_node.resume_var}' is not defined in graph state.")
        node.resume_var = u_node.resume_var

        if u_node.payload_vars is not None:
            for pv in u_node.payload_vars:
                if pv not in valid_keys:
                    raise ValidationError(f"Payload variable '{pv}' is not defined in graph state.")
            node.payload_vars = u_node.payload_vars
