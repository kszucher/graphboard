"""=============================================================================
PURE AST COMPILER WARNING
=============================================================================
This module generates code using Pure Python AST (`ast.Module`, `ast.parse`,
`ast.Call`, `ast.Dict`).

DO NOT revert to raw string formatting for code logic or graph generation.
ANY FURTHER CHANGES MUST STRICTLY ADHERE TO GENERATING FULL PURE AST NODES.
============================================================================="""

import ast
import asyncio
import json
import multiprocessing
import shutil
import sys
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from app.graphs.schemas import DiagnosticRead, GraphFlowData, SlotRead
from app.graphs.validation import validate_flow_data

_execution_executor: ProcessPoolExecutor | None = None

TYPE_MAP_GB_TO_PY = {"number": "int", "float": "float", "boolean": "bool", "string": "str"}
DEFAULT_TYPE_VALUES = {"number": 0, "float": 0.0, "boolean": False, "string": ""}
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


def get_executor() -> ProcessPoolExecutor:
    global _execution_executor
    if _execution_executor is None:
        _execution_executor = ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn"))
    return _execution_executor


def _resolve_ruff_path() -> str:
    exe_dir = Path(sys.executable).parent
    ruff_name = "ruff.exe" if sys.platform == "win32" else "ruff"
    local_ruff = exe_dir / ruff_name
    if not local_ruff.exists():
        try:
            local_ruff = (
                Path(__file__).resolve().parents[2]
                / ".venv"
                / ("Scripts" if sys.platform == "win32" else "bin")
                / ruff_name
            )
        except Exception:
            pass
    return str(local_ruff) if local_ruff.exists() else (shutil.which("ruff") or "ruff")


async def _run_ruff(args: list[str], stdin_data: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            _resolve_ruff_path(),
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=stdin_data.encode("utf-8"))
        if proc.returncode == 0 or (args and args[0] == "check"):
            return stdout.decode("utf-8")
        print(f"Ruff failed code {proc.returncode}: {stderr.decode('utf-8')}", file=sys.stderr)
    except Exception as e:
        print(f"Ruff execution error: {e}", file=sys.stderr)
    return ""


# ----------------------------------------------------
# AST Helpers & Building Shortcuts
# ----------------------------------------------------
def _ref(node_id: str) -> ast.expr:
    return ast.Name(id=node_id, ctx=ast.Load()) if node_id in ("START", "END") else ast.Constant(value=node_id)


def _call(func_expr: str, *args: ast.expr) -> ast.Expr:
    """Helper to convert 'obj.method' string into an ast.Expr(ast.Call(...)) node."""
    parts = func_expr.split(".")
    obj = ast.Name(id=parts[0], ctx=ast.Load())
    func = ast.Attribute(value=obj, attr=parts[1], ctx=ast.Load()) if len(parts) > 1 else obj
    return ast.Expr(value=ast.Call(func=func, args=list(args), keywords=[]))


def ast_expr_to_node(node: dict[str, Any] | None, default_fallback: str = "True") -> ast.expr:
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
        left, right = (
            ast_expr_to_node(node.get("left"), default_fallback),
            ast_expr_to_node(node.get("right"), default_fallback),
        )
        return (
            ast.Compare(left=left, ops=[MAP_COMPARE_OPS.get(op_str, ast.Eq())], comparators=[right])
            if op_str in MAP_COMPARE_OPS
            else ast.BinOp(left=left, op=MAP_BIN_OPS[op_str], right=right)
        )
    if kind == "unaryOp":
        return ast.UnaryOp(
            op={"not": ast.Not(), "-": ast.USub(), "+": ast.UAdd()}.get(node.get("op", "not"), ast.Not()),
            operand=ast_expr_to_node(node.get("expr"), default_fallback),
        )
    return ast.parse(default_fallback, mode="eval").body


def compile_ast_dict_returning_node(node_id: str, items: list[Any], valid_keys: set[str]) -> ast.FunctionDef:
    keys = [
        ast.Constant(value=getattr(i, "target_var_key"))
        for i in items
        if getattr(i, "target_var_key", None) in valid_keys
    ]
    values = [
        ast_expr_to_node(getattr(i, "expression"))
        if getattr(i, "expression", None) is not None
        else ast.Constant(value=getattr(i, "value", None))
        for i in items
        if getattr(i, "target_var_key", None) in valid_keys
    ]
    func = ast.FunctionDef(
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
    return ast.fix_missing_locations(func)


def compile_ast_switch_node(node_id: str, slots: list[SlotRead]) -> ast.FunctionDef:
    def build_if(idx: int) -> list[ast.stmt]:
        if idx >= len(slots):
            return [ast.Return(value=ast.Constant(value=""))]
        return [
            ast.If(
                test=ast_expr_to_node(slots[idx].expression, "False"),
                body=[ast.Return(value=ast.Constant(value=slots[idx].raw_string or f"Slot {idx + 1}"))],
                orelse=build_if(idx + 1),
            )
        ]

    func = ast.FunctionDef(
        name=node_id,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg="state", annotation=ast.Name(id="State", ctx=ast.Load()))],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=build_if(0),
        decorator_list=[],
        returns=ast.Name(id="str", ctx=ast.Load()),
    )
    return ast.fix_missing_locations(func)


