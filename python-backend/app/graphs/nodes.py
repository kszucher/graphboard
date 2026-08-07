from __future__ import annotations

import re
import uuid
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, Field

from app.constants import NodeType


def _make_slot_id(node_id: str, raw_string: str) -> str:
    """Deterministically generate a slot handle ID from node_id and raw_string label."""
    slug = re.sub(r"[^a-z0-9]+", "_", raw_string.lower()).strip("_") or "slot"
    return f"{node_id}_{slug}"


class BaseNode(BaseModel):
    id: str

    def get_variable_references(self) -> set[str]:
        return set()

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        pass

    def apply_config(self, config: Any, state_variables: list[Any]) -> None:
        pass

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

    def get_variable_references(self) -> set[str]:
        from app.graphs.expressions import get_expression_variables

        refs = set()
        for asgn in self.assignments:
            if asgn.target_var_key:
                refs.add(asgn.target_var_key)
            if asgn.expression:
                refs.update(get_expression_variables(asgn.expression))
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        from app.graphs.expressions import rename_expression_variables

        for asgn in self.assignments:
            if asgn.target_var_key == old_key:
                asgn.target_var_key = new_key
            if asgn.expression:
                asgn.expression = rename_expression_variables(asgn.expression, old_key, new_key)

    def apply_config(self, config: Any, state_variables: list[Any]) -> None:
        from app.exceptions import ValidationError
        from app.graphs.expressions import get_expression_variables
        from app.graphs.mutations import validate_default_value_type
        from app.graphs.schemas import LogicalAssignerConfig

        if not isinstance(config, LogicalAssignerConfig):
            return

        valid_keys = {v.key for v in state_variables if v.key}
        parsed_assignments = []
        for a in config.assignments:
            import uuid

            a_id = a.id or str(uuid.uuid4())
            target_var = a.target_var_key.strip()
            expr = a.expression

            target_var_schema = next((v for v in state_variables if v.key == target_var), None)
            if not target_var_schema:
                raise ValidationError(f"Assignment target variable '{target_var}' is not defined in state schema.")

            if expr is not None:
                if not (get_expression_variables(expr) <= valid_keys):
                    raise ValidationError(f"Assignment expression for '{target_var}' references undefined variables.")
                if getattr(expr, "kind", None) == "literal":
                    validate_default_value_type(target_var_schema.type, getattr(expr, "value", None))

            parsed_assignments.append(
                LogicalAssignmentSchema(
                    id=a_id,
                    target_var_key=target_var,
                    expression=expr,
                )
            )
        self.assignments = parsed_assignments


class AgenticAssignerNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_ASSIGNER] = NodeType.AGENTIC_ASSIGNER
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)

    def get_variable_references(self) -> set[str]:
        refs = set()
        if self.agentic_inputs:
            refs.update(self.agentic_inputs)
        if self.agentic_outputs:
            refs.update(self.agentic_outputs)
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        if self.agentic_inputs:
            self.agentic_inputs = [new_key if k == old_key else k for k in self.agentic_inputs]
        if self.agentic_outputs:
            self.agentic_outputs = [new_key if k == old_key else k for k in self.agentic_outputs]
        if self.prompt:
            self.prompt = self.prompt.replace(f"{{{old_key}}}", f"{{{new_key}}}")

    def apply_config(self, config: Any, state_variables: list[Any]) -> None:
        from app.exceptions import ValidationError
        from app.graphs.schemas import AgenticAssignerConfig

        if not isinstance(config, AgenticAssignerConfig):
            return

        valid_keys = {v.key for v in state_variables if v.key}
        self.prompt = config.prompt

        for inp in config.agentic_inputs:
            if inp not in valid_keys:
                raise ValidationError(f"Agentic input '{inp}' is not defined in state schema.")
        self.agentic_inputs = config.agentic_inputs

        for outp in config.agentic_outputs:
            if outp not in valid_keys:
                raise ValidationError(f"Agentic output '{outp}' is not defined in state schema.")
        self.agentic_outputs = config.agentic_outputs

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

    def get_variable_references(self) -> set[str]:
        from app.graphs.expressions import get_expression_variables

        refs = set()
        for slot in self.slots:
            if slot.expression:
                refs.update(get_expression_variables(slot.expression))
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        from app.graphs.expressions import rename_expression_variables

        for slot in self.slots:
            if slot.expression:
                slot.expression = rename_expression_variables(slot.expression, old_key, new_key)

    def apply_config(self, config: Any, state_variables: list[Any]) -> None:
        from app.exceptions import ValidationError
        from app.graphs.expressions import get_expression_variables
        from app.graphs.schemas import LogicalSwitchConfig, SlotRead

        if not isinstance(config, LogicalSwitchConfig):
            return

        valid_keys = {v.key for v in state_variables if v.key}
        parsed_slots = []
        for s in config.slots:
            s_id = _make_slot_id(self.id, s.raw_string)
            raw_str = s.raw_string
            expr = s.expression
            target_var = s.target_var_key

            if expr is not None and not (get_expression_variables(expr) <= valid_keys):
                raise ValidationError(f"Switch slot '{raw_str}' expression references undefined variables.")

            parsed_slots.append(
                SlotRead(
                    id=s_id,
                    raw_string=raw_str,
                    expression=expr,
                    target_var_key=target_var,
                )
            )
        self.slots = parsed_slots

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

    def get_variable_references(self) -> set[str]:
        refs = set()
        if self.payload_vars:
            refs.update(self.payload_vars)
        if self.resume_var:
            refs.add(self.resume_var)
        return refs

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        if self.payload_vars:
            self.payload_vars = [new_key if k == old_key else k for k in self.payload_vars]
        if self.resume_var == old_key:
            self.resume_var = new_key

    def apply_config(self, config: Any, state_variables: list[Any]) -> None:
        from app.exceptions import ValidationError
        from app.graphs.schemas import InterruptConfig

        if not isinstance(config, InterruptConfig):
            return

        valid_keys = {v.key for v in state_variables if v.key}
        for pv in config.payload_vars:
            if pv not in valid_keys:
                raise ValidationError(f"Interrupt payload variable '{pv}' is not defined in state schema.")
        self.payload_vars = config.payload_vars

        r_var = config.resume_var
        if r_var and r_var not in valid_keys:
            raise ValidationError(f"Interrupt resume variable '{r_var}' is not defined in state schema.")
        self.resume_var = r_var

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

    def get_variable_references(self) -> set[str]:
        return {self.agentic_input} if self.agentic_input else set()

    def rename_variable_references(self, old_key: str, new_key: str) -> None:
        if self.agentic_input == old_key:
            self.agentic_input = new_key

    def apply_config(self, config: Any, state_variables: list[Any]) -> None:
        from app.exceptions import ValidationError
        from app.graphs.schemas import AgenticSlotRead, AgenticSwitchConfig

        if not isinstance(config, AgenticSwitchConfig):
            return

        valid_keys = {v.key for v in state_variables if v.key}
        parsed_agentic_slots = []
        for s_agentic in config.slots:
            s_id = _make_slot_id(self.id, s_agentic.raw_string)
            parsed_agentic_slots.append(
                AgenticSlotRead(
                    id=s_id,
                    raw_string=s_agentic.raw_string,
                )
            )
        self.slots = parsed_agentic_slots

        inp = config.agentic_input
        if inp and inp not in valid_keys:
            raise ValidationError(f"Agentic switch input '{inp}' is not defined in state schema.")
        self.agentic_input = inp

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
