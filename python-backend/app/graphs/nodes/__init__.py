from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import Field

from app.constants import NodeType

from .agentic_assigner import AgenticAssignerConfig, AgenticAssignerNode
from .agentic_switch import AgenticSwitchConfig, AgenticSwitchNode
from .base import BaseNode, _make_slot_id
from .end import EndConfig, EndNode
from .interrupt import InterruptConfig, InterruptNode
from .logical_assigner import LogicalAssignerConfig, LogicalAssignerNode, LogicalAssignmentSchema
from .logical_switch import Branch, LogicalSwitchConfig, LogicalSwitchNode
from .rag_retriever import RagRetrieverConfig, RagRetrieverNode
from .start import StartConfig, StartNode

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

__all__ = [
    "_make_slot_id",
    "BaseNode",
    "StartNode",
    "StartConfig",
    "EndNode",
    "EndConfig",
    "LogicalAssignmentSchema",
    "LogicalAssignerNode",
    "LogicalAssignerConfig",
    "AgenticAssignerNode",
    "AgenticAssignerConfig",
    "Branch",
    "LogicalSwitchNode",
    "LogicalSwitchConfig",
    "AgenticSwitchNode",
    "AgenticSwitchConfig",
    "InterruptNode",
    "InterruptConfig",
    "RagRetrieverNode",
    "RagRetrieverConfig",
    "NodeRead",
    "NodeConfig",
    "NODE_CLASS_MAP",
]