# ----------------------------------------------------
# Pure AST LangGraph Compiler
# ----------------------------------------------------
class PureAstLangGraphCompiler:
    def __init__(self, flow_data: GraphFlowData):
        self.flow_data = flow_data
        self.all_variables = [v for op in flow_data.operations.definer for v in op.variables if v.key]
        self.valid_keys = {v.key for v in self.all_variables}
        self.definer_ids = {n.id for n in flow_data.nodes if n.node_type == "DEFINER"}
        self.executable_nodes = [
            n for n in flow_data.nodes if n.node_type in ("STEP", "SWITCH", "LOGICAL_ASSIGNER", "AGENTIC_ASSIGNER")
        ]
        self.switch_nodes = {n.id: n for n in self.executable_nodes if n.node_type == "SWITCH"}

    def resolve_target_id(self, target_id: str, visited: set[str] | None = None) -> str:
        visited = visited or set()
        if target_id in visited or target_id == "end":
            return "END"
        visited.add(target_id)
        if target_id in self.definer_ids:
            out_edge = next((e for e in self.flow_data.edges if e.source_id == target_id), None)
            return self.resolve_target_id(out_edge.target_id, visited) if out_edge else "END"
        return target_id

    def build_state_ast(self) -> list[ast.stmt]:
        if not self.all_variables:
            return ast.parse("class State(TypedDict):\n    pass\ninitial_state: State = {}").body

        anns = [
            ast.AnnAssign(
                target=ast.Name(id=v.key, ctx=ast.Store()),
                annotation=ast.Name(id=TYPE_MAP_GB_TO_PY.get(v.type, "str"), ctx=ast.Load()),
                value=None,
                simple=1,
            )
            for v in self.all_variables
        ]
        cls_def = ast.ClassDef(
            name="State", bases=[ast.Name(id="TypedDict", ctx=ast.Load())], keywords=[], body=anns, decorator_list=[]
        )
        init_state = ast.Assign(
            targets=[ast.Name(id="initial_state", ctx=ast.Store())],
            value=ast.Dict(
                keys=[ast.Constant(value=v.key) for v in self.all_variables],
                values=[
                    ast.Constant(
                        value=v.default_value if v.default_value is not None else DEFAULT_TYPE_VALUES.get(v.type, "")
                    )
                    for v in self.all_variables
                ],
            ),
        )
        return [cls_def, init_state]

    def build_workflow_ast(self) -> list[ast.stmt]:
        stmts: list[ast.stmt] = [
            ast.Assign(
                targets=[ast.Name(id="workflow", ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Name(id="StateGraph", ctx=ast.Load()),
                    args=[ast.Name(id="State", ctx=ast.Load())],
                    keywords=[],
                ),
            )
        ]

        switch_sources: dict[str, list[str]] = {sid: [] for sid in self.switch_nodes}
        edges_to_switches: set[uuid.UUID] = set()
        for e in self.flow_data.edges:
            tid = self.resolve_target_id(e.target_id)
            if tid in self.switch_nodes:
                edges_to_switches.add(e.id)
                switch_sources[tid].append("START" if e.source_id == "start" else e.source_id)

        # Add Nodes
        for n in self.executable_nodes:
            if n.node_type == "SWITCH" and not switch_sources[n.id]:
                stmts.append(
                    _call(
                        "workflow.add_node",
                        ast.Constant(value=n.id),
                        ast.Lambda(
                            args=ast.arguments(
                                posonlyargs=[], args=[ast.arg(arg="state")], kwonlyargs=[], kw_defaults=[], defaults=[]
                            ),
                            body=ast.Constant(value=None),
                        ),
                    )
                )
            elif n.node_type != "SWITCH":
                stmts.append(_call("workflow.add_node", ast.Constant(value=n.id), ast.Name(id=n.id, ctx=ast.Load())))

        # Add Edges
        for e in self.flow_data.edges:
            if e.id in edges_to_switches or e.target_id == "start":
                continue
            if e.source_id == "start":
                stmts.append(
                    _call(
                        "workflow.add_edge",
                        ast.Name(id="START", ctx=ast.Load()),
                        _ref(self.resolve_target_id(e.target_id)),
                    )
                )
            elif e.source_id not in self.definer_ids and e.source_type == "node":
                stmts.append(
                    _call(
                        "workflow.add_edge", ast.Constant(value=e.source_id), _ref(self.resolve_target_id(e.target_id))
                    )
                )

        # Conditional Edges
        for switch in self.switch_nodes.values():
            routing_edges = [e for e in self.flow_data.edges if e.source_id in {s.id for s in switch.slots}]
            if not routing_edges:
                continue
            slot_map = {
                s.raw_string: _ref(self.resolve_target_id(e.target_id))
                for s in switch.slots
                for e in routing_edges
                if e.source_id == s.id
            }
            keys = [ast.Constant(value=k) for k in slot_map.keys()]
            vals = list(slot_map.values())
            for source in switch_sources[switch.id] or [switch.id]:
                stmts.append(
                    _call(
                        "workflow.add_conditional_edges",
                        _ref(source),
                        ast.Name(id=switch.id, ctx=ast.Load()),
                        ast.Dict(keys=keys, values=vals),
                    )
                )

        stmts.append(
            ast.Assign(
                targets=[ast.Name(id="app", ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id="workflow", ctx=ast.Load()), attr="compile", ctx=ast.Load()),
                    args=[],
                    keywords=[],
                ),
            )
        )
        return stmts

    def compile(self) -> str:
        imports = ast.parse(
            "from typing import TypedDict, Literal, Any\nfrom langgraph.graph import StateGraph, START, END"
        ).body
        logical_ops = {op.id: op.assignments for op in self.flow_data.operations.logical}
        nodes = [
            compile_ast_switch_node(n.id, n.slots)
            if n.node_type == "SWITCH"
            else compile_ast_dict_returning_node(n.id, logical_ops.get(n.ref_id or "") or [], self.valid_keys)
            if n.node_type == "LOGICAL_ASSIGNER"
            else compile_ast_dict_returning_node(n.id, n.slots, self.valid_keys)
            for n in self.executable_nodes
        ]

        mod = ast.Module(body=imports + self.build_state_ast() + nodes + self.build_workflow_ast(), type_ignores=[])
        return ast.unparse(ast.fix_missing_locations(mod))


