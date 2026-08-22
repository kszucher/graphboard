from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel

from app.core.exceptions import ValidationError
from app.modules.copilot.agents import planner_schemas
from app.modules.copilot.models import CopilotState


def convert_condition_group(group: dict[str, Any] | None) -> dict[str, Any] | None:
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


def convert_assignment(asgn: dict[str, Any]) -> dict[str, Any]:
    """Converts a StrictAssignment dictionary into internal Assignment AST format."""
    target_var_key = asgn["target_var_key"]
    inner = asgn.get("assignment", {})
    if isinstance(inner, dict):
        if "var" in inner and len(inner) == 1:
            expr = {"var": inner["var"]}
        elif "value" in inner and len(inner) == 1:
            expr = inner["value"]
        elif "op" in inner and inner["op"] in {"increment", "decrement", "multiply", "divide"} and "amount" in inner:
            expr = {inner["op"]: inner["amount"]}
        else:
            expr = inner
    else:
        expr = inner
    return {"target_var_key": target_var_key, "expression": expr}


def validate_node_connectivity(update_payload: dict[str, Any], initial_flow_data: dict[str, Any] | None) -> None:
    """Ensures newly created nodes are connected to avoid dangling orphan subgraphs."""
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
        if n.get("target"):
            targeted_ids.add(n["target"])
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


def translate_plan_to_operations(
    tool_calls: list[dict[str, Any]],
    initial_flow_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministically parses and translates planner tool calls into a validated GraphUpdateInput payload."""
    update_payload: dict[str, Any] = {
        "start_target": None,
        "variables": {"upsert": [], "delete": []},
        "nodes": {"upsert": [], "delete": []},
        "rename_variables": [],
        "rename_nodes": [],
    }

    schema_map: dict[str, type[BaseModel]] = {
        "upsert_variable": planner_schemas.UpsertVariable,
        "upsert_node": planner_schemas.UpsertNode,
        "upsert_switch_branch": planner_schemas.UpsertSwitchBranch,
        "delete_entity": planner_schemas.DeleteEntity,
        "rename_entity": planner_schemas.RenameEntity,
    }

    initial_nodes = (initial_flow_data or {}).get("nodes", [])
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
                    for edge in (initial_flow_data or {}).get("edges", []):
                        if edge.get("source") == node_id and edge.get("source_handle") == branch_id:
                            edge_target = edge.get("target")
                            break
                    expr_id = br.get("expr_id")
                    expr_val = None
                    if expr_id:
                        expr_record = (initial_flow_data or {}).get("expressions", {}).get(expr_id)
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
                for edge in (initial_flow_data or {}).get("edges", []):
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
                            expr_record = (initial_flow_data or {}).get("expressions", {}).get(expr_id)
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
        if not name or not isinstance(name, str):
            raise ValidationError(f"Missing or invalid tool call name in '{tc}'")

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
            node_type = args.get("node_type")
            config = args.get("config")
            target = args.get("target")

            if node_id.lower() == "start":
                update_payload["start_target"] = target
            elif config is None:
                # Retargeting or partial update on existing node
                node = get_or_create_upsert(node_id)
                if target is not None:
                    node["target"] = target
            else:
                if node_type == "LOGICAL_ASSIGNER":
                    assignments = [convert_assignment(a) for a in config.get("assignments", [])]
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
                        expr_ast = convert_condition_group(b.get("condition"))
                        branches[b["label"]] = {"expression": expr_ast, "target": b.get("target")}
                    update_payload["nodes"]["upsert"].append(
                        {"id": node_id, "node_type": node_type, "branches": branches}
                    )

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
            expr_ast = convert_condition_group(condition)

            node = get_or_create_upsert(node_id)
            if "branches" not in node or node["branches"] is None:
                node["branches"] = {}
            node["branches"][label] = {"expression": expr_ast, "target": target}

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

    validate_node_connectivity(update_payload, initial_flow_data)
    return update_payload


def translate_plan_node(state: CopilotState) -> dict[str, Any]:
    """LangGraph node wrapper: translates plan tool calls to operations."""
    tool_calls = state.get("tool_calls") or []
    initial_flow_data = state.get("initial_flow_data")

    operations = translate_plan_to_operations(tool_calls, initial_flow_data)
    return {"operations": operations}
