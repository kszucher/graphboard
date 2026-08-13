import pytest

from app.graphs.operations.pipeline import apply_patch, sort_operations_by_dependency
from app.graphs.schemas import GraphFlowData
from app.graphs.operations.topology_ops import CreateNodeOp
from app.graphs.operations.state_ops import DeclareVariableOp
from app.graphs.nodes import LogicalAssignerNode

def test_pipeline_basic() -> None:
    flow = GraphFlowData(nodes=[], edges=[], state=[])
    
    patch = [
        CreateNodeOp(op="create_node", node_id="assign_1", node_type="LOGICAL_ASSIGNER"),
        DeclareVariableOp(op="declare_variable", key="score", type="number", default_value=0),
    ]
    
    sorted_patch = sort_operations_by_dependency(patch)
    assert sorted_patch[0].op == "declare_variable"
    assert sorted_patch[1].op == "create_node"
    
    updated = apply_patch(flow, sorted_patch)
    
    assert len(updated.nodes) == 1
    assert isinstance(updated.nodes[0], LogicalAssignerNode)
    assert updated.nodes[0].id == "assign_1"
    
    assert len(updated.state) == 1
    assert updated.state[0].key == "score"
