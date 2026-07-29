import ast
import asyncio
import json
import multiprocessing
import shutil
import sys
import textwrap
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Literal, Protocol

from app.graphs.schemas import (
    DiagnosticRead,
    GraphFlowData,
    SlotRead,
)
from app.graphs.validation import validate_flow_data

# ----------------------------------------------------
# Global Constants & Type Mapping
# ----------------------------------------------------
_execution_executor: ProcessPoolExecutor | None = None

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


# ----------------------------------------------------
# Process / Tool Support Helpers
# ----------------------------------------------------
def get_executor() -> ProcessPoolExecutor:
    global _execution_executor
    if _execution_executor is None:
        ctx = multiprocessing.get_context("spawn")
        _execution_executor = ProcessPoolExecutor(max_workers=4, mp_context=ctx)
    return _execution_executor


def _resolve_ruff_path() -> str:
    exe_dir = Path(sys.executable).parent
    ruff_name = "ruff.exe" if sys.platform == "win32" else "ruff"
    local_ruff = exe_dir / ruff_name

    if not local_ruff.exists():
        try:
            project_root = Path(__file__).resolve().parents[2]
            bin_dir = "Scripts" if sys.platform == "win32" else "bin"
            local_ruff = project_root / ".venv" / bin_dir / ruff_name
        except Exception:
            pass

    return str(local_ruff) if local_ruff.exists() else (shutil.which("ruff") or "ruff")


async def _run_ruff(args: list[str], stdin_data: str) -> str:
    ruff_path = _resolve_ruff_path()
    try:
        process = await asyncio.create_subprocess_exec(
            ruff_path,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(input=stdin_data.encode("utf-8"))
        if process.returncode == 0 or (args and args[0] == "check"):
            return stdout.decode("utf-8")

        print(
            f"Ruff failed with return code {process.returncode}. Stderr: {stderr.decode('utf-8')}",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"Ruff execution error: {e}", file=sys.stderr)
    return ""


# ----------------------------------------------------
# AST Building & Code Compiler
# ----------------------------------------------------
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


class AssignmentItem(Protocol):
    target_var_key: str | None
    expression: dict[str, Any] | None
    value: Any | None


def compile_ast_dict_returning_node(node_id: str, items: list[Any], valid_keys: set[str]) -> ast.FunctionDef:
    """Generates state mutation Python functions return-value dictionaries."""
    keys: list[ast.expr | None] = []
    values: list[ast.expr] = []

    for item in items:
        target = getattr(item, "target_var_key", None)
        if target and target in valid_keys:
            keys.append(ast.Constant(value=target))
            expr = getattr(item, "expression", None)
            if expr is not None:
                values.append(ast_expr_to_node(expr))
            else:
                values.append(ast.Constant(value=getattr(item, "value", None)))

    func_node = ast.FunctionDef(
        name=node_id,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg="state", annotation=ast.Name(id="State", ctx=ast.Load()))],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=[ast.Return(value=ast.Dict(keys=keys, values=values))],
        decorator_list=[],
        returns=ast.Name(id="dict", ctx=ast.Load()),
    )
    return ast.fix_missing_locations(func_node)


def compile_ast_switch_node(node_id: str, slots: list[SlotRead]) -> ast.FunctionDef:
    """Compiles a SWITCH node into a string-returning conditional router function."""

    def build_if_chain(index: int) -> list[ast.stmt]:
        if index >= len(slots):
            return [ast.Return(value=ast.Constant(value=""))]

        slot = slots[index]
        label = slot.raw_string or f"Slot {index + 1}"
        test_node = ast_expr_to_node(slot.expression, default_fallback="False")

        return [
            ast.If(
                test=test_node,
                body=[ast.Return(value=ast.Constant(value=label))],
                orelse=build_if_chain(index + 1),
            )
        ]

    func_node = ast.FunctionDef(
        name=node_id,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg="state", annotation=ast.Name(id="State", ctx=ast.Load()))],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=build_if_chain(0),
        decorator_list=[],
        returns=ast.Name(id="str", ctx=ast.Load()),
    )
    return ast.fix_missing_locations(func_node)


