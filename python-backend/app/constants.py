from enum import Enum


class EventName(str, Enum):
    GRAPH_CREATED = "graph_created"
    GRAPH_UPDATED = "graph_updated"
    NODE_CREATED = "node_created"
    NODE_UPDATED = "node_updated"
    NODE_DELETED = "node_deleted"
    EDGE_CREATED = "edge_created"
    EDGE_DELETED = "edge_deleted"
    EDGES_UPDATED = "edges_updated"
    SLOT_CREATED = "slot_created"
    SLOT_UPDATED = "slot_updated"
    SLOT_DELETED = "slot_deleted"


class NodeType(str, Enum):
    START = "START"
    END = "END"
    STEP = "STEP"
    SWITCH = "SWITCH"
    DEFINER = "DEFINER"
    LOGICAL_ASSIGNER = "LOGICAL_ASSIGNER"
    AGENTIC_ASSIGNER = "AGENTIC_ASSIGNER"


class SlotType(str, Enum):
    BASE_INPUT = "BASE_INPUT"
    SUB_INPUT = "SUB_INPUT"
    SUB_UNCONNECTED = "SUB_UNCONNECTED"
    BASE_OUTPUT = "BASE_OUTPUT"
    SUB_OUTPUT = "SUB_OUTPUT"
    BASE_INPUT_OUTPUT = "BASE_INPUT_OUTPUT"
