from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from app.graphs.schemas import DefinerVariableSchema, EdgeRead, LogicalAssignmentSchema, SlotRead


class SentinelKind(str, Enum):
    START = "START"
    END = "END"


class ComputationKind(str, Enum):
    LOGICAL = "logical"
    AGENTIC = "agentic"
    INTERRUPT = "interrupt"
    PASSTHROUGH = "passthrough"


class RouterKind(str, Enum):
    LOGICAL_SWITCH = "logical_switch"
    AGENTIC_SWITCH = "agentic_switch"


class CanonicalNode(BaseModel):
    id: str


class CanonicalSentinel(CanonicalNode):
    kind: SentinelKind


class CanonicalComputation(CanonicalNode):
    body: ComputationKind
    assignments: list[LogicalAssignmentSchema] = Field(default_factory=list)
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)
    agentic_outputs: list[str] = Field(default_factory=list)
    payload_vars: list[str] = Field(default_factory=list)
    resume_var: str = ""


class CanonicalRouter(CanonicalNode):
    body: RouterKind
    slots: list[SlotRead] = Field(default_factory=list)
    prompt: str = ""
    agentic_inputs: list[str] = Field(default_factory=list)


class CanonicalRetry(CanonicalNode):
    max_attempts: int = 3
    valid_expression: dict[str, Any] | None = None
    slots: list[SlotRead] = Field(default_factory=list)


class ResolvedGraph(BaseModel):
    nodes: list[CanonicalNode] = Field(default_factory=list)
    edges: list[EdgeRead] = Field(default_factory=list)
    state: list[DefinerVariableSchema] = Field(default_factory=list)
