from __future__ import annotations

from typing import Any

from app.graphs.schemas import (
    ConnectOp,
    DeleteNodeOp,
    DeleteStateVarOp,
    DisconnectOp,
    GraphOperation,
    UpsertAgenticAssignerOp,
    UpsertAgenticSwitchOp,
    UpsertInterruptOp,
    UpsertLogicalAssignerOp,
    UpsertLogicalSwitchOp,
    UpsertRagRetrieverOp,
    UpsertStateVarOp,
)

ALL_FLAT_TOOLS = {
    "upsert_logical_assigner": {
        "type": "function",
        "function": {
            "name": "upsert_logical_assigner",
            "description": "Add or update a logical assigner node with deterministic inline variable assignments.",
            "parameters": UpsertLogicalAssignerOp.model_json_schema(),
        },
    },
    "upsert_agentic_assigner": {
        "type": "function",
        "function": {
            "name": "upsert_agentic_assigner",
            "description": "Add or update an agentic assigner node that invokes LLMs for structured state mutations.",
            "parameters": UpsertAgenticAssignerOp.model_json_schema(),
        },
    },
    "upsert_logical_switch": {
        "type": "function",
        "function": {
            "name": "upsert_logical_switch",
            "description": "Add or update a logical switch node to evaluate deterministic expression branching logic.",
            "parameters": UpsertLogicalSwitchOp.model_json_schema(),
        },
    },
    "upsert_agentic_switch": {
        "type": "function",
        "function": {
            "name": "upsert_agentic_switch",
            "description": "Add or update an agentic switch node for LLM-driven decision routing across options.",
            "parameters": UpsertAgenticSwitchOp.model_json_schema(),
        },
    },
    "upsert_interrupt": {
        "type": "function",
        "function": {
            "name": "upsert_interrupt",
            "description": "Add or update an interrupt node to pause workflow execution for user payloads.",
            "parameters": UpsertInterruptOp.model_json_schema(),
        },
    },
    "upsert_rag_retriever": {
        "type": "function",
        "function": {
            "name": "upsert_rag_retriever",
            "description": "Add or update a RAG node that queries a Neon Postgres vector index using Hugging Face embeddings.",
            "parameters": UpsertRagRetrieverOp.model_json_schema(),
        },
    },
    "delete_node": {
        "type": "function",
        "function": {
            "name": "delete_node",
            "description": "Delete a node and all of its incoming/outgoing connections.",
            "parameters": DeleteNodeOp.model_json_schema(),
        },
    },
    "connect": {
        "type": "function",
        "function": {
            "name": "connect",
            "description": "Draw a connection edge from a source node/branch to a target node. Automatically registers branches on Switch nodes if a case label is provided.",
            "parameters": ConnectOp.model_json_schema(),
        },
    },
    "disconnect": {
        "type": "function",
        "function": {
            "name": "disconnect",
            "description": "Remove a connection edge between a source node/handle and target node/handle.",
            "parameters": DisconnectOp.model_json_schema(),
        },
    },
    "upsert_state_var": {
        "type": "function",
        "function": {
            "name": "upsert_state_var",
            "description": "Declare or update a global state variable key, type, and default value.",
            "parameters": UpsertStateVarOp.model_json_schema(),
        },
    },
    "delete_state_var": {
        "type": "function",
        "function": {
            "name": "delete_state_var",
            "description": "Delete a global state variable.",
            "parameters": DeleteStateVarOp.model_json_schema(),
        },
    },
}


def translate_tool_calls_to_operations(tool_calls: list[Any]) -> list[GraphOperation]:
    """Translates raw LLM tool call dictionaries to GraphOperation instances."""
    from pydantic import TypeAdapter

    ops: list[GraphOperation] = []
    for tc in tool_calls:
        func_name = tc.function.name
        args_str = tc.function.arguments

        import json

        try:
            args = json.loads(args_str)
        except Exception:
            args = {}

        args["op"] = func_name
        ops.append(TypeAdapter(GraphOperation).validate_python(args))
    return ops
