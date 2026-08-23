from __future__ import annotations

from typing import Any

from app.core.exceptions import ValidationError
from app.modules.copilot import planner_schemas
from app.modules.copilot.state import CopilotState
from app.modules.graphs.operations import GraphUpdateInput


def _hydrate_existing_node(node_id: str, initial_flow_data: dict[str, Any] | None) -> dict[str, Any]:
    """Extracts existing node configuration and edge targets to support partial retargeting or surgical branch patching."""
    initial_nodes = (initial_flow_data or {}).get("nodes", [])
    initial_edges = (initial_flow_data or {}).get("edges", [])
    initial_node = next((n for n in initial_nodes if n.get("id") == node_id), None)

    if not initial_node:
        raise ValidationError(f"Cannot route edge or branch from unknown node '{node_id}'.")

    node_type = initial_node.get("node_type") or initial_node.get("node_class")
    hydrated: dict[str, Any] = {"id": node_id, "node_type": node_type}

    if node_type in {"LOGICAL_SWITCH", "AGENTIC_SWITCH"}:
        branches: dict[str, Any] = {}
        for br in initial_node.get("branches", []):
            branch_id = br.get("id")
            edge_target = next(
                (
                    edge.get("target")
                    for edge in initial_edges
                    if edge.get("source") == node_id and edge.get("source_handle") == branch_id
                ),
                None,
            )
            branches[br["label"]] = {
                "expression": br.get("expression"),
                "target": edge_target,
            }
        hydrated["branches"] = branches
        if node_type == "AGENTIC_SWITCH":
            hydrated["agentic_input"] = initial_node.get("agentic_input")
    else:
        edge_target = next(
            (
                edge.get("target")
                for edge in initial_edges
                if edge.get("source") == node_id and edge.get("source_handle") is None
            ),
            None,
        )
        hydrated["target"] = edge_target

        if node_type == "LOGICAL_ASSIGNER":
            hydrated["assignments"] = [
                {"target_var_key": a.get("target_var_key"), "expression": a.get("expression")}
                for a in initial_node.get("assignments", [])
            ]
        elif node_type == "AGENTIC_ASSIGNER":
            hydrated["agentic_inputs"] = initial_node.get("agentic_inputs", [])
            raw_outputs = initial_node.get("agentic_outputs", [])
            hydrated["agentic_outputs"] = [
                {"key": o, "type": "string"} if isinstance(o, str) else o for o in raw_outputs
            ]
            hydrated["prompt"] = initial_node.get("prompt", "")
        elif node_type == "RAG_RETRIEVER":
            hydrated["query_var"] = initial_node.get("query_var")
            hydrated["context_output_var"] = initial_node.get("context_output_var")
            hydrated["knowledge_base"] = initial_node.get("knowledge_base")
            hydrated["top_k"] = initial_node.get("top_k", 3)
        elif node_type == "INTERRUPT":
            hydrated["payload_vars"] = initial_node.get("payload_vars", [])
            hydrated["resume_var"] = initial_node.get("resume_var")

    return hydrated


