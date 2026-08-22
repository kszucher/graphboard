from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import Field

from app.core.constants import NodeType

from .agentic_assigner import AgenticAssignerNode
from .agentic_switch import AgenticBranch, AgenticSwitchNode
from .base import BaseNode, _make_slot_id
from .end import EndNode
from .interrupt import InterruptNode
from .logical_assigner import LogicalAssignerNode, LogicalAssignmentSchema
from .logical_switch import Branch, LogicalSwitchNode
from .rag_retriever import RagRetrieverNode
from .start import StartNode

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

__all__ = [
    "_make_slot_id",
    "BaseNode",
    "StartNode",
    "EndNode",
    "LogicalAssignmentSchema",
    "LogicalAssignerNode",
    "AgenticAssignerNode",
    "Branch",
    "AgenticBranch",
    "LogicalSwitchNode",
    "AgenticSwitchNode",
    "InterruptNode",
    "RagRetrieverNode",
    "NodeRead",
    "NODE_CLASS_MAP",
]
