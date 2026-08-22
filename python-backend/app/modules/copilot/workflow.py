from __future__ import annotations

import logging
import os
from typing import Any, Literal, cast

from google import genai
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.exceptions import ValidationError
from app.modules.copilot.agents.planner import generate_plan
from app.modules.copilot.logger import log_validation_error
from app.modules.copilot.models import CopilotState
from app.modules.graphs.operations import GraphUpdateInput, apply_graph_update
from app.modules.graphs.schemas import GraphFlowData

logger = logging.getLogger(__name__)


async def planner_node(state: CopilotState) -> dict[str, Any]:
    """Invokes the Planner LLM to generate the checklist of agent tasks."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValidationError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": f"## Current Graph State:\n{state['serialized_state']}\n\n## User Request:\n{state['user_prompt']}",
        },
    ]

    plan = await generate_plan(
        client,
        state["trace_id"],
        state.get("graph_id", ""),
        messages,
        initial_flow=state.get("initial_flow_data"),
    )
    checklist = {"tool_calls": plan}

    return {
        "agent_checklist": checklist,
        "operations": None,
        "plan": [],
    }


def _convert_condition_group(group: dict[str, Any] | None) -> dict[str, Any] | None:
    """Converts a closed-schema ConditionGroup dictionary into internal ComparisonExpression AST."""
    if not group:
        return None
    conditions = group.get("conditions", [])
    if not conditions:
        return None

    converted = []
    for c in conditions:
        var = c["var"]
        op = c["op"]
        compare_var = c.get("compare_var")
        literal_val = c.get("literal_value")
        right_side = {"var": compare_var} if compare_var is not None else literal_val

        if op in {"equals", "eq"}:
            converted.append({var: {"equals": right_side}})
        elif op in {"not_equals", "ne", "not"}:
            converted.append({var: {"not": right_side}})
        elif op in {"gt", "gte", "lt", "lte", "in"}:
            converted.append({var: {op: right_side}})
        else:
            converted.append({var: {"equals": right_side}})

    if len(converted) == 1:
        return converted[0]

    logic = group.get("logic", "ALL")
    if logic == "ANY":
        return {"OR": converted}
    return {"AND": converted}


def _convert_assignment(asgn: dict[str, Any]) -> dict[str, Any]:
    """Converts a StrictAssignment dictionary into internal Assignment AST format."""
    target_var_key = asgn["target_var_key"]
    inner = asgn.get("assignment", {})
    if "var" in inner:
        expr = {"var": inner["var"]}
    elif "value" in inner:
        expr = inner["value"]
    elif "op" in inner:
        expr = {inner["op"]: inner["amount"]}
    else:
        expr = inner
    return {"target_var_key": target_var_key, "expression": expr}


def translate_plan_node(state: CopilotState) -> dict[str, Any]:
    """Deterministically validates planner operations and maps them straight to the update object."""
    import json

    from pydantic import BaseModel

    from app.modules.copilot.agents import planner_schemas

    checklist = state.get("agent_checklist") or {}
    tool_calls = checklist.get("tool_calls") or []

    # Construct standard GraphUpdateInput payload
    update_payload: dict[str, Any] = {
        "start_target": None,
        "variables": {"upsert": [], "delete": []},
        "nodes": {"upsert": [], "delete": []},
        "rename_variables": [],
        "rename_nodes": [],
    }

    # Map name of tool call to its corresponding validation schema
    schema_map: dict[str, type[BaseModel]] = {
        "upsert_variable": planner_schemas.UpsertVariable,
        "upsert_node": planner_schemas.UpsertNode,
        "upsert_switch_branch": planner_schemas.UpsertSwitchBranch,
        "reroute_edge": planner_schemas.RerouteEdge,
        "delete_entity": planner_schemas.DeleteEntity,
        "rename_entity": planner_schemas.RenameEntity,
    }

    initial_nodes = state.get("initial_flow_data", {}).get("nodes", [])
    initial_node_map = {n.get("id"): n for n in initial_nodes if n.get("id")}

    def get_or_create_upsert(node_id: str) -> dict[str, Any]:
        for u in update_payload["nodes"]["upsert"]:
            if u["id"] == node_id:
                return cast(dict[str, Any], u)
        if node_id in initial_node_map:
            initial_node = initial_node_map[node_id]
            node_type = initial_node.get("node_type") or initial_node.get("node_class")
            node_update: dict[str, Any] = {"id": node_id, "node_type": node_type}
            if node_type in {"LOGICAL_SWITCH", "AGENTIC_SWITCH"}:
                branches = {}
                for br in initial_node.get("branches", []):
                    branch_id = br.get("id")
                    edge_target = None
                    for edge in state.get("initial_flow_data", {}).get("edges", []):
                        if edge.get("source") == node_id and edge.get("source_handle") == branch_id:
                            edge_target = edge.get("target")
                            break
                    expr_id = br.get("expr_id")
                    expr_val = None
                    if expr_id:
                        expr_record = state.get("initial_flow_data", {}).get("expressions", {}).get(expr_id)
                        if expr_record:
                            expr_val = expr_record.get("expr")
                    branches[br["label"]] = {
                        "expression": expr_val,
                        "target": edge_target,
                    }
                node_update["branches"] = branches
                if node_type == "AGENTIC_SWITCH":
                    node_update["agentic_input"] = initial_node.get("agentic_input")
            else:
                edge_target = None
                for edge in state.get("initial_flow_data", {}).get("edges", []):
                    if edge.get("source") == node_id and edge.get("source_handle") is None:
                        edge_target = edge.get("target")
                        break
                node_update["target"] = edge_target

                if node_type == "LOGICAL_ASSIGNER":
                    assignments = []
                    for asgn in initial_node.get("assignments", []):
                        expr_id = asgn.get("expr_id")
                        expr_val = None
                        if expr_id:
                            expr_record = state.get("initial_flow_data", {}).get("expressions", {}).get(expr_id)
                            if expr_record:
                                expr_val = expr_record.get("expr")
                        assignments.append(
                            {
                                "target_var_key": asgn.get("target_var_key"),
                                "expression": expr_val,
                            }
                        )
                    node_update["assignments"] = assignments
                elif node_type == "AGENTIC_ASSIGNER":
                    node_update["agentic_inputs"] = initial_node.get("agentic_inputs", [])
                    node_update["agentic_outputs"] = initial_node.get("agentic_outputs", [])
                    node_update["prompt"] = initial_node.get("prompt", "")
                elif node_type == "RAG_RETRIEVER":
                    node_update["query_var"] = initial_node.get("query_var")
                    node_update["context_output_var"] = initial_node.get("context_output_var")
                    node_update["knowledge_base"] = initial_node.get("knowledge_base")
                    node_update["top_k"] = initial_node.get("top_k")
                elif node_type == "INTERRUPT":
                    node_update["payload_vars"] = initial_node.get("payload_vars", [])
                    node_update["resume_var"] = initial_node.get("resume_var")

            update_payload["nodes"]["upsert"].append(node_update)
            return node_update
        raise ValidationError(f"Cannot route edge from unknown node '{node_id}'.")

    # Pass 1: Parse and validate all tool calls
    for tc in tool_calls:
        name = tc.get("name")
        args_str = tc.get("arguments", "{}")
        try:
            args_dict = json.loads(args_str)
        except Exception as e:
            raise ValidationError(f"Failed to parse arguments for tool '{name}': {str(e)}")

        schema = schema_map.get(name)
        if not schema:
            raise ValidationError(f"Unknown tool call generated by planner: '{name}'")

        try:
            validated = schema.model_validate(args_dict)
        except Exception as e:
            raise ValidationError(f"Arguments validation failed for tool '{name}': {str(e)}")

        args = validated.model_dump(mode="json")

        if name == "upsert_variable":
            update_payload["variables"]["upsert"].append(args)

        elif name == "upsert_node":
            node_id = args["id"]
            node_type = args["node_type"]
            config = args.get("config", {})
            target = args.get("target")

            if node_type == "LOGICAL_ASSIGNER":
                assignments = [_convert_assignment(a) for a in config.get("assignments", [])]
                node_update = {
                    "id": node_id,
                    "node_type": node_type,
                    "assignments": assignments,
                }
                if target is not None:
                    node_update["target"] = target
                update_payload["nodes"]["upsert"].append(node_update)

            elif node_type == "AGENTIC_ASSIGNER":
                node_update = {
                    "id": node_id,
                    "node_type": node_type,
                    "prompt": config.get("prompt"),
                    "agentic_inputs": config.get("agentic_inputs", []),
                    "agentic_outputs": config.get("agentic_outputs", []),
                }
                if target is not None:
                    node_update["target"] = target
                update_payload["nodes"]["upsert"].append(node_update)

            elif node_type == "RAG_RETRIEVER":
                node_update = {
                    "id": node_id,
                    "node_type": node_type,
                    "query_var": config.get("query_var"),
                    "context_output_var": config.get("context_output_var"),
                    "knowledge_base": config.get("knowledge_base"),
                    "top_k": config.get("top_k", 3),
                }
                if target is not None:
                    node_update["target"] = target
                update_payload["nodes"]["upsert"].append(node_update)

            elif node_type == "INTERRUPT":
                node_update = {
                    "id": node_id,
                    "node_type": node_type,
                    "resume_var": config.get("resume_var"),
                    "payload_vars": config.get("payload_vars", []),
                }
                if target is not None:
                    node_update["target"] = target
                update_payload["nodes"]["upsert"].append(node_update)

            elif node_type == "LOGICAL_SWITCH":
                branches = {}
                for b in config.get("branches", []):
                    expr_ast = _convert_condition_group(b.get("condition"))
                    branches[b["label"]] = {"expression": expr_ast, "target": b.get("target")}
                update_payload["nodes"]["upsert"].append({"id": node_id, "node_type": node_type, "branches": branches})

            elif node_type == "AGENTIC_SWITCH":
                branches = {}
                for b in config.get("branches", []):
                    branches[b["label"]] = {"expression": None, "target": b.get("target")}
                update_payload["nodes"]["upsert"].append(
                    {
                        "id": node_id,
                        "node_type": node_type,
                        "agentic_input": config.get("agentic_input"),
                        "branches": branches,
                    }
                )

        elif name == "upsert_switch_branch":
            node_id = args["node_id"]
            label = args["label"]
            target = args["target"]
            condition = args.get("condition")
            expr_ast = _convert_condition_group(condition)

            node = get_or_create_upsert(node_id)
            if "branches" not in node or node["branches"] is None:
                node["branches"] = {}
            node["branches"][label] = {"expression": expr_ast, "target": target}

        elif name == "reroute_edge":
            source_id = args["source"]
            branch_label = args.get("branch")
            new_target = args.get("new_target")

            if source_id.lower() == "start":
                update_payload["start_target"] = new_target
            else:
                node = get_or_create_upsert(source_id)
                if node["node_type"] in {"LOGICAL_SWITCH", "AGENTIC_SWITCH"}:
                    if not branch_label:
                        raise ValidationError(
                            f"Cannot reroute switch node '{source_id}' without specifying a branch label."
                        )
                    if "branches" not in node or node["branches"] is None:
                        node["branches"] = {}
                    if branch_label not in node["branches"]:
                        node["branches"][branch_label] = {}
                    node["branches"][branch_label]["target"] = new_target or ""
                else:
                    if branch_label:
                        raise ValidationError(f"Cannot specify branch '{branch_label}' for linear node '{source_id}'.")
                    node["target"] = new_target or ""

        elif name == "delete_entity":
            kind = args["kind"]
            eid = args["id"]
            parent_id = args.get("parent_id")

            if kind == "node":
                update_payload["nodes"]["delete"].append(eid)
            elif kind == "variable":
                update_payload["variables"]["delete"].append(eid)
            elif kind == "switch_branch":
                if not parent_id:
                    raise ValidationError("parent_id is required when deleting a switch_branch")
                node = get_or_create_upsert(parent_id)
                if "branches" in node and eid in node["branches"]:
                    node["branches"][eid]["target"] = ""

        elif name == "rename_entity":
            kind = args["kind"]
            old_name = args["old_name"]
            new_name = args["new_name"]

            if kind == "node":
                update_payload["rename_nodes"].append({"old_key": old_name, "new_key": new_name})
            elif kind == "variable":
                update_payload["rename_variables"].append({"old_key": old_name, "new_key": new_name})

    validate_node_connectivity(update_payload, state.get("initial_flow_data"))

    result: dict[str, Any] = {"operations": update_payload}
    return result


def validate_node_connectivity(update_payload: dict[str, Any], initial_flow_data: dict[str, Any] | None) -> None:
    if not initial_flow_data:
        return

    initial_nodes = initial_flow_data.get("nodes", [])
    initial_node_ids = {n.get("id") for n in initial_nodes if n.get("id")}

    # Track renames
    renamed_ids = {}
    for rn in update_payload.get("rename_nodes", []):
        renamed_ids[rn["new_key"]] = rn["old_key"]

    # All upserted node IDs
    upserted_nodes = update_payload.get("nodes", {}).get("upsert", [])
    upserted_ids = {n["id"] for n in upserted_nodes}

    # Collect targeted IDs
    targeted_ids = set()
    if update_payload.get("start_target"):
        targeted_ids.add(update_payload["start_target"])

    for n in upserted_nodes:
        # Linear target
        if n.get("target"):
            targeted_ids.add(n["target"])
        # Branches targets
        branches = n.get("branches") or {}
        for br in branches.values():
            if br.get("target"):
                targeted_ids.add(br["target"])

    # Find brand new nodes
    new_nodes = set()
    for nid in upserted_ids:
        if nid not in initial_node_ids and nid not in renamed_ids:
            new_nodes.add(nid)

    for nid in new_nodes:
        if nid not in targeted_ids:
            raise ValidationError(
                f"Orphan node detected: The new node '{nid}' is not targeted by any transition. "
                "Ensure that a preceding node's target/branches routes to it."
            )


def aggregation_node(state: CopilotState) -> dict[str, Any]:
    """Aggregates the transaction update into a list of human-readable plan steps for the UI."""
    state_ops = state.get("operations") or {}
    try:
        update = GraphUpdateInput.model_validate(state_ops)
    except Exception as e:
        raise ValidationError(f"Agents generated invalid updates: {str(e)}")

    plan_steps = []
    if update.start_target:
        plan_steps.append(
            {
                "action": "set_start_target",
                "description": f"Set starting node to '{update.start_target}'",
                "details": {},
            }
        )
    if update.rename_variables:
        for ru in update.rename_variables:
            plan_steps.append(
                {
                    "action": "rename_variable",
                    "description": f"Rename variable '{ru.old_key}' to '{ru.new_key}'",
                    "details": {},
                }
            )
    if update.rename_nodes:
        for rn in update.rename_nodes:
            plan_steps.append(
                {"action": "rename_node", "description": f"Rename node '{rn.old_key}' to '{rn.new_key}'", "details": {}}
            )
    if update.variables:
        if update.variables.delete:
            for d in update.variables.delete:
                plan_steps.append({"action": "delete_variable", "description": f"Delete variable '{d}'", "details": {}})
        if update.variables.upsert:
            for u in update.variables.upsert:
                plan_steps.append(
                    {
                        "action": "upsert_variable",
                        "description": f"Upsert variable '{u.key}' (type: {u.type})",
                        "details": u.model_dump(),
                    }
                )
    if update.nodes:
        if update.nodes.delete:
            for dn in update.nodes.delete:
                plan_steps.append({"action": "delete_node", "description": f"Delete node '{dn}'", "details": {}})
        if update.nodes.upsert:
            for un in update.nodes.upsert:
                plan_steps.append(
                    {
                        "action": "upsert_node",
                        "description": f"Upsert node '{un.id}' (type: {un.node_type})",
                        "details": un.model_dump(),
                    }
                )

    return {"plan": plan_steps}


def wait_for_plan_node(state: CopilotState) -> dict[str, Any]:
    """Automatically approves the plan to continue workflow execution."""
    return {"plan_approved": True}


def validation_node(state: CopilotState) -> dict[str, Any]:
    """Validates generated operations by dry-running them against the backend mutations engine."""
    if not state.get("plan_approved") or not state.get("operations"):
        return {}

    try:
        flow_data = GraphFlowData.model_validate(state["initial_flow_data"])
        state_ops = state.get("operations") or {}
        update = GraphUpdateInput.model_validate(state_ops)

        # Dry-run patch application
        apply_graph_update(flow_data, update)
        return {"validation_error": None}
    except Exception as e:
        logger.warning("Agent operation dry-run failed: %s", str(e))
        log_validation_error(state["trace_id"], state.get("graph_id"), str(e))
        return {"validation_error": str(e)}


def wait_for_apply_node(state: CopilotState) -> dict[str, Any]:
    """Automatically approves applying the patch if validation succeeded."""
    has_error = bool(state.get("validation_error"))
    return {"apply_approved": not has_error}


def apply_node(state: CopilotState) -> dict[str, Any]:
    """Marks the state as applied so the service can persist changes."""
    if not state.get("apply_approved") or state.get("validation_error"):
        return {"applied": False}
    return {"applied": True}


# --- Graph Routing Logic ---


def route_after_plan(state: CopilotState) -> Literal["validation_node", "__end__"]:
    if state.get("plan_approved"):
        return "validation_node"
    return "__end__"


def route_after_apply(state: CopilotState) -> Literal["apply_node", "__end__"]:
    if state.get("apply_approved") and not state.get("validation_error"):
        return "apply_node"
    return "__end__"


# --- Build StateGraph ---

workflow = StateGraph(CopilotState)

workflow.add_node("planner_node", planner_node)
workflow.add_node("translate_plan_node", translate_plan_node)
workflow.add_node("aggregation_node", aggregation_node)
workflow.add_node("wait_for_plan_node", wait_for_plan_node)
workflow.add_node("validation_node", validation_node)
workflow.add_node("wait_for_apply_node", wait_for_apply_node)
workflow.add_node("apply_node", apply_node)

workflow.add_edge(START, "planner_node")
workflow.add_edge("planner_node", "translate_plan_node")
workflow.add_edge("translate_plan_node", "aggregation_node")
workflow.add_edge("aggregation_node", "wait_for_plan_node")
workflow.add_conditional_edges("wait_for_plan_node", route_after_plan)
workflow.add_edge("validation_node", "wait_for_apply_node")
workflow.add_conditional_edges("wait_for_apply_node", route_after_apply)
workflow.add_edge("apply_node", END)

# In-memory saver to persist threads across HTTP cycles
memory_saver = MemorySaver()
copilot_graph = workflow.compile(checkpointer=memory_saver)
