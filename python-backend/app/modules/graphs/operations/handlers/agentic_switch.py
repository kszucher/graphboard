from __future__ import annotations

from app.core.exceptions import ValidationError
from app.modules.graphs.nodes import AgenticBranch, AgenticSwitchNode, BaseNode, _make_slot_id
from app.modules.graphs.operations.schemas import NodeUpsertInput
from app.modules.graphs.schemas import EdgeRead, GraphFlowData


class AgenticSwitchHandler:
    def apply(
        self,
        node: BaseNode,
        u_node: NodeUpsertInput,
        flow_data: GraphFlowData,
        valid_keys: set[str],
    ) -> None:
        if not isinstance(node, AgenticSwitchNode):
            raise ValidationError(f"Node '{u_node.id}' is not an instance of AgenticSwitchNode.")

        if u_node.branches is None:
            raise ValidationError(f"Node '{u_node.id}' of type AGENTIC_SWITCH must specify 'branches'.")

        if u_node.agentic_input is not None:
            if u_node.agentic_input not in valid_keys:
                raise ValidationError(
                    f"Agentic switch input variable '{u_node.agentic_input}' is not defined in graph state."
                )
            node.agentic_input = u_node.agentic_input
        elif not node.agentic_input:
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
                    flow_data.edges.append(EdgeRead(source=u_node.id, source_handle=branch_id, target=br.target))

        node.branches = agentic_branches
