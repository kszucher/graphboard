import json
import subprocess
from typing import Any

from app.graphs.schemas import DiagnosticRead

TYPE_MAP_GB_TO_PY = {
    "number": "int",
    "float": "float",
    "string": "str",
    "boolean": "bool",
}


def ast_expr_to_py(node: dict[str, Any] | None) -> str:
    """Recursively converts a slot AST expression dict to Python code string."""
    if not node:
        return "True"

    kind = node.get("kind")
    if kind == "literal":
        return repr(node.get("value"))
    elif kind == "stateRef":
        var_key = node.get("varKey", "")
        return f'state.get("{var_key}")' if var_key else "None"
    elif kind == "binaryOp":
        left = ast_expr_to_py(node.get("left"))
        right = ast_expr_to_py(node.get("right"))
        op = node.get("op", "==")
        return f"({left} {op} {right})"
    elif kind == "unaryOp":
        expr = ast_expr_to_py(node.get("expr"))
        op = node.get("op", "not")
        return f"({op} {expr})"
    return "True"


def generate_graph_code(payload: dict[str, Any]) -> str:
    """
    Generates Python code strictly from graph payload (nodes, slots, edges, operations).
    Code is derived completely deterministically.
    """
    code_lines = [
        "from typing import TypedDict",
        "",
        "from langgraph.graph import END, START, StateGraph",
        "",
    ]

    # 1. State Definition
    code_lines.append("# ----------------------------------------------------")
    code_lines.append("# State Definition")
    code_lines.append("# ----------------------------------------------------")
    code_lines.append("class State(TypedDict):")

    ops = payload.get("operations", {})
    definer_ops = ops.get("definer", []) if isinstance(ops, dict) else []
    all_variables = []
    for op in definer_ops:
        all_variables.extend(op.get("variables", []))

    # Fallback to legacy state_schema if operations.definer is empty
    if not all_variables and payload.get("state_schema"):
        all_variables = payload.get("state_schema", [])

    if all_variables:
        for var in all_variables:
            var_key = var.get("key") or var.get("name") or var.get("id")
            var_type = var.get("type", "string")
            py_type = TYPE_MAP_GB_TO_PY.get(var_type, "str")
            default_val = var.get("default_value")
            if default_val is None:
                if var_type in ("number", "float"):
                    default_val = 0 if var_type == "number" else 0.0
                elif var_type == "boolean":
                    default_val = False
                else:
                    default_val = ""
            code_lines.append(f"    {var_key}: {py_type}  # default: {repr(default_val)}")
    else:
        code_lines.append("    pass")
    code_lines.append("")

    if all_variables:
        code_lines.append("initial_state: State = {")
        for var in all_variables:
            var_key = var.get("key") or var.get("name") or var.get("id")
            var_type = var.get("type", "string")
            default_val = var.get("default_value")
            if default_val is None:
                if var_type in ("number", "float"):
                    default_val = 0 if var_type == "number" else 0.0
                elif var_type == "boolean":
                    default_val = False
                else:
                    default_val = ""
            code_lines.append(f'    "{var_key}": {repr(default_val)},')
        code_lines.append("}")
        code_lines.append("")

    # 2. Nodes (Excludes DEFINER nodes - 0 python functions!)
    code_lines.append("# ----------------------------------------------------")
    code_lines.append("# Nodes")
    code_lines.append("# ----------------------------------------------------")

    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])

    definer_node_ids = {n["id"] for n in nodes if n.get("node_type") == "DEFINER"}
    executable_logic_nodes = [
        n for n in nodes if n.get("node_type") in ("STEP", "SWITCH", "LOGICAL_ASSIGNER", "AGENTIC_ASSIGNER")
    ]

    for node in executable_logic_nodes:
        node_name = node["id"]
        if node.get("node_type") == "SWITCH":
            slots = node.get("slots", [])
            code_lines.append(f"def {node_name}(state: State) -> str:")
            if not slots:
                code_lines.append("    # Add output slots in the UI first")
                code_lines.append('    return ""')
            else:
                for i, slot in enumerate(slots):
                    label = slot.get("raw_string") or f"Slot {i + 1}"
                    expr_dict = slot.get("expression")
                    cond_str = ast_expr_to_py(expr_dict)

                    code_lines.append(f"    {'if' if i == 0 else 'elif'} {cond_str}:")
                    code_lines.append(f'        return "{label}"')
                code_lines.append('    return ""')
        elif node.get("node_type") == "LOGICAL_ASSIGNER":
            code_lines.append(f"def {node_name}(state: State) -> dict:")
            ref_id = node.get("ref_id")
            logical_ops = ops.get("logical", []) if isinstance(ops, dict) else []
            target_op = next((o for o in logical_ops if o.get("id") == ref_id), None) if ref_id else None
            assignments = target_op.get("assignments", []) if target_op else []

            if assignments:
                code_lines.append("    return {")
                for asgn in assignments:
                    target_key = asgn.get("target_var_key")
                    if target_key:
                        val = asgn.get("value")
                        expr_str = repr(val)
                        if asgn.get("expression"):
                            expr_str = ast_expr_to_py(asgn.get("expression"))
                        code_lines.append(f'        "{target_key}": {expr_str},')
                code_lines.append("    }")
            else:
                code_lines.append("    return {}")
        else:
            # STEP / AGENTIC_ASSIGNER nodes
            code_lines.append(f"def {node_name}(state: State) -> dict:")
            slots = node.get("slots", [])
            mutations = [s for s in slots if s.get("target_var_key")]
            if mutations:
                code_lines.append("    return {")
                for m in mutations:
                    target_key = m["target_var_key"]
                    expr_str = ast_expr_to_py(m.get("expression"))
                    code_lines.append(f'        "{target_key}": {expr_str},')
                code_lines.append("    }")
            else:
                code_lines.append("    return {}")
        code_lines.append("")

    # 3. Graph Definition
    code_lines.append("# ----------------------------------------------------")
    code_lines.append("# Graph Definition")
    code_lines.append("# ----------------------------------------------------")
    code_lines.append("workflow = StateGraph(State)")
    code_lines.append("")

    for node in executable_logic_nodes:
        code_lines.append(f'workflow.add_node("{node["id"]}", {node["id"]})')
    code_lines.append("")

    # Bypass resolution for START -> definer -> first_target (with cycle protection)
    def resolve_target(target_id: str, visited: set[str] | None = None) -> str:
        if visited is None:
            visited = set()
        if target_id in visited:
            return "END"
        visited.add(target_id)

        if target_id in definer_node_ids:
            # Trace outgoing edge from definer node
            definer_out = next((e for e in edges if e.get("source_id") == target_id), None)
            if definer_out:
                return resolve_target(definer_out.get("target_id", "end"), visited)
            return "END"
        return "END" if target_id == "end" else f'"{target_id}"'

    start_edges = [e for e in edges if e.get("source_id") == "start"]
    for e in start_edges:
        target = resolve_target(e.get("target_id", "end"))
        code_lines.append(f"workflow.add_edge(START, {target})")

    static_edges = [
        e
        for e in edges
        if e.get("source_id") != "start"
        and e.get("source_id") not in definer_node_ids
        and e.get("source_type") == "node"
        and e.get("target_id") != "start"
    ]
    for e in static_edges:
        tgt = resolve_target(e.get("target_id", "end"))
        code_lines.append(f'workflow.add_edge("{e.get("source_id")}", {tgt})')

    switch_nodes = [n for n in executable_logic_nodes if n.get("node_type") == "SWITCH"]

    for switch in switch_nodes:
        node_name = switch["id"]
        switch_slots = {s["id"]: s.get("raw_string") for s in switch.get("slots", [])}
        routing_edges = [e for e in edges if e.get("source_id") in switch_slots]

        if routing_edges:
            path_map_lines = []
            for slot in switch.get("slots", []):
                slot_edge = next((e for e in routing_edges if e.get("source_id") == slot["id"]), None)
                if slot_edge:
                    tgt = "END" if slot_edge.get("target_id") == "end" else f'"{slot_edge.get("target_id")}"'
                    path_map_lines.append(f'        "{slot.get("raw_string")}": {tgt},')

            code_lines.append("workflow.add_conditional_edges(")
            code_lines.append(f'    "{node_name}",')
            code_lines.append(f"    {node_name},")
            code_lines.append("    {")
            code_lines.extend(path_map_lines)
            code_lines.append("    }")
            code_lines.append(")")
            code_lines.append("")

    code_lines.append("app = workflow.compile()")

    generated_code = "\n".join(code_lines)

    # Format code with ruff if available
    try:
        process = subprocess.Popen(
            ["ruff", "format", "-"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, _ = process.communicate(input=generated_code)
        if process.returncode == 0 and stdout:
            generated_code = stdout
    except Exception:
        pass

    return generated_code


def run_ruff_diagnostics(code: str) -> list[DiagnosticRead]:
    """Runs ruff check via subprocess and parses JSON diagnostics."""
    if not code.strip():
        return []

    try:
        process = subprocess.Popen(
            ["ruff", "check", "--output-format=json", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, _ = process.communicate(input=code)
        if not stdout.strip():
            return []

        raw_diagnostics = json.loads(stdout)
        diagnostics: list[DiagnosticRead] = []

        for item in raw_diagnostics:
            code_str = item.get("code", "")
            severity = "error" if code_str.startswith(("E", "F")) else "warning"
            loc = item.get("location", {})
            diagnostics.append(
                DiagnosticRead(
                    line=loc.get("row", 1),
                    column=loc.get("column", 1),
                    code=code_str,
                    message=item.get("message", ""),
                    severity=severity,
                )
            )
        return diagnostics
    except Exception:
        return []
