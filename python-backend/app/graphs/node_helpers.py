from __future__ import annotations

from app.graphs.expressions import get_expression_variables, rename_expression_variables
from app.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    NodeRead,
)


def get_node_variable_references(node: NodeRead) -> set[str]:
    """Returns a set of state variable keys referenced by the given node."""
    refs: set[str] = set()

    if isinstance(node, LogicalAssignerNode):
        for asgn in node.assignments:
            if asgn.target_var_key:
                refs.add(asgn.target_var_key)
            if asgn.expression:
                refs.update(get_expression_variables(asgn.expression))

    elif isinstance(node, LogicalSwitchNode):
        for slot in node.slots:
            if slot.expression:
                refs.update(get_expression_variables(slot.expression))

    elif isinstance(node, AgenticAssignerNode):
        if node.agentic_inputs:
            refs.update(node.agentic_inputs)
        if node.agentic_outputs:
            refs.update(node.agentic_outputs)

    elif isinstance(node, AgenticSwitchNode):
        if node.agentic_input:
            refs.add(node.agentic_input)

    elif isinstance(node, InterruptNode):
        if node.payload_vars:
            refs.update(node.payload_vars)
        if node.resume_var:
            refs.add(node.resume_var)

    return refs


def rename_node_variable_references(node: NodeRead, old_key: str, new_key: str) -> None:
    """Updates variable reference keys in-place within the node when a variable is renamed."""
    if isinstance(node, LogicalAssignerNode):
        for asgn in node.assignments:
            if asgn.target_var_key == old_key:
                asgn.target_var_key = new_key
            if asgn.expression:
                rename_expression_variables(asgn.expression, old_key, new_key)

    elif isinstance(node, LogicalSwitchNode):
        for slot in node.slots:
            if slot.expression:
                rename_expression_variables(slot.expression, old_key, new_key)

    elif isinstance(node, AgenticAssignerNode):
        if node.agentic_inputs:
            node.agentic_inputs = [new_key if k == old_key else k for k in node.agentic_inputs]
        if node.agentic_outputs:
            node.agentic_outputs = [new_key if k == old_key else k for k in node.agentic_outputs]
        if node.prompt:
            node.prompt = node.prompt.replace(f"{{{old_key}}}", f"{{{new_key}}}")

    elif isinstance(node, AgenticSwitchNode):
        if node.agentic_input == old_key:
            node.agentic_input = new_key

    elif isinstance(node, InterruptNode):
        if node.payload_vars:
            node.payload_vars = [new_key if k == old_key else k for k in node.payload_vars]
        if node.resume_var == old_key:
            node.resume_var = new_key
