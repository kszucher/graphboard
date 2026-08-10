from __future__ import annotations

import re
import uuid
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field

from app.constants import NodeType


def _make_slot_id(node_id: str, raw_string: str) -> str:
    """Deterministically generate a slot handle ID from node_id and raw_string label."""
    slug = re.sub(r"[^a-z0-9]+", "_", raw_string.lower()).strip("_") or "slot"
    return f"{node_id}_{slug}"


class BaseNode(BaseModel):
    id: str

    def get_variable_references(self) -> set[str]:
        from app.graphs.expressions import get_expression_variables

        refs: set[str] = set()
        # Scan fields dynamically
        for field in getattr(self, "_variable_fields", []):
            val = getattr(self, field, None)
            if isinstance(val, str) and val:
                refs.add(val)
            elif isinstance(val, list):
                refs.update(item for item in val if isinstance(item, str) and item)

        # Scan nested lists (assignments, slots)
        for field in ("assignments", "slots"):
            for item in getattr(self, field, []):
                t_var = getattr(item, "target_var_key", None)
                if t_var:
                    refs.add(t_var)
                expr = getattr(item, "expression", None)
                if expr:
                    refs.update(get_expression_variables(expr))
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        from app.graphs.expressions import rename_expression_variables

        # Rename in direct variable fields
        for field in getattr(self, "_variable_fields", []):
            val = getattr(self, field, None)
            if isinstance(val, str) and val == old_key:
                setattr(self, field, new_key)
            elif isinstance(val, list):
                setattr(self, field, [new_key if k == old_key else k for k in val])

        # Rename in nested lists
        for field in ("assignments", "slots"):
            for item in getattr(self, field, []):
                if getattr(item, "target_var_key", None) == old_key:
                    item.target_var_key = new_key
                expr = getattr(item, "expression", None)
                if expr:
                    item.expression = rename_expression_variables(expr, old_key, new_key)

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        pass


class StartNode(BaseNode):
    node_type: Literal[NodeType.START] = NodeType.START


class EndNode(BaseNode):
    node_type: Literal[NodeType.END] = NodeType.END


class LogicalAssignmentSchema(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_var_key: str
    expression: str | None = None


class LogicalAssignerNode(BaseNode):
    node_type: Literal[NodeType.LOGICAL_ASSIGNER] = NodeType.LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class AgenticAssignerNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_ASSIGNER] = NodeType.AGENTIC_ASSIGNER
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)

    _variable_fields = ["agentic_inputs", "agentic_outputs"]

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        super().rename_variable_references(old_key, new_key)
        if self.prompt:
            self.prompt = self.prompt.replace(f"{{{old_key}}}", f"{{{new_key}}}")

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        if not self.prompt or not self.prompt.strip():
            raise ValidationError(f"Node '{self.id}' has an empty prompt.")
        if not self.agentic_outputs:
            raise ValidationError(f"Agentic Assigner node '{self.id}' must have at least one output variable.")


class SlotRead(BaseModel):
    id: str = ""
    raw_string: str = ""
    expression: str | None = None
    target_var_key: str | None = None


class LogicalSwitchNode(BaseNode):
    node_type: Literal[NodeType.LOGICAL_SWITCH] = NodeType.LOGICAL_SWITCH
    slots: list[SlotRead] = Field(default_factory=list)

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        for slot in self.slots:
            if slot.expression is None:
                raise ValidationError(
                    f"Logical Switch node '{self.id}' has an unset condition on option '{slot.raw_string}'."
                )
            if (self.id, slot.id) not in edge_sources:
                raise ValidationError(
                    f"Logical Switch option '{slot.raw_string}' on node '{self.id}' is not connected to any target node."
                )


class InterruptNode(BaseNode):
    node_type: Literal[NodeType.INTERRUPT] = NodeType.INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""

    _variable_fields = ["payload_vars", "resume_var"]

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        if not self.resume_var:
            raise ValidationError(f"Interrupt node '{self.id}' must have a valid resume_var.")


class AgenticSlotRead(BaseModel):
    id: str = ""
    raw_string: str = ""


class AgenticSwitchNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_SWITCH] = NodeType.AGENTIC_SWITCH
    slots: list[AgenticSlotRead] = Field(default_factory=list)
    agentic_input: str = ""

    _variable_fields = ["agentic_input"]

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        for aslot in self.slots:
            if (self.id, aslot.id) not in edge_sources:
                raise ValidationError(
                    f"Agentic Switch option '{aslot.raw_string}' on node '{self.id}' is not connected to any target node."
                )


NodeRead: TypeAlias = Annotated[
    StartNode
    | EndNode
    | LogicalAssignerNode
    | AgenticAssignerNode
    | InterruptNode
    | LogicalSwitchNode
    | AgenticSwitchNode,
    Field(discriminator="node_type"),
]

NODE_CLASS_MAP: dict[NodeType, type[BaseNode]] = {
    NodeType.START: StartNode,
    NodeType.END: EndNode,
    NodeType.LOGICAL_ASSIGNER: LogicalAssignerNode,
    NodeType.AGENTIC_ASSIGNER: AgenticAssignerNode,
    NodeType.LOGICAL_SWITCH: LogicalSwitchNode,
    NodeType.AGENTIC_SWITCH: AgenticSwitchNode,
    NodeType.INTERRUPT: InterruptNode,
}