def translate_plan(
    plan: planner_schemas.ApplyGraphPlan,
    initial_flow_data: dict[str, Any] | None = None,
) -> GraphUpdateInput:
    """Transforms an ApplyGraphPlan into a validated GraphUpdateInput."""
    nodes_upsert: list[dict[str, Any]] = []
    nodes_delete: list[str] = []
    vars_upsert: list[dict[str, Any]] = []
    vars_delete: list[str] = []
    rename_variables: list[dict[str, str]] = []
    rename_nodes: list[dict[str, str]] = []
    start_target: str | None = None

    def get_or_create_upsert(node_id: str) -> dict[str, Any]:
        for u in nodes_upsert:
            if u["id"] == node_id:
                return u
        hydrated = _hydrate_existing_node(node_id, initial_flow_data)
        nodes_upsert.append(hydrated)
        return hydrated

    # 1. State Variables
    for var in plan.variables:
        vars_upsert.append(var.model_dump(mode="json"))

    # 2. Renames
    for rn in plan.renames:
        if rn.kind == "node":
            rename_nodes.append({"old_key": rn.old_name, "new_key": rn.new_name})
        elif rn.kind == "variable":
            rename_variables.append({"old_key": rn.old_name, "new_key": rn.new_name})

    # 3. Deletions
    for dl in plan.deletions:
        if dl.kind == "node":
            nodes_delete.append(dl.id)
        elif dl.kind == "variable":
            vars_delete.append(dl.id)
        elif dl.kind == "switch_branch":
            if not dl.parent_id:
                raise ValidationError("parent_id is required when deleting a switch_branch")
            node = get_or_create_upsert(dl.parent_id)
            if "branches" in node and dl.id in node["branches"]:
                node["branches"].pop(dl.id, None)

    # 4. Nodes
    for n in plan.nodes:
        node_id = n.id
        node_type = n.node_type
        config = n.config
        target = n.target

        if node_id.lower() == "start":
            start_target = target
        elif config is None:
            node = get_or_create_upsert(node_id)
            if target is not None:
                node["target"] = target
        else:
            config_dict = config.model_dump(mode="json")
            node_update: dict[str, Any]
            if node_type == "LOGICAL_ASSIGNER":
                node_update = {
                    "id": node_id,
                    "node_type": node_type,
                    "assignments": [
                        {"target_var_key": a["target_var_key"], "expression": a["expression"]}
                        for a in config_dict.get("assignments", [])
                    ],
                }
                if target is not None:
                    node_update["target"] = target
                nodes_upsert.append(node_update)

            elif node_type == "AGENTIC_ASSIGNER":
                node_update = {
                    "id": node_id,
                    "node_type": node_type,
                    "prompt": config_dict.get("prompt"),
                    "agentic_inputs": config_dict.get("inputs", []),
                    "agentic_outputs": config_dict.get("outputs", []),
                }
                if target is not None:
                    node_update["target"] = target
                nodes_upsert.append(node_update)

            elif node_type == "RAG_RETRIEVER":
                node_update = {
                    "id": node_id,
                    "node_type": node_type,
                    "query_var": config_dict.get("query_var"),
                    "context_output_var": config_dict.get("context_output_var"),
                    "knowledge_base": config_dict.get("knowledge_base", "trivia"),
                    "top_k": config_dict.get("top_k", 3),
                }
                if target is not None:
                    node_update["target"] = target
                nodes_upsert.append(node_update)

            elif node_type == "INTERRUPT":
                node_update = {
                    "id": node_id,
                    "node_type": node_type,
                    "resume_var": config_dict.get("resume_var"),
                    "payload_vars": config_dict.get("payload_vars", []),
                }
                if target is not None:
                    node_update["target"] = target
                nodes_upsert.append(node_update)

            elif node_type == "LOGICAL_SWITCH":
                branches = {
                    b["label"]: {
                        "expression": b.get("condition"),
                        "target": b.get("target"),
                    }
                    for b in config_dict.get("branches", [])
                }
                nodes_upsert.append({"id": node_id, "node_type": node_type, "branches": branches})

            elif node_type == "AGENTIC_SWITCH":
                branches = {
                    b["label"]: {"expression": None, "target": b.get("target")} for b in config_dict.get("branches", [])
                }
                nodes_upsert.append(
                    {
                        "id": node_id,
                        "node_type": node_type,
                        "agentic_input": config_dict.get("agentic_input"),
                        "branches": branches,
                    }
                )

    # 5. Surgical Switch Branches
    for sb in plan.switch_branches:
        node = get_or_create_upsert(sb.node_id)
        if "branches" not in node or node["branches"] is None:
            node["branches"] = {}
        node["branches"][sb.label] = {"expression": sb.condition, "target": sb.target}

    raw_payload: dict[str, Any] = {
        "start_target": start_target,
        "variables": {"upsert": vars_upsert, "delete": vars_delete},
        "nodes": {"upsert": nodes_upsert, "delete": nodes_delete},
        "rename_variables": rename_variables,
        "rename_nodes": rename_nodes,
    }

    return GraphUpdateInput.model_validate(raw_payload)


def translate_plan_node(state: CopilotState) -> dict[str, Any]:
    """LangGraph node wrapper: translates ApplyGraphPlan to GraphUpdateInput."""
    plan = state.get("plan")
    initial_flow_data = state.get("initial_flow_data")

    if not plan:
        return {"operations": None, "validation_error": "No plan generated by planner."}

    try:
        operations = translate_plan(plan, initial_flow_data)
        return {"operations": operations, "validation_error": None}
    except Exception as e:
        return {"operations": None, "validation_error": str(e)}