async def generate_graph_code(flow_data: GraphFlowData) -> str:
    formatted = await _run_ruff(["format", "-"], PureAstLangGraphCompiler(flow_data).compile())
    return formatted or PureAstLangGraphCompiler(flow_data).compile()


# ----------------------------------------------------
# Worker Execution & Diagnostics
# ----------------------------------------------------
def _worker_execute_langgraph(code: str) -> dict[str, Any]:
    exec_globals: dict[str, Any] = {}
    try:
        exec(code, exec_globals)
    except Exception as e:
        return {"variables": [], "error": f"Compilation/Execution failed: {str(e)}"}

    app = exec_globals.get("app")
    if not app:
        return {"variables": [], "error": "Compiled workflow does not define 'app'"}

    try:
        final_state = app.invoke(exec_globals.get("initial_state", {}))
        return {"variables": [{"key": k, "value": v} for k, v in final_state.items()]}
    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}


async def run_ruff_diagnostics(code: str) -> list[DiagnosticRead]:
    if not code.strip():
        return []
    stdout = await _run_ruff(["check", "--output-format=json", "-"], code)
    if not stdout:
        return []
    try:
        return [
            DiagnosticRead(
                line=item.get("location", {}).get("row", 1),
                column=item.get("location", {}).get("column", 1),
                code=item.get("code", "UNK"),
                message=item.get("message", ""),
                severity="error" if item.get("code", "").startswith(("E", "F")) else "warning",
            )
            for item in json.loads(stdout)
        ]
    except Exception:
        return []


async def compile_flow_with_langgraph(flow_data: GraphFlowData) -> dict[str, Any]:
    errors = validate_flow_data(flow_data)
    severe_errors = [e for e in errors if e.severity == "error"]
    if severe_errors:
        return {
            "variables": [],
            "error": f"Compilation/Execution failed: {'; '.join(e.message for e in severe_errors)}",
        }

    try:
        code = await generate_graph_code(flow_data)
        return await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(get_executor(), _worker_execute_langgraph, code), timeout=5.0
        )
    except TimeoutError:
        return {"variables": [], "error": "LangGraph execution timed out (possible infinite loop in visual graph)"}
    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}
