import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.graphs.schemas import DefinerVariableSchema, DiagnosticRead, GraphFlowData


def _get_ruff_path() -> str:
    """Resolves the local virtual environment's ruff binary if available, falling back to PATH."""
    exe_dir = Path(sys.executable).parent
    ruff_name = "ruff.exe" if sys.platform == "win32" else "ruff"
    local_ruff = exe_dir / ruff_name
    if local_ruff.exists():
        return str(local_ruff)

    which_ruff = shutil.which("ruff")
    if which_ruff:
        return which_ruff

    return "ruff"


TYPE_MAP_GB_TO_PY = {
    "number": "int",
    "float": "float",
    "boolean": "bool",
    "string": "str",
}


def ast_expr_to_py(
    node: dict[str, Any] | None, default_fallback: str = "True", valid_keys: set[str] | None = None
) -> str:
    """Recursively converts a slot AST expression dict to Python code string."""
    if not node:
        return default_fallback

    kind = node.get("kind")
    if kind == "literal":
        val = node.get("value")
        if isinstance(val, str):
            return repr(val)
        return str(val)

    elif kind == "stateRef":
        var_key = node.get("varKey", "")
        return f'state.get("{var_key}")'

    elif kind == "binaryOp":
        op = node.get("op", "==")
        left = ast_expr_to_py(node.get("left"), default_fallback, valid_keys)
        right = ast_expr_to_py(node.get("right"), default_fallback, valid_keys)
        return f"({left} {op} {right})"

    elif kind == "unaryOp":
        op = node.get("op", "not")
        expr = ast_expr_to_py(node.get("expr"), default_fallback, valid_keys)
        if op == "not":
            return f"(not {expr})"
        return f"({op}{expr})"

    return default_fallback


def _find_invalid_state_refs(expr_node: dict[str, Any] | None, valid_keys: set[str]) -> set[str]:
    if not expr_node or not isinstance(expr_node, dict):
        return set()

    invalid = set()
    kind = expr_node.get("kind")
    if kind == "stateRef":
        var_key = expr_node.get("varKey")
        if var_key and var_key not in valid_keys:
            invalid.add(var_key)
    elif kind == "binaryOp":
        invalid.update(_find_invalid_state_refs(expr_node.get("left"), valid_keys))
        invalid.update(_find_invalid_state_refs(expr_node.get("right"), valid_keys))
    elif kind == "unaryOp":
        invalid.update(_find_invalid_state_refs(expr_node.get("expr"), valid_keys))

    return invalid


def validate_flow_data(flow_data: GraphFlowData) -> list[DiagnosticRead]:
    diagnostics = []

    # Get all definer variables
    all_variables = []
    for op in flow_data.operations.definer:
        all_variables.extend(op.variables)

    valid_keys = {var.key for var in all_variables if var.key}

    # 1. Check STEP nodes for invalid target_var_key in slots
    for node in flow_data.nodes:
        if node.node_type == "STEP":
            for slot in node.slots:
                target_key = slot.target_var_key
                if target_key and target_key not in valid_keys:
                    diagnostics.append(
                        DiagnosticRead(
                            line=1,
                            column=1,
                            code="E001",
                            message=f"Invalid mutation target: variable '{target_key}' is missing or deleted.",
                            severity="error",
                            node_id=node.id,
                            slot_id=slot.id,
                        )
                    )

        # 2. Check LOGICAL_ASSIGNER nodes
        elif node.node_type == "LOGICAL_ASSIGNER":
            ref_id = node.ref_id
            logical_ops = flow_data.operations.logical
            target_op = next((o for o in logical_ops if o.id == ref_id), None) if ref_id else None
            assignments = target_op.assignments if target_op else []
            for asgn in assignments:
                target_key = asgn.target_var_key
                if target_key and target_key not in valid_keys:
                    diagnostics.append(
                        DiagnosticRead(
                            line=1,
                            column=1,
                            code="E002",
                            message=f"Invalid assignment target: variable '{target_key}' is missing or deleted.",
                            severity="error",
                            node_id=node.id,
                            slot_id=asgn.id,
                        )
                    )

        # 3. Check SWITCH nodes
        elif node.node_type == "SWITCH":
            for slot in node.slots:
                expr = slot.expression
                if expr:
                    invalid_refs = _find_invalid_state_refs(expr, valid_keys)
                    for invalid_var in invalid_refs:
                        diagnostics.append(
                            DiagnosticRead(
                                line=1,
                                column=1,
                                code="E003",
                                message=f"Invalid state reference: variable '{invalid_var}' is missing or deleted.",
                                severity="error",
                                node_id=node.id,
                                slot_id=slot.id,
                            )
                        )

    return diagnostics


