from __future__ import annotations

from app.modules.graphs.expressions import get_expression_variables
from app.modules.graphs.nodes import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    NodeRead,
    RagRetrieverNode,
)


def get_node_variable_references(node: NodeRead) -> set[str]:
    refs: set[str] = set()
    match node:
        case LogicalAssignerNode():
            for a in node.assignments:
                if a.target_var_key:
                    refs.add(a.target_var_key)
                if a.expression is not None:
                    refs.update(get_expression_variables(a.expression))
        case LogicalSwitchNode():
            for b in node.branches:
                if b.target_var_key:
                    refs.add(b.target_var_key)
                if b.expression is not None:
                    refs.update(get_expression_variables(b.expression))
        case AgenticAssignerNode():
            if node.agentic_inputs:
                refs.update(node.agentic_inputs)
            if node.agentic_outputs:
                refs.update(node.agentic_outputs)
        case AgenticSwitchNode():
            if node.agentic_input:
                refs.add(node.agentic_input)
        case InterruptNode():
            if node.payload_vars:
                refs.update(node.payload_vars)
            if node.resume_var:
                refs.add(node.resume_var)
        case RagRetrieverNode():
            if node.query_var:
                refs.add(node.query_var)
            if node.context_output_var:
                refs.add(node.context_output_var)
    return refs


def rename_node_variable_references(node: NodeRead, old_key: str, new_key: str) -> None:
    match node:
        case LogicalAssignerNode():
            for a in node.assignments:
                if a.target_var_key == old_key:
                    a.target_var_key = new_key
        case LogicalSwitchNode():
            for b in node.branches:
                if b.target_var_key == old_key:
                    b.target_var_key = new_key
        case AgenticAssignerNode():
            if node.agentic_inputs:
                node.agentic_inputs = [new_key if x == old_key else x for x in node.agentic_inputs]
            if node.agentic_outputs:
                node.agentic_outputs = [new_key if x == old_key else x for x in node.agentic_outputs]
        case AgenticSwitchNode():
            if node.agentic_input == old_key:
                node.agentic_input = new_key
        case InterruptNode():
            if node.payload_vars:
                node.payload_vars = [new_key if x == old_key else x for x in node.payload_vars]
            if node.resume_var == old_key:
                node.resume_var = new_key
        case RagRetrieverNode():
            if node.query_var == old_key:
                node.query_var = new_key
            if node.context_output_var == old_key:
                node.context_output_var = new_key
