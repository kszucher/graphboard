from __future__ import annotations

from app.core.constants import NodeType
from app.modules.graphs.operations.handlers.agentic_assigner import AgenticAssignerHandler
from app.modules.graphs.operations.handlers.agentic_switch import AgenticSwitchHandler
from app.modules.graphs.operations.handlers.base import BaseNodeHandler
from app.modules.graphs.operations.handlers.interrupt import InterruptHandler
from app.modules.graphs.operations.handlers.logical_assigner import LogicalAssignerHandler
from app.modules.graphs.operations.handlers.logical_switch import LogicalSwitchHandler
from app.modules.graphs.operations.handlers.rag_retriever import RagRetrieverHandler

NODE_HANDLERS: dict[NodeType, BaseNodeHandler] = {
    NodeType.LOGICAL_ASSIGNER: LogicalAssignerHandler(),
    NodeType.AGENTIC_ASSIGNER: AgenticAssignerHandler(),
    NodeType.LOGICAL_SWITCH: LogicalSwitchHandler(),
    NodeType.AGENTIC_SWITCH: AgenticSwitchHandler(),
    NodeType.INTERRUPT: InterruptHandler(),
    NodeType.RAG_RETRIEVER: RagRetrieverHandler(),
}

__all__ = [
    "AgenticAssignerHandler",
    "AgenticSwitchHandler",
    "BaseNodeHandler",
    "InterruptHandler",
    "LogicalAssignerHandler",
    "LogicalSwitchHandler",
    "NODE_HANDLERS",
    "RagRetrieverHandler",
]
