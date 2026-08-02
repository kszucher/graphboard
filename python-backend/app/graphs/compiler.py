"""=============================================================================
PURE AST COMPILER
=============================================================================
Translates GraphFlowData directly to executable Python AST.
Frontend (CodeMirror / Prettier) handles all visual code formatting.
============================================================================="""

import ast
import asyncio
import multiprocessing
import uuid
from concurrent.futures import ProcessPoolExecutor
from typing import Any, cast

from app.constants import NodeType
from app.graphs.schemas import (
    AgenticAssignerNode,
    DefinerVariableSchema,
    GraphFlowData,
    LogicalAssignerNode,
    NodeRead,
    SlotRead,
    SwitchNode,
)

try:
    import black
except ImportError:
    black = None  # type: ignore[assignment]


_execution_executor: ProcessPoolExecutor | None = None

TYPE_MAP = {"number": "int", "float": "float", "boolean": "bool", "string": "str"}
DEFAULT_VALUES = {"number": 0, "float": 0.0, "boolean": False, "string": ""}
COMPARE_OPS = {
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
BIN_OPS = {
    "+": ast.Add(),
    "-": ast.Sub(),
    "*": ast.Mult(),
    "/": ast.Div(),
    "//": ast.FloorDiv(),
    "%": ast.Mod(),
    "**": ast.Pow(),
}
UNARY_OPS = {
    "not": ast.Not(),
    "-": ast.USub(),
    "+": ast.UAdd(),
}


def get_executor() -> ProcessPoolExecutor:
    global _execution_executor
    if _execution_executor is None:
        _execution_executor = ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn"))
    return _execution_executor


def _ref(node_id: str) -> ast.expr:
    return ast.Name(id=node_id, ctx=ast.Load()) if node_id in ("START", "END") else ast.Constant(value=node_id)


def _call(func_expr: str, *args: ast.expr) -> ast.Expr:
    parts = func_expr.split(".")
    obj = ast.Name(id=parts[0], ctx=ast.Load())
    func = ast.Attribute(value=obj, attr=parts[1], ctx=ast.Load()) if len(parts) > 1 else obj
    return ast.Expr(value=ast.Call(func=func, args=list(args), keywords=[]))


def ast_expr_to_node(node: dict[str, Any] | None, fallback: str = "True") -> ast.expr:
    if not node:
        return ast.parse(fallback, mode="eval").body

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
        op = node.get("op", "==")
        left, right = ast_expr_to_node(node.get("left"), fallback), ast_expr_to_node(node.get("right"), fallback)
        return (
            ast.Compare(left=left, ops=[COMPARE_OPS[op]], comparators=[right])
            if op in COMPARE_OPS
            else ast.BinOp(left=left, op=BIN_OPS.get(op, ast.Add()), right=right)
        )
    if kind == "unaryOp":
        op_str = node.get("op", "not")
        return ast.UnaryOp(
            op=UNARY_OPS.get(op_str, ast.Not()),
            operand=ast_expr_to_node(node.get("expr"), fallback),
        )

    return ast.parse(fallback, mode="eval").body


def compile_ast_dict_returning_node(node_id: str, items: list[Any], valid_keys: set[str]) -> ast.FunctionDef:
    valid_items = [i for i in items if getattr(i, "target_var_key", None) in valid_keys]
    keys: list[ast.expr | None] = [ast.Constant(value=i.target_var_key) for i in valid_items]
    values = [
        ast_expr_to_node(getattr(i, "expression", None))
        if getattr(i, "expression", None) is not None
        else ast.Constant(value=getattr(i, "value", None))
        for i in valid_items
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


def compile_ast_agentic_node(
    node: AgenticAssignerNode,
    valid_keys: set[str],
    all_variables: list[DefinerVariableSchema],
) -> list[ast.stmt]:
    inputs = [k for k in (node.agentic_inputs or []) if k in valid_keys]
    outputs = [k for k in (node.agentic_outputs or []) if k in valid_keys]

    anns: list[ast.stmt] = []
    for var_key in outputs:
        var_type = "string"
        var_desc = None
        for v in all_variables:
            if v.key == var_key:
                var_type = v.type
                var_desc = v.description
                break

        py_type = TYPE_MAP.get(var_type, "str")
        val = None
        if var_desc:
            val = ast.Call(
                func=ast.Name(id="Field", ctx=ast.Load()),
                args=[],
                keywords=[ast.keyword(arg="description", value=ast.Constant(value=var_desc))],
            )

        anns.append(
            ast.AnnAssign(
                target=ast.Name(id=var_key, ctx=ast.Store()),
                annotation=ast.Name(id=py_type, ctx=ast.Load()),
                value=val,
                simple=1,
            )
        )

    class_def = ast.ClassDef(
        name=f"{node.id}Output",
        bases=[ast.Name(id="BaseModel", ctx=ast.Load())],
        keywords=[],
        body=anns or [ast.Pass()],
        decorator_list=[],
    )

    body_stmts: list[ast.stmt] = [
        ast.Assign(
            targets=[ast.Name(id="client", ctx=ast.Store())],
            value=ast.Call(func=ast.Name(id="Groq", ctx=ast.Load()), args=[], keywords=[]),
        ),
        ast.Assign(
            targets=[ast.Name(id="prompt_text", ctx=ast.Store())],
            value=ast.Constant(value=node.prompt or ""),
        ),
    ]

    for k in inputs:
        replace_call = ast.Call(
            func=ast.Attribute(value=ast.Name(id="prompt_text", ctx=ast.Load()), attr="replace", ctx=ast.Load()),
            args=[
                ast.Constant(value=f"{{{k}}}"),
                ast.Call(
                    func=ast.Name(id="str", ctx=ast.Load()),
                    args=[
                        ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id="state", ctx=ast.Load()),
                                attr="get",
                                ctx=ast.Load(),
                            ),
                            args=[ast.Constant(value=k)],
                            keywords=[],
                        )
                    ],
                    keywords=[],
                ),
            ],
            keywords=[],
        )
        body_stmts.append(ast.Assign(targets=[ast.Name(id="prompt_text", ctx=ast.Store())], value=replace_call))

    parse_call = ast.Attribute(
        value=ast.Attribute(
            value=ast.Attribute(
                value=ast.Attribute(
                    value=ast.Name(id="client", ctx=ast.Load()),
                    attr="beta",
                    ctx=ast.Load(),
                ),
                attr="chat",
                ctx=ast.Load(),
            ),
            attr="completions",
            ctx=ast.Load(),
        ),
        attr="parse",
        ctx=ast.Load(),
    )

    chat_completion_val = ast.Call(
        func=parse_call,
        args=[],
        keywords=[
            ast.keyword(
                arg="messages",
                value=ast.List(
                    elts=[
                        ast.Dict(
                            keys=[ast.Constant(value="role"), ast.Constant(value="content")],
                            values=[ast.Constant(value="user"), ast.Name(id="prompt_text", ctx=ast.Load())],
                        )
                    ],
                    ctx=ast.Load(),
                ),
            ),
            ast.keyword(arg="model", value=ast.Constant(value="llama3-8b-8192")),
            ast.keyword(arg="response_format", value=ast.Name(id=f"{node.id}Output", ctx=ast.Load())),
        ],
    )

    body_stmts.append(
        ast.Assign(
            targets=[ast.Name(id="chat_completion", ctx=ast.Store())],
            value=chat_completion_val,
        )
    )

    res_val = ast.Attribute(
        value=ast.Attribute(
            value=ast.Subscript(
                value=ast.Attribute(
                    value=ast.Name(id="chat_completion", ctx=ast.Load()),
                    attr="choices",
                    ctx=ast.Load(),
                ),
                slice=ast.Constant(value=0),
                ctx=ast.Load(),
            ),
            attr="message",
            ctx=ast.Load(),
        ),
        attr="parsed",
        ctx=ast.Load(),
    )
    body_stmts.append(ast.Assign(targets=[ast.Name(id="res", ctx=ast.Store())], value=res_val))

    keys: list[ast.expr | None] = [ast.Constant(value=k) for k in outputs]
    values: list[ast.expr] = [
        ast.Attribute(value=ast.Name(id="res", ctx=ast.Load()), attr=k, ctx=ast.Load()) for k in outputs
    ]
    body_stmts.append(ast.Return(value=ast.Dict(keys=keys, values=values)))

    func_def = ast.FunctionDef(
        name=node.id,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg="state", annotation=ast.Name(id="State", ctx=ast.Load()))],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=body_stmts,
        decorator_list=[],
        returns=ast.Name(id="dict", ctx=ast.Load()),
    )

    return [class_def, ast.fix_missing_locations(func_def)]


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
# Pure AST Compiler
# ----------------------------------------------------
class PureAstLangGraphCompiler:
    def __init__(self, flow_data: GraphFlowData):
        self.flow_data = flow_data
        self.all_variables = [v for v in flow_data.state if v.key] if flow_data.state else []
        self.valid_keys = {v.key for v in self.all_variables}
        self.definer_ids: set[str] = set()
        self.executable_nodes = [
            n
            for n in flow_data.nodes
            if isinstance(n, (SwitchNode, LogicalAssignerNode, AgenticAssignerNode))
        ]
        self.switch_nodes = {n.id: n for n in self.executable_nodes if isinstance(n, SwitchNode)}

    def resolve_target_id(self, target_id: str, visited: set[str] | None = None) -> str:
        visited = visited or set()
        if target_id in visited or target_id == "end":
            return "END"
        visited.add(target_id)
        if target_id in self.definer_ids:
            out_edge = next((e for e in self.flow_data.edges if e.source_id == target_id), None)
            return self.resolve_target_id(out_edge.target_id, visited) if out_edge else "END"
        return target_id

    def resolve_source_id(self, source_id: str, visited: set[str] | None = None) -> str:
        visited = visited or set()
        if source_id in visited or source_id == "start":
            return "START"
        visited.add(source_id)
        if source_id in self.definer_ids:
            in_edge = next((e for e in self.flow_data.edges if e.target_id == source_id), None)
            return self.resolve_source_id(in_edge.source_id, visited) if in_edge else "START"
        return source_id

    def build_state_ast(self) -> list[ast.stmt]:
        if not self.all_variables:
            return ast.parse("class State(TypedDict):\n    pass\ninitial_state: State = {}").body

        anns: list[ast.stmt] = [
            ast.AnnAssign(
                target=ast.Name(id=v.key, ctx=ast.Store()),
                annotation=ast.Name(id=TYPE_MAP.get(v.type, "str"), ctx=ast.Load()),
                value=None,
                simple=1,
            )
            for v in self.all_variables
        ]
        cls_def = ast.ClassDef(
            name="State", bases=[ast.Name(id="TypedDict", ctx=ast.Load())], keywords=[], body=anns, decorator_list=[]
        )

        dict_values: list[ast.expr] = [
            ast.Constant(
                value=cast(
                    Any,
                    v.default_value if v.default_value is not None else DEFAULT_VALUES.get(v.type, ""),
                )
            )
            for v in self.all_variables
        ]

        init_state = ast.Assign(
            targets=[ast.Name(id="initial_state", ctx=ast.Store())],
            value=ast.Dict(
                keys=[ast.Constant(value=v.key) for v in self.all_variables],
                values=dict_values,
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
                resolved_src = self.resolve_source_id(e.source_id)
                switch_sources[tid].append(resolved_src)

        # Add Nodes
        for n in self.executable_nodes:
            if isinstance(n, SwitchNode) and not switch_sources[n.id]:
                dummy_lambda = ast.Lambda(
                    args=ast.arguments(
                        posonlyargs=[], args=[ast.arg(arg="state")], kwonlyargs=[], kw_defaults=[], defaults=[]
                    ),
                    body=ast.Constant(value=None),
                )
                stmts.append(_call("workflow.add_node", ast.Constant(value=n.id), dummy_lambda))
            elif not isinstance(n, SwitchNode):
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

        # Conditional Router Edges
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
            keys: list[ast.expr | None] = [ast.Constant(value=k) for k in slot_map.keys()]
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

        compile_call = ast.Call(
            func=ast.Attribute(value=ast.Name(id="workflow", ctx=ast.Load()), attr="compile", ctx=ast.Load()),
            args=[],
            keywords=[],
        )
        stmts.append(ast.Assign(targets=[ast.Name(id="app", ctx=ast.Store())], value=compile_call))
        return stmts

    def compile(self) -> str:
        has_agentic = any(isinstance(n, AgenticAssignerNode) for n in self.executable_nodes)
        import_lines = [
            "from typing import TypedDict, Literal, Any",
            "from langgraph.graph import StateGraph, START, END",
        ]
        if has_agentic:
            import_lines.extend(["from pydantic import BaseModel, Field", "from groq import Groq"])
        imports = ast.parse("\n".join(import_lines)).body
        nodes: list[ast.stmt] = []
        for n in self.executable_nodes:
            if isinstance(n, SwitchNode):
                nodes.append(compile_ast_switch_node(n.id, n.slots))
            elif isinstance(n, LogicalAssignerNode):
                nodes.append(compile_ast_dict_returning_node(n.id, n.assignments, self.valid_keys))
            elif isinstance(n, AgenticAssignerNode):
                nodes.extend(compile_ast_agentic_node(n, self.valid_keys, self.all_variables))

        mod = ast.Module(body=imports + self.build_state_ast() + nodes + self.build_workflow_ast(), type_ignores=[])
        return ast.unparse(ast.fix_missing_locations(mod))


async def generate_graph_code(flow_data: GraphFlowData) -> str:
    raw_code = PureAstLangGraphCompiler(flow_data).compile()
    if black is not None:
        try:
            return black.format_str(raw_code, mode=black.Mode(line_length=60))
        except Exception:
            pass
    return raw_code


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


async def compile_flow_with_langgraph(flow_data: GraphFlowData) -> dict[str, Any]:
    try:
        code = await generate_graph_code(flow_data)
        return await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(get_executor(), _worker_execute_langgraph, code),
            timeout=5.0,
        )
    except TimeoutError:
        return {"variables": [], "error": "LangGraph execution timed out (possible infinite loop in visual graph)"}
    except Exception as e:
        return {"variables": [], "error": f"LangGraph runtime failed: {str(e)}"}
