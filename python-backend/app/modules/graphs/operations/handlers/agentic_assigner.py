from __future__ import annotations

from app.core.exceptions import ValidationError
from app.modules.graphs.nodes import AgenticAssignerNode, BaseNode
from app.modules.graphs.operations.schemas import NodeUpsertInput
from app.modules.graphs.schemas import GraphFlowData


class AgenticAssignerHandler:
    def apply(
        self,
        node: BaseNode,
        u_node: NodeUpsertInput,
        flow_data: GraphFlowData,
        valid_keys: set[str],
    ) -> None:
        if not isinstance(node, AgenticAssignerNode):
            raise ValidationError(f"Node '{u_node.id}' is not an instance of AgenticAssignerNode.")

        if u_node.prompt is None:
            raise ValidationError(f"Node '{u_node.id}' of type AGENTIC_ASSIGNER must specify 'prompt'.")
        node.prompt = u_node.prompt

        if u_node.agentic_inputs is not None:
            for inp in u_node.agentic_inputs:
                if inp not in valid_keys:
                    raise ValidationError(f"Variable '{inp}' is not defined in graph state.")
            node.agentic_inputs = u_node.agentic_inputs

        if u_node.agentic_outputs is not None:
            outputs = []
            for out in u_node.agentic_outputs:
                if out.key not in valid_keys:
                    raise ValidationError(f"Output variable '{out.key}' is not defined in graph state.")
                outputs.append(out.key)
            node.agentic_outputs = outputs
