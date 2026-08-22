from __future__ import annotations

from app.core.exceptions import ValidationError
from app.modules.graphs.expressions import get_expression_variables
from app.modules.graphs.nodes import BaseNode, Branch, LogicalSwitchNode, _make_slot_id
from app.modules.graphs.operations.schemas import NodeUpsertInput
from app.modules.graphs.schemas import EdgeRead, ExpressionRecord, GraphFlowData


class LogicalSwitchHandler:
    def apply(
        self,
        node: BaseNode,
        u_node: NodeUpsertInput,
        flow_data: GraphFlowData,
        valid_keys: set[str],
    ) -> None:
        if not isinstance(node, LogicalSwitchNode):
            raise ValidationError(f"Node '{u_node.id}' is not an instance of LogicalSwitchNode.")

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
                    flow_data.edges.append(EdgeRead(source=u_node.id, source_handle=branch_id, target=br.target))

        node.branches = logical_branches
