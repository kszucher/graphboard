from __future__ import annotations

import json
from pathlib import Path

from app.graphs.schemas import GraphFlowData


def build_default_trivia_graph_flow_data() -> GraphFlowData:
    json_path = Path(__file__).parent / "default_trivia_graph.json"
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    flow = GraphFlowData.model_validate(data)

    from app.graphs.schemas import ExpressionRecord
    from app.graphs.nodes import LogicalAssignerNode, LogicalSwitchNode

    # Dynamically seed flow.expressions from existing nodes to align with expressions store format
    for node in flow.nodes:
        if isinstance(node, LogicalAssignerNode):
            for a in node.assignments:
                if a.expression:
                    expr_id = f"expr_{node.id}_{a.target_var_key}"
                    flow.expressions[expr_id] = ExpressionRecord(id=expr_id, expr=a.expression)
        elif isinstance(node, LogicalSwitchNode):
            for b in node.branches:
                if b.expression:
                    expr_id = f"expr_{node.id}_{b.label.lower()}"
                    flow.expressions[expr_id] = ExpressionRecord(id=expr_id, expr=b.expression)

    return flow
