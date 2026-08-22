from __future__ import annotations

import re
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.core.constants import NodeType
from app.modules.graphs.expressions import ComparisonExpression, Expression


def _make_slot_id(node_id: str, label: str) -> str:
    """Deterministically generate a branch handle ID from node_id and branch label."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "branch"
    return f"{node_id}_{slug}"


class BaseNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = ""

    def handle_node_rename(self, old_id: str, new_id: str) -> None:
        self.id = new_id

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        pass


class StartNode(BaseNode):
    node_type: Literal[NodeType.START] = NodeType.START


class EndNode(BaseNode):
    node_type: Literal[NodeType.END] = NodeType.END


class LogicalAssignmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_var_key: str
    expression: Expression | None = None


class LogicalAssignerNode(BaseNode):
    node_type: Literal[NodeType.LOGICAL_ASSIGNER] = NodeType.LOGICAL_ASSIGNER
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)


class Branch(BaseModel):
    """A routing branch on a logical switch node."""

    model_config = ConfigDict(extra="forbid")
    id: SkipJsonSchema[str] = ""
    label: str
    expression: ComparisonExpression | None = None


class LogicalSwitchNode(BaseNode):
    node_type: Literal[NodeType.LOGICAL_SWITCH] = NodeType.LOGICAL_SWITCH
    branches: list[Branch] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_branch_ids(self) -> LogicalSwitchNode:
        for branch in self.branches:
            branch.id = _make_slot_id(self.id, branch.label)
        return self

    def handle_node_rename(self, old_id: str, new_id: str) -> None:
        self.id = new_id
        for branch in self.branches:
            if branch.id.startswith(f"{old_id}_"):
                branch.id = branch.id.replace(f"{old_id}_", f"{new_id}_", 1)

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.core.exceptions import ValidationError

        for branch in self.branches:
            if (self.id, branch.id) not in edge_sources:
                raise ValidationError(
                    f"Logical Switch option '{branch.label}' on node '{self.id}' is not connected to any target node."
                )


class AgenticAssignerNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_ASSIGNER] = NodeType.AGENTIC_ASSIGNER
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.core.exceptions import ValidationError

        if not self.prompt or not self.prompt.strip():
            raise ValidationError(f"Agentic Node '{self.id}' has an empty prompt.")
        if not self.agentic_outputs:
            raise ValidationError(f"Agentic Node '{self.id}' must have at least one output variable.")


class AgenticBranch(BaseModel):
    """A routing branch on an agentic switch node."""

    model_config = ConfigDict(extra="forbid")
    id: SkipJsonSchema[str] = ""
    label: str


class AgenticSwitchNode(BaseNode):
    node_type: Literal[NodeType.AGENTIC_SWITCH] = NodeType.AGENTIC_SWITCH
    branches: list[AgenticBranch] = Field(default_factory=list)
    agentic_input: str = ""

    @model_validator(mode="after")
    def populate_branch_ids(self) -> AgenticSwitchNode:
        for branch in self.branches:
            branch.id = _make_slot_id(self.id, branch.label)
        return self

    def handle_node_rename(self, old_id: str, new_id: str) -> None:
        self.id = new_id
        for branch in self.branches:
            if branch.id.startswith(f"{old_id}_"):
                branch.id = branch.id.replace(f"{old_id}_", f"{new_id}_", 1)

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.core.exceptions import ValidationError

        for branch in self.branches:
            if (self.id, branch.id) not in edge_sources:
                raise ValidationError(
                    f"Agentic Switch option '{branch.label}' on node '{self.id}' is not connected to any target node."
                )


class InterruptNode(BaseNode):
    node_type: Literal[NodeType.INTERRUPT] = NodeType.INTERRUPT
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.core.exceptions import ValidationError

        if not self.resume_var:
            raise ValidationError(f"Interrupt node '{self.id}' must have a valid resume_var.")


class RagRetrieverNode(BaseNode):
    node_type: Literal[NodeType.RAG_RETRIEVER] = NodeType.RAG_RETRIEVER
    query_var: str = ""
    context_output_var: str = ""
    knowledge_base: str = "trivia"
    top_k: int = 3

    def validate_integrity(self, edge_sources: set[tuple[str, str]]) -> None:
        from app.core.exceptions import ValidationError

        if not self.query_var:
            raise ValidationError(f"RAG node '{self.id}' requires a query_var.")
        if not self.context_output_var:
            raise ValidationError(f"RAG node '{self.id}' requires a context_output_var.")


NodeRead = Annotated[
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

NODE_CLASS_MAP: dict[NodeType, type[BaseNode]] = {
    NodeType.START: StartNode,
    NodeType.END: EndNode,
    NodeType.LOGICAL_ASSIGNER: LogicalAssignerNode,
    NodeType.AGENTIC_ASSIGNER: AgenticAssignerNode,
    NodeType.INTERRUPT: InterruptNode,
    NodeType.LOGICAL_SWITCH: LogicalSwitchNode,
    NodeType.AGENTIC_SWITCH: AgenticSwitchNode,
    NodeType.RAG_RETRIEVER: RagRetrieverNode,
}
