from __future__ import annotations

from app.core.exceptions import ValidationError
from app.modules.graphs.nodes import BaseNode, RagRetrieverNode
from app.modules.graphs.operations.schemas import NodeUpsertInput
from app.modules.graphs.schemas import GraphFlowData


class RagRetrieverHandler:
    def apply(
        self,
        node: BaseNode,
        u_node: NodeUpsertInput,
        flow_data: GraphFlowData,
        valid_keys: set[str],
    ) -> None:
        if not isinstance(node, RagRetrieverNode):
            raise ValidationError(f"Node '{u_node.id}' is not an instance of RagRetrieverNode.")

        if u_node.query_var not in valid_keys:
            raise ValidationError(f"Query variable '{u_node.query_var}' is not defined in graph state.")
        if u_node.context_output_var not in valid_keys:
            raise ValidationError(
                f"Context output variable '{u_node.context_output_var}' is not defined in graph state."
            )
        node.query_var = u_node.query_var
        node.context_output_var = u_node.context_output_var
        if u_node.knowledge_base is not None:
            node.knowledge_base = u_node.knowledge_base
        if u_node.top_k is not None:
            node.top_k = u_node.top_k
