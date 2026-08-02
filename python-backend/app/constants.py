from enum import Enum


class EventName(str, Enum):
    GRAPH_CREATED = "graph_created"
    GRAPH_UPDATED = "graph_updated"


class NodeType(str, Enum):
    START = "START"
    END = "END"
    SWITCH = "SWITCH"
    LOGICAL_ASSIGNER = "LOGICAL_ASSIGNER"
    AGENTIC_ASSIGNER = "AGENTIC_ASSIGNER"
    INTERRUPT = "INTERRUPT"
    AGENTIC_SWITCH = "AGENTIC_SWITCH"
    RETRY = "RETRY"
    EXTRACT = "EXTRACT"
    VALIDATE = "VALIDATE"
    REVIEW = "REVIEW"
    CONFIRM = "CONFIRM"
