from __future__ import annotations

import re
import uuid
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.constants import NodeType


def _make_slot_id(node_id: str, label: str) -> str:
    """Deterministically generate a branch handle ID from node_id and branch label."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "branch"
    return f"{node_id}_{slug}"


class BaseNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = ""

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

        # Scan nested lists (assignments, branches)
        for field in ("assignments", "branches"):
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
        for field in ("assignments", "branches"):
            for item in getattr(self, field, []):
                if getattr(item, "target_var_key", None) == old_key:
                    item.target_var_key = new_key
                expr = getattr(item, "expression", None)
                if expr:
                    item.expression = rename_expression_variables(expr, old_key, new_key)

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        pass


class StartConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.START] = NodeType.START


class StartNode(BaseNode, StartConfig):
    pass


class EndConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.END] = NodeType.END


class EndNode(BaseNode, EndConfig):
    pass


class LogicalAssignmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_var_key: str
    expression: str | None = None


class LogicalAssignerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.LOGICAL_ASSIGNER] = NodeType.LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class LogicalAssignerNode(BaseNode, LogicalAssignerConfig):
    pass


class AgenticAssignerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.AGENTIC_ASSIGNER] = NodeType.AGENTIC_ASSIGNER
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)


class AgenticAssignerNode(BaseNode, AgenticAssignerConfig):
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


class Branch(BaseModel):
    """A routing branch on a switch node.

    Invariant: `label` retains the original human-readable casing (e.g. 'Submit').
    `id` is auto-generated from `label` via `_make_slot_id` and is not part of the
    JSON schema exposed to the LLM — do NOT set it manually.
    """

    model_config = ConfigDict(extra="forbid")
    id: SkipJsonSchema[str] = ""
    label: str  # required — the human-readable routing label
    expression: str | None = None  # LogicalSwitch condition (Python expression)
    target_var_key: str | None = None  # optional variable binding for integrity tracking


class LogicalSwitchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.LOGICAL_SWITCH] = NodeType.LOGICAL_SWITCH
    branches: list[Branch] = Field(default_factory=list)


class LogicalSwitchNode(BaseNode, LogicalSwitchConfig):
    @model_validator(mode="after")
    def populate_branch_ids(self) -> LogicalSwitchNode:
        for branch in self.branches:
            branch.id = _make_slot_id(self.id, branch.label)
        return self

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        for branch in self.branches:
            if branch.expression is None:
                raise ValidationError(
                    f"Logical Switch node '{self.id}' has an unset condition on option '{branch.label}'."
                )
            if (self.id, branch.id) not in edge_sources:
                raise ValidationError(
                    f"Logical Switch option '{branch.label}' on node '{self.id}' is not connected to any target node."
                )


class InterruptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.INTERRUPT] = NodeType.INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""


class InterruptNode(BaseNode, InterruptConfig):
    _variable_fields = ["payload_vars", "resume_var"]

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        if not self.resume_var:
            raise ValidationError(f"Interrupt node '{self.id}' must have a valid resume_var.")


class AgenticSwitchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.AGENTIC_SWITCH] = NodeType.AGENTIC_SWITCH
    branches: list[Branch] = Field(default_factory=list)
    agentic_input: str = ""


class AgenticSwitchNode(BaseNode, AgenticSwitchConfig):
    @model_validator(mode="after")
    def populate_branch_ids(self) -> AgenticSwitchNode:
        for branch in self.branches:
            branch.id = _make_slot_id(self.id, branch.label)
        return self

    _variable_fields = ["agentic_input"]

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        for branch in self.branches:
            if (self.id, branch.id) not in edge_sources:
                raise ValidationError(
                    f"Agentic Switch option '{branch.label}' on node '{self.id}' is not connected to any target node."
                )


class RagRetrieverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_type: Literal[NodeType.RAG_RETRIEVER] = NodeType.RAG_RETRIEVER
    query_var: str = ""
    context_output_var: str = ""
    knowledge_base: str = "trivia"
    top_k: int = 3


class RagRetrieverNode(BaseNode, RagRetrieverConfig):
    _variable_fields = ["query_var", "context_output_var"]

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.exceptions import ValidationError

        if not self.query_var:
            raise ValidationError(f"RAG node '{self.id}' requires a query_var.")
        if not self.context_output_var:
            raise ValidationError(f"RAG node '{self.id}' requires a context_output_var.")


NodeRead: TypeAlias = Annotated[
    StartNode
    | EndNode
    | LogicalAssignerNode
    | AgenticAssignerNode
    | InterruptNode
    | LogicalSwitchNode
    | AgenticSwitchNode
    | RagRetrieverNode,
    Field(discriminator="node_type"),
]

NodeConfig: TypeAlias = Annotated[
    StartConfig
    | EndConfig
    | LogicalAssignerConfig
    | AgenticAssignerConfig
    | InterruptConfig
    | LogicalSwitchConfig
    | AgenticSwitchConfig
    | RagRetrieverConfig,
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
    NodeType.RAG_RETRIEVER: RagRetrieverNode,
}