def generate_graph_code(payload: dict[str, Any] | GraphFlowData) -> str:
    legacy_schema: list[Any] = []
    if isinstance(payload, dict):
        legacy_schema = payload.get("state_schema") or []
        flow_data = GraphFlowData.model_validate(payload)
    else:
        flow_data = payload

    code_lines = []

    # Imports
    code_lines.append("from typing import TypedDict, Literal, Any")
    code_lines.append("from langgraph.graph import StateGraph, START, END")
    code_lines.append("")

    # 1. State Definition
    code_lines.append("# ----------------------------------------------------")
    code_lines.append("# State Definition")
    code_lines.append("# ----------------------------------------------------")

    # Get all variables from definer operations
    all_variables = []
    for op in flow_data.operations.definer:
        all_variables.extend(op.variables)

    # Fallback to legacy state_schema if operations.definer is empty
    if not all_variables and legacy_schema:
        for item in legacy_schema:
            all_variables.append(
                DefinerVariableSchema(
                    id=item.get("id") or item.get("key") or "",
                    key=item.get("key") or "",
                    type=item.get("type") or "string",
                    default_value=item.get("default_value"),
                    description=item.get("description"),
                )
            )

    valid_keys = {var.key for var in all_variables if var.key}

    if all_variables:
        code_lines.append("class State(TypedDict):")
        for var in all_variables:
            var_key = var.key
            var_type = var.type
            py_type = TYPE_MAP_GB_TO_PY.get(var_type, "str")
            code_lines.append(f"    {var_key}: {py_type}")
        code_lines.append("")

        code_lines.append("initial_state: State = {")
        for var in all_variables:
            var_key = var.key
            var_type = var.type
            default_val = var.default_value
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
    else:
        code_lines.append("class State(TypedDict):")
        code_lines.append("    pass")
        code_lines.append("")
        code_lines.append("initial_state: State = {}")
        code_lines.append("")

    # 2. Nodes (Excludes DEFINER nodes - 0 python functions!)
    code_lines.append("# ----------------------------------------------------")
    code_lines.append("# Nodes")
    code_lines.append("# ----------------------------------------------------")

    nodes = flow_data.nodes
    edges = flow_data.edges

    definer_node_ids = {n.id for n in nodes if n.node_type == "DEFINER"}
    executable_logic_nodes = [
        n for n in nodes if n.node_type in ("STEP", "SWITCH", "LOGICAL_ASSIGNER", "AGENTIC_ASSIGNER")
    ]

    for node in executable_logic_nodes:
        node_name = node.id
        if node.node_type == "SWITCH":
            slots = node.slots
            code_lines.append(f"def {node_name}_node(state: State) -> None:")
            code_lines.append("    pass")
            code_lines.append("")
            code_lines.append(f"def {node_name}(state: State) -> str:")
            if not slots:
                code_lines.append("    # Add output slots in the UI first")
                code_lines.append('    return ""')
            else:
                for i, slot in enumerate(slots):
                    label = slot.raw_string or f"Slot {i + 1}"
                    expr_dict = slot.expression
                    cond_str = ast_expr_to_py(expr_dict, default_fallback="False", valid_keys=valid_keys)

                    code_lines.append(f"    {'if' if i == 0 else 'elif'} {cond_str}:")
                    code_lines.append(f'        return "{label}"')
                code_lines.append('    return ""')
        elif node.node_type == "LOGICAL_ASSIGNER":
            code_lines.append(f"def {node_name}(state: State) -> dict:")
            ref_id = node.ref_id
            logical_ops = flow_data.operations.logical
            target_op = next((o for o in logical_ops if o.id == ref_id), None) if ref_id else None
            assignments = target_op.assignments if target_op else []

            if assignments:
                code_lines.append("    return {")
                for asgn in assignments:
                    target_key = asgn.target_var_key
                    if target_key:
                        if target_key not in valid_keys:
                            continue
                        val = asgn.value
                        expr_str = repr(val)
                        if asgn.expression:
                            expr_str = ast_expr_to_py(asgn.expression, valid_keys=valid_keys)
                        code_lines.append(f'        "{target_key}": {expr_str},')
                code_lines.append("    }")
            else:
                code_lines.append("    return {}")
        else:
            # STEP / AGENTIC_ASSIGNER nodes
            code_lines.append(f"def {node_name}(state: State) -> dict:")
            slots = node.slots
            mutations = [s for s in slots if s.target_var_key]
            if mutations:
                code_lines.append("    return {")
                for m in mutations:
                    slot_target_key = m.target_var_key
                    if not slot_target_key or slot_target_key not in valid_keys:
                        continue
                    expr_str = ast_expr_to_py(m.expression, valid_keys=valid_keys)
                    code_lines.append(f'        "{slot_target_key}": {expr_str},')
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
        if node.node_type == "SWITCH":
            code_lines.append(f'workflow.add_node("{node.id}", {node.id}_node)')
        else:
            code_lines.append(f'workflow.add_node("{node.id}", {node.id})')
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
            definer_out = next((e for e in edges if e.source_id == target_id), None)
            if definer_out:
                return resolve_target(definer_out.target_id, visited)
            return "END"
        return "END" if target_id == "end" else f'"{target_id}"'

    start_edges = [e for e in edges if e.source_id == "start"]
    for e in start_edges:
        target = resolve_target(e.target_id)
        code_lines.append(f"workflow.add_edge(START, {target})")

    static_edges = [
        e
        for e in edges
        if e.source_id != "start"
        and e.source_id not in definer_node_ids
        and e.source_type == "node"
        and e.target_id != "start"
    ]
    for e in static_edges:
        tgt = resolve_target(e.target_id)
        code_lines.append(f'workflow.add_edge("{e.source_id}", {tgt})')

    switch_nodes = [n for n in executable_logic_nodes if n.node_type == "SWITCH"]

    for switch in switch_nodes:
        node_name = switch.id
        switch_slots = {s.id: s.raw_string for s in switch.slots}
        routing_edges = [e for e in edges if e.source_id in switch_slots]

        if routing_edges:
            path_map_lines = []
            for slot in switch.slots:
                slot_edge = next((e for e in routing_edges if e.source_id == slot.id), None)
                if slot_edge:
                    tgt = "END" if slot_edge.target_id == "end" else f'"{slot_edge.target_id}"'
                    path_map_lines.append(f'        "{slot.raw_string}": {tgt},')

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
            [_get_ruff_path(), "format", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, _ = process.communicate(input=generated_code)
        if process.returncode == 0 and stdout:
            return stdout
    except Exception:
        pass

    return generated_code


def run_ruff_diagnostics(code: str) -> list[DiagnosticRead]:
    if not code.strip():
        return []

    try:
        process = subprocess.Popen(
            [_get_ruff_path(), "check", "--output-format=json", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, _ = process.communicate(input=code)
        if process.returncode != 0 and not stdout:
            return []

        data = json.loads(stdout)
        diagnostics = []
        for item in data:
            diagnostics.append(
                DiagnosticRead(
                    line=item.get("location", {}).get("row", 1),
                    column=item.get("location", {}).get("column", 1),
                    code=item.get("code", "UNK"),
                    message=item.get("message", ""),
                    severity="warning" if item.get("code", "").startswith("W") else "error",
                )
            )
        return diagnostics
    except Exception:
        return []


def compile_flow_with_langgraph(payload: dict[str, Any] | GraphFlowData) -> dict[str, Any]:
    """
    Compiles the flow payload into executable python code, executes it,
    runs the compiled LangGraph workflow with its initial state, and returns the final state.
    """
    if isinstance(payload, dict):
        flow_data = GraphFlowData.model_validate(payload)
    else:
        flow_data = payload

    # Run semantic validation
    errors = validate_flow_data(flow_data)
    severe_errors = [e for e in errors if e.severity == "error"]
    if severe_errors:
        err_msg = "; ".join(e.message for e in severe_errors)
        return {"variables": [], "error": f"Compilation/Execution failed: {err_msg}"}

    namespace: dict[str, Any] = {}
    try:
        code = generate_graph_code(flow_data)
        exec(code, namespace)
    except Exception as e:
        return {"variables": [], "error": f"Compilation/Execution failed: {str(e)}"}

    app = namespace.get("app")
    initial_state = namespace.get("initial_state", {})

    if not app:
        return {"variables": [], "error": "Compiled workflow does not define 'app'"}

    try:
        final_state = app.invoke(initial_state)
    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}

    variables_list = [{"key": k, "value": v} for k, v in final_state.items()]
    return {"variables": variables_list}
