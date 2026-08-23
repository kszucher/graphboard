from __future__ import annotations

import json
from pathlib import Path

from app.modules.graphs.schemas import GraphFlowData


def build_default_trivia_graph_flow_data() -> GraphFlowData:
    json_path = Path(__file__).parent / "default_trivia_graph.json"
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    return GraphFlowData.model_validate(data)
