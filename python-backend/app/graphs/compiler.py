import ast
import asyncio
import json
import multiprocessing
import shutil
import sys
import textwrap
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from app.graphs.schemas import DefinerVariableSchema, DiagnosticRead, GraphFlowData

_execution_executor: ProcessPoolExecutor | None = None


def get_executor() -> ProcessPoolExecutor:
    global _execution_executor
    if _execution_executor is None:
        ctx = multiprocessing.get_context("spawn")
        _execution_executor = ProcessPoolExecutor(max_workers=4, mp_context=ctx)
    return _execution_executor


def _worker_execute_langgraph(code: str) -> dict[str, Any]:
    """Helper function run inside the child process."""
    namespace: dict[str, Any] = {}
    try:
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


async def _run_ruff(args: list[str], stdin_data: str) -> str:
    """Helper to execute ruff as a subprocess and return stdout."""
    # Resolve local virtual env ruff if available
    exe_dir = Path(sys.executable).parent
    ruff_name = "ruff.exe" if sys.platform == "win32" else "ruff"
    local_ruff = exe_dir / ruff_name
    ruff_path = str(local_ruff) if local_ruff.exists() else (shutil.which("ruff") or "ruff")

    try:
        process = await asyncio.create_subprocess_exec(
            ruff_path,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate(input=stdin_data.encode("utf-8"))
        if process.returncode == 0 or args[0] == "check":
            return stdout.decode("utf-8")
    except Exception:
        pass
    return ""


# AST Translation Maps & Utilities
TYPE_MAP_GB_TO_PY = {
    "number": "int",
    "float": "float",
    "boolean": "bool",
    "string": "str",
}

DEFAULT_TYPE_VALUES = {
    "number": 0,
    "float": 0.0,
    "boolean": False,
    "string": "",
}

MAP_COMPARE_OPS = {
    "==": ast.Eq(),
    "!=": ast.NotEq(),
    "<": ast.Lt(),
    "<=": ast.LtE(),
    ">": ast.Gt(),
    ">=": ast.GtE(),
    "in": ast.In(),
    "not in": ast.NotIn(),
    "is": ast.Is(),
    "is not": ast.IsNot(),
}

MAP_BIN_OPS = {
    "+": ast.Add(),
    "-": ast.Sub(),
    "*": ast.Mult(),
    "/": ast.Div(),
    "//": ast.FloorDiv(),
    "%": ast.Mod(),
    "**": ast.Pow(),
}


def ast_expr_to_node(node: dict[str, Any] | None, default_fallback: str = "True") -> ast.expr:
    """Recursively converts a slot AST expression dict directly to a Python AST node."""
    if not node:
        return ast.parse(default_fallback, mode="eval").body

    kind = node.get("kind")
    if kind == "literal":
        return ast.Constant(value=node.get("value"))

    if kind == "stateRef":
        return ast.Call(
            func=ast.Attribute(value=ast.Name(id="state", ctx=ast.Load()), attr="get", ctx=ast.Load()),
            args=[ast.Constant(value=node.get("varKey", ""))],
            keywords=[],
        )

    if kind == "binaryOp":
        op_str = node.get("op", "==")
        left = ast_expr_to_node(node.get("left"), default_fallback)
        right = ast_expr_to_node(node.get("right"), default_fallback)

        if op_str in MAP_COMPARE_OPS:
            return ast.Compare(left=left, ops=[MAP_COMPARE_OPS[op_str]], comparators=[right])
        if op_str in MAP_BIN_OPS:
            return ast.BinOp(left=left, op=MAP_BIN_OPS[op_str], right=right)
        return ast.Compare(left=left, ops=[ast.Eq()], comparators=[right])

    if kind == "unaryOp":
        op_str = node.get("op", "not")
        expr = ast_expr_to_node(node.get("expr"), default_fallback)
        op_map = {"not": ast.Not(), "-": ast.USub(), "+": ast.UAdd()}
        return ast.UnaryOp(op=op_map.get(op_str, ast.Not()), operand=expr)

    return ast.parse(default_fallback, mode="eval").body


def ast_expr_to_py(node: dict[str, Any] | None, default_fallback: str = "True") -> str:
    """Recursively converts a slot AST expression dict to Python code string using AST unparsing."""
    return ast.unparse(ast_expr_to_node(node, default_fallback))


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


# AST Node Compilers
def _compile_ast_dict_returning_node(node_id: str, items: list[Any], valid_keys: set[str]) -> ast.FunctionDef:
    """Unifies step/mutation node and logical assigner node generation by building dict-return ASTs."""
    keys: list[ast.expr | None] = []
    values: list[ast.expr] = []
    for item in items:
        target = item.target_var_key
        if target and target in valid_keys:
            keys.append(ast.Constant(value=target))
            expr = getattr(item, "expression", None)
            if expr is not None:
                values.append(ast_expr_to_node(expr))
            else:
                val = getattr(item, "value", None)
                values.append(ast.Constant(value=val))

    func_def = ast.parse("def _stub(state: State) -> dict: pass").body[0]
    assert isinstance(func_def, ast.FunctionDef)
    func_def.name = node_id
    func_def.body = [ast.Return(value=ast.Dict(keys=keys, values=values))]
    return func_def


def compile_ast_step_node(node_id: str, slots: list[Any], valid_keys: set[str]) -> ast.FunctionDef:
    return _compile_ast_dict_returning_node(node_id, slots, valid_keys)


def compile_ast_logical_node(node_id: str, assignments: list[Any], valid_keys: set[str]) -> ast.FunctionDef:
    return _compile_ast_dict_returning_node(node_id, assignments, valid_keys)


def compile_ast_switch_node(node_id: str, slots: list[Any], valid_keys: set[str]) -> list[ast.stmt]:
    node_func = ast.parse("def _stub_node(state: State) -> None: pass").body[0]
    assert isinstance(node_func, ast.FunctionDef)
    node_func.name = f"{node_id}_node"

    def build_if_chain(index: int) -> list[ast.stmt]:
        if index >= len(slots):
            res: list[ast.stmt] = [ast.Return(value=ast.Constant(value=""))]
            return res

        slot = slots[index]
        label = slot.raw_string or f"Slot {index + 1}"
        test_node = ast_expr_to_node(slot.expression, default_fallback="False")
        body_node: list[ast.stmt] = [ast.Return(value=ast.Constant(value=label))]
        orelse_node = build_if_chain(index + 1)

        return [ast.If(test=test_node, body=body_node, orelse=orelse_node)]

    router_func = ast.parse("def _stub(state: State) -> str: pass").body[0]
    assert isinstance(router_func, ast.FunctionDef)
    router_func.name = node_id
    router_func.body = build_if_chain(0)

    return [node_func, router_func]


# Flow Verification & Compilation
def validate_flow_data(flow_data: GraphFlowData) -> list[DiagnosticRead]:
    diagnostics = []
    valid_keys = {var.key for op in flow_data.operations.definer for var in op.variables if var.key}
    logical_ops_map = {op.id: op.assignments for op in flow_data.operations.logical}

    for node in flow_data.nodes:
        if node.node_type == "STEP":
            for slot in node.slots:
                if slot.target_var_key and slot.target_var_key not in valid_keys:
                    diagnostics.append(
                        DiagnosticRead(
                            line=1,
                            column=1,
                            code="E001",
                            severity="error",
                            message=f"Invalid mutation target: variable '{slot.target_var_key}' is missing or deleted.",
                            node_id=node.id,
                            slot_id=slot.id,
                        )
                    )

        elif node.node_type == "LOGICAL_ASSIGNER":
            assignments = logical_ops_map.get(node.ref_id or "") or []
            for asgn in assignments:
                if asgn.target_var_key and asgn.target_var_key not in valid_keys:
                    diagnostics.append(
                        DiagnosticRead(
                            line=1,
                            column=1,
                            code="E002",
                            severity="error",
                            message=f"Invalid assignment target: variable '{asgn.target_var_key}' is missing or deleted.",
                            node_id=node.id,
                            slot_id=asgn.id,
                        )
                    )

        elif node.node_type == "SWITCH":
            for slot in node.slots:
                if slot.expression:
                    for invalid_var in _find_invalid_state_refs(slot.expression, valid_keys):
                        diagnostics.append(
                            DiagnosticRead(
                                line=1,
                                column=1,
                                code="E003",
                                severity="error",
                                message=f"Invalid state reference: variable '{invalid_var}' is missing or deleted.",
                                node_id=node.id,
                                slot_id=slot.id,
                            )
                        )

    return diagnostics


async def generate_graph_code(payload: dict[str, Any] | GraphFlowData) -> str:
    if isinstance(payload, dict):
        legacy_schema = payload.get("state_schema") or []
        flow_data = GraphFlowData.model_validate(payload)
    else:
        legacy_schema = []
        flow_data = payload

    all_variables = [var for op in flow_data.operations.definer for var in op.variables]

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

    # State Definition Block
    if all_variables:
        vars_str = "\n".join(f"    {v.key}: {TYPE_MAP_GB_TO_PY.get(v.type, 'str')}" for v in all_variables if v.key)
        defaults_str = "\n".join(
            f'    "{v.key}": {repr(v.default_value if v.default_value is not None else DEFAULT_TYPE_VALUES.get(v.type, ""))},'
            for v in all_variables
            if v.key
        )
        state_definition_str = f"class State(TypedDict):\n{vars_str}\n\ninitial_state: State = {{\n{defaults_str}\n}}"
    else:
        state_definition_str = "class State(TypedDict):\n    pass\n\ninitial_state: State = {}"

    # AST Nodes compilation
    logical_ops_map = {op.id: op.assignments for op in flow_data.operations.logical}
    executable_logic_nodes = [
        n for n in flow_data.nodes if n.node_type in ("STEP", "SWITCH", "LOGICAL_ASSIGNER", "AGENTIC_ASSIGNER")
    ]

    node_asts = []
    for node in executable_logic_nodes:
        if node.node_type == "SWITCH":
            node_asts.extend(compile_ast_switch_node(node.id, node.slots, valid_keys))
        elif node.node_type == "LOGICAL_ASSIGNER":
            assignments = logical_ops_map.get(node.ref_id or "") or []
            node_asts.append(compile_ast_logical_node(node.id, assignments, valid_keys))
        else:
            node_asts.append(compile_ast_step_node(node.id, node.slots, valid_keys))

    module_node = ast.Module(body=node_asts, type_ignores=[])
    ast.fix_missing_locations(module_node)
    node_definitions_str = ast.unparse(module_node)

    # Graph Definition Block
    workflow_lines = ["workflow = StateGraph(State)", ""]
    workflow_lines.extend(
        f'workflow.add_node("{n.id}", {n.id}_node)'
        if n.node_type == "SWITCH"
        else f'workflow.add_node("{n.id}", {n.id})'
        for n in executable_logic_nodes
    )
    workflow_lines.append("")

    definer_node_ids = {n.id for n in flow_data.nodes if n.node_type == "DEFINER"}

    def resolve_target(target_id: str, visited: set[str] | None = None) -> str:
        visited = visited or set()
        if target_id in visited:
            return "END"
        visited.add(target_id)

        if target_id in definer_node_ids:
            definer_out = next((e for e in flow_data.edges if e.source_id == target_id), None)
            return resolve_target(definer_out.target_id, visited) if definer_out else "END"
        return "END" if target_id == "end" else f'"{target_id}"'

    workflow_lines.extend(
        f"workflow.add_edge(START, {resolve_target(e.target_id)})" for e in flow_data.edges if e.source_id == "start"
    )

    static_edges = [
        e
        for e in flow_data.edges
        if e.source_id != "start"
        and e.source_id not in definer_node_ids
        and e.source_type == "node"
        and e.target_id != "start"
    ]
    workflow_lines.extend(f'workflow.add_edge("{e.source_id}", {resolve_target(e.target_id)})' for e in static_edges)
    workflow_lines.append("")

    for switch in [n for n in executable_logic_nodes if n.node_type == "SWITCH"]:
        routing_edges = [e for e in flow_data.edges if e.source_id in {s.id for s in switch.slots}]
        if routing_edges:
            slot_map = {
                s.raw_string: resolve_target(e.target_id)
                for s in switch.slots
                for e in routing_edges
                if e.source_id == s.id
            }
            slot_map_str = ", ".join(f'"{k}": {v}' for k, v in slot_map.items())
            workflow_lines.append(f'workflow.add_conditional_edges("{switch.id}", {switch.id}, {{{slot_map_str}}})')

    workflow_lines.extend(["", "app = workflow.compile()"])
    workflow_definition_str = "\n".join(workflow_lines)

    template = textwrap.dedent(
        """\
        from typing import TypedDict, Literal, Any
        from langgraph.graph import StateGraph, START, END

        # ----------------------------------------------------
        # State Definition
        # ----------------------------------------------------
        {state_definition}

        # ----------------------------------------------------
        # Nodes
        # ----------------------------------------------------
        {node_definitions}

        # ----------------------------------------------------
        # Graph Definition
        # ----------------------------------------------------
        {workflow_definition}
        """
    )
    generated_code = template.format(
        state_definition=state_definition_str,
        node_definitions=node_definitions_str,
        workflow_definition=workflow_definition_str,
    )

    formatted = await _run_ruff(["format", "-"], generated_code)
    return formatted or generated_code


async def run_ruff_diagnostics(code: str) -> list[DiagnosticRead]:
    if not code.strip():
        return []

    stdout = await _run_ruff(["check", "--output-format=json", "-"], code)
    if not stdout:
        return []

    try:
        data = json.loads(stdout)
        return [
            DiagnosticRead(
                line=item.get("location", {}).get("row", 1),
                column=item.get("location", {}).get("column", 1),
                code=item.get("code", "UNK"),
                message=item.get("message", ""),
                severity="warning" if item.get("code", "").startswith("W") else "error",
            )
            for item in data
        ]
    except Exception:
        return []


async def compile_flow_with_langgraph(payload: dict[str, Any] | GraphFlowData) -> dict[str, Any]:
    """
    Compiles the flow payload into executable python code, executes it,
    runs the compiled LangGraph workflow with its initial state, and returns the final state.
    """
    flow_data = payload if isinstance(payload, GraphFlowData) else GraphFlowData.model_validate(payload)

    errors = validate_flow_data(flow_data)
    severe_errors = [e for e in errors if e.severity == "error"]
    if severe_errors:
        err_msg = "; ".join(e.message for e in severe_errors)
        return {"variables": [], "error": f"Compilation/Execution failed: {err_msg}"}

    try:
        code = await generate_graph_code(flow_data)
    except Exception as e:
        return {"variables": [], "error": f"Compilation/Execution failed: {str(e)}"}

    loop = asyncio.get_running_loop()
    executor = get_executor()
    try:
        result = await asyncio.wait_for(loop.run_in_executor(executor, _worker_execute_langgraph, code), timeout=5.0)
        return result
    except TimeoutError:
        return {"variables": [], "error": "LangGraph execution timed out (possible infinite loop in visual graph)"}
    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}
