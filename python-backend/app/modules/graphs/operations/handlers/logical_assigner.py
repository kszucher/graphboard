from __future__ import annotations

from app.core.exceptions import ValidationError
from app.modules.graphs.expressions import get_expression_variables
from app.modules.graphs.nodes import BaseNode, LogicalAssignerNode, LogicalAssignmentSchema
from app.modules.graphs.operations.schemas import NodeUpsertInput
from app.modules.graphs.schemas import ExpressionRecord, GraphFlowData


class LogicalAssignerHandler:
    def apply(
        self,
        node: BaseNode,
        u_node: NodeUpsertInput,
        flow_data: GraphFlowData,
        valid_keys: set[str],
    ) -> None:
        if not isinstance(node, LogicalAssignerNode):
            raise ValidationError(f"Node '{u_node.id}' is not an instance of LogicalAssignerNode.")

        if u_node.assignments is None:
            raise ValidationError(f"Node '{u_node.id}' of type LOGICAL_ASSIGNER must specify 'assignments'.")

        assignments = []
        for a in u_node.assignments:
            if a.target_var_key not in valid_keys:
                raise ValidationError(f"Variable '{a.target_var_key}' is not defined in the graph state.")

            referenced = get_expression_variables(a.expression)
            for ref in referenced:
                if ref not in valid_keys:
                    raise ValidationError(
                        f"Variable '{ref}' referenced in expression is not defined in the graph state."
                    )

            expr_id = f"expr_{u_node.id}_{a.target_var_key}"
            flow_data.expressions[expr_id] = ExpressionRecord(id=expr_id, expr=a.expression)
            assignments.append(LogicalAssignmentSchema(target_var_key=a.target_var_key, expr_id=expr_id))

        node.assignments = assignments
