from enum import Enum


class EventName(str, Enum):
    GRAPH_CREATED = "graph_created"
    GRAPH_UPDATED = "graph_updated"


class NodeType(str, Enum):
    START = "START"
    END = "END"
    INTERRUPT = "INTERRUPT"
    LOGICAL_ASSIGNER = "LOGICAL_ASSIGNER"
    AGENTIC_ASSIGNER = "AGENTIC_ASSIGNER"
    LOGICAL_SWITCH = "LOGICAL_SWITCH"
    AGENTIC_SWITCH = "AGENTIC_SWITCH"