class LangGraphCompiler:
    """Translates UI GraphFlowData payloads into standard LangGraph python files."""

    def __init__(self, flow_data: GraphFlowData):
        self.flow_data = flow_data
        self.all_variables = [var for op in flow_data.operations.definer for var in op.variables]
        self.valid_keys = {var.key for var in self.all_variables if var.key}
        self.definer_node_ids = {n.id for n in flow_data.nodes if n.node_type == "DEFINER"}

        self.executable_nodes = [
            n for n in flow_data.nodes if n.node_type in ("STEP", "SWITCH", "LOGICAL_ASSIGNER", "AGENTIC_ASSIGNER")
        ]
        self.switch_nodes = {n.id: n for n in self.executable_nodes if n.node_type == "SWITCH"}

    def resolve_target(self, target_id: str, visited: set[str] | None = None) -> str:
        """Resolves bypass/definer nodes to actual functional execution targets or END."""
        visited = visited or set()
        if target_id in visited or target_id == "end":
            return "END"
        visited.add(target_id)

        if target_id in self.definer_node_ids:
            out_edge = next((e for e in self.flow_data.edges if e.source_id == target_id), None)
            return self.resolve_target(out_edge.target_id, visited) if out_edge else "END"

        return f'"{target_id}"'

    def build_state_code(self) -> str:
        if not self.valid_keys:
            return "class State(TypedDict):\n    pass\n\ninitial_state: State = {}"

        var_annotations = [f"    {v.key}: {TYPE_MAP_GB_TO_PY.get(v.type, 'str')}" for v in self.all_variables if v.key]
        defaults = [
            f'    "{v.key}": {repr(v.default_value if v.default_value is not None else DEFAULT_TYPE_VALUES.get(v.type, ""))},'
            for v in self.all_variables
            if v.key
        ]

        return (
            "class State(TypedDict):\n"
            + "\n".join(var_annotations)
            + "\n\ninitial_state: State = {\n"
            + "\n".join(defaults)
            + "\n}"
        )

    def build_node_code(self) -> str:
        logical_ops = {op.id: op.assignments for op in self.flow_data.operations.logical}
        node_asts = []

        for node in self.executable_nodes:
            if node.node_type == "SWITCH":
                node_asts.append(compile_ast_switch_node(node.id, node.slots))
            elif node.node_type == "LOGICAL_ASSIGNER":
                assignments = logical_ops.get(node.ref_id or "") or []
                node_asts.append(compile_ast_dict_returning_node(node.id, assignments, self.valid_keys))
            else:
                node_asts.append(compile_ast_dict_returning_node(node.id, node.slots, self.valid_keys))

        return "\n\n\n".join(ast.unparse(ast_node) for ast_node in node_asts)

    def build_workflow_code(self) -> str:
        lines = ["workflow = StateGraph(State)", ""]
        switch_sources: dict[str, list[str]] = {sid: [] for sid in self.switch_nodes}
        edges_to_switches: set[uuid.UUID] = set()

        # Map edges to switches
        for e in self.flow_data.edges:
            target = self.resolve_target(e.target_id)
            if target.startswith('"') and target.endswith('"'):
                raw_target_id = target[1:-1]
                if raw_target_id in self.switch_nodes:
                    edges_to_switches.add(e.id)
                    source = "START" if e.source_id == "start" else f'"{e.source_id}"'
                    switch_sources[raw_target_id].append(source)

        # 1. Add Execution Nodes
        for n in self.executable_nodes:
            if n.node_type == "SWITCH":
                if not switch_sources[n.id]:  # Orphaned switch fallback
                    lines.append(f'workflow.add_node("{n.id}", lambda state: None)')
            else:
                lines.append(f'workflow.add_node("{n.id}", {n.id})')
        lines.append("")

        # 2. Add Standard Edges
        start_edges = [e for e in self.flow_data.edges if e.source_id == "start" and e.id not in edges_to_switches]
        static_edges = [
            e
            for e in self.flow_data.edges
            if e.source_id != "start"
            and e.source_id not in self.definer_node_ids
            and e.source_type == "node"
            and e.target_id != "start"
            and e.id not in edges_to_switches
        ]

        lines.extend(f"workflow.add_edge(START, {self.resolve_target(e.target_id)})" for e in start_edges)
        lines.extend(f'workflow.add_edge("{e.source_id}", {self.resolve_target(e.target_id)})' for e in static_edges)
        lines.append("")

        # 3. Add Conditional Router Edges
        for switch in self.switch_nodes.values():
            routing_edges = [e for e in self.flow_data.edges if e.source_id in {s.id for s in switch.slots}]
            if not routing_edges:
                continue

            slot_map = {
                s.raw_string: self.resolve_target(e.target_id)
                for s in switch.slots
                for e in routing_edges
                if e.source_id == s.id
            }

            path_map_lines = [f'        "{k}": {v},' for k, v in slot_map.items()]
            sources = switch_sources[switch.id] or [f'"{switch.id}"']

            for source in sources:
                lines.append("workflow.add_conditional_edges(")
                lines.append(f"    {source},")
                lines.append(f"    {switch.id},")
                lines.append("    {")
                lines.extend(path_map_lines)
                lines.append("    },")
                lines.append(")")
                lines.append("")

        lines.extend(["", "app = workflow.compile()"])
        return "\n".join(lines)

    def compile(self) -> str:
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
        return template.format(
            state_definition=self.build_state_code(),
            node_definitions=self.build_node_code(),
            workflow_definition=self.build_workflow_code(),
        )


async def generate_graph_code(flow_data: GraphFlowData) -> str:
    compiler = LangGraphCompiler(flow_data)
    generated_code = compiler.compile()
    formatted = await _run_ruff(["format", "-"], generated_code)
    return formatted or generated_code


# ----------------------------------------------------
# Worker Execution & Diagnostics
# ----------------------------------------------------
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
                severity=cast_severity(item.get("code", "")),
            )
            for item in data
        ]
    except Exception:
        return []


def cast_severity(code_str: str) -> Literal["error", "warning"]:
    return "error" if code_str.startswith(("E", "F")) else "warning"


async def compile_flow_with_langgraph(flow_data: GraphFlowData) -> dict[str, Any]:
    """Compiles the flow payload into executable python code, executes it,

    runs the compiled LangGraph workflow with its initial state, and returns the final state.
    """
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
        return await asyncio.wait_for(
            loop.run_in_executor(executor, _worker_execute_langgraph, code),
            timeout=5.0,
        )
    except TimeoutError:
        return {"variables": [], "error": "LangGraph execution timed out (possible infinite loop in visual graph)"}
    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}
