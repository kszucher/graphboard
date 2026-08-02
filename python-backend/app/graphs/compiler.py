"""=============================================================================
PURE CODE GENERATOR COMPILER (Layer 2)
=============================================================================
Translates ResolvedGraph (canonical nodes and pre-assembled edges) directly to
executable Python LangGraph code strings with single-pass AST validation.
============================================================================="""

from __future__ import annotations

import ast
import asyncio
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from app.graphs.canonical import (
    CanonicalComputation,
    CanonicalRetry,
    CanonicalRouter,
    CanonicalSentinel,
    ComputationKind,
    ResolvedGraph,
    RouterKind,
)
from app.graphs.schemas import DefinerVariableSchema, GraphFlowData

try:
    import black
except ImportError:
    black = None  # type: ignore[assignment]


_execution_executor: ProcessPoolExecutor | None = None

TYPE_MAP = {"number": "int", "float": "float", "boolean": "bool", "string": "str"}
DEFAULT_VALUES: dict[str, Any] = {"number": 0, "float": 0.0, "boolean": False, "string": ""}


def get_executor() -> ProcessPoolExecutor:
    global _execution_executor
    if _execution_executor is None:
        _execution_executor = ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn"))
    return _execution_executor


def ast_expr_to_code(node: dict[str, Any] | None, fallback: str = "True") -> str:
    """Converts a visual AST expression dict to Python code string."""
    if not node:
        return fallback

    kind = node.get("kind")
    if kind == "literal":
        return repr(node.get("value"))
    if kind == "stateRef":
        return f"state.get({repr(node.get('varKey', ''))})"
    if kind == "binaryOp":
        op = node.get("op", "==")
        left = ast_expr_to_code(node.get("left"), fallback)
        right = ast_expr_to_code(node.get("right"), fallback)
        return f"({left} {op} {right})"
    if kind == "unaryOp":
        op_str = node.get("op", "not")
        expr_str = ast_expr_to_code(node.get("expr"), fallback)
        return f"({op_str} {expr_str})"

    return fallback


class PureAstLangGraphCompiler:
    """Layer 2 Compiler: High-level code-string generator for LangGraph Python scripts."""

    def __init__(self, resolved_graph: ResolvedGraph):
        self.resolved_graph = resolved_graph
        self.all_variables = [v for v in resolved_graph.state if v.key]
        self.valid_keys = {v.key for v in self.all_variables}
        self.executable_nodes = [n for n in resolved_graph.nodes if not isinstance(n, CanonicalSentinel)]

    def emit_imports(self) -> str:
        has_agentic = any(
            (isinstance(n, CanonicalComputation) and n.body == ComputationKind.AGENTIC)
            or (isinstance(n, CanonicalRouter) and n.body == RouterKind.AGENTIC_SWITCH)
            for n in self.executable_nodes
        )
        has_interrupt = any(
            isinstance(n, CanonicalComputation) and n.body == ComputationKind.INTERRUPT for n in self.executable_nodes
        )

        lines = [
            "from typing import TypedDict, Literal, Any",
            "from langgraph.graph import StateGraph, START, END",
        ]
        if has_agentic:
            lines.extend(["from pydantic import BaseModel, Field", "from groq import Groq"])
        if has_interrupt:
            lines.append("from langgraph.types import interrupt")

        return "\n".join(lines)

    def emit_state_typeddict(self) -> str:
        known_keys = {v.key for v in self.all_variables}
        synthetic_vars: list[tuple[str, str, Any]] = []

        for n in self.executable_nodes:
            if isinstance(n, CanonicalRetry):
                ckey = f"__retry_{n.id}_count"
                if ckey not in known_keys and not any(k == ckey for k, _, _ in synthetic_vars):
                    synthetic_vars.append((ckey, "int", 0))
            elif isinstance(n, CanonicalRouter) and n.body == RouterKind.AGENTIC_SWITCH:
                skey = f"__sys_choice_{n.id}"
                if skey not in known_keys and not any(k == skey for k, _, _ in synthetic_vars):
                    synthetic_vars.append((skey, "str", ""))

        for v in self.resolved_graph.state:
            if v.key and v.key not in known_keys and not any(k == v.key for k, _, _ in synthetic_vars):
                py_type = TYPE_MAP.get(v.type, "str")
                def_val = v.default_value if v.default_value is not None else DEFAULT_VALUES.get(v.type, "")
                synthetic_vars.append((v.key, py_type, def_val))

        all_keys: list[tuple[str, str, Any]] = [
            (
                v.key,
                TYPE_MAP.get(v.type, "str"),
                v.default_value if v.default_value is not None else DEFAULT_VALUES.get(v.type, ""),
            )
            for v in self.all_variables
        ] + synthetic_vars

        if not all_keys:
            return "class State(TypedDict):\n    pass\n\ninitial_state: State = {}"

        fields = "\n".join(f"    {k}: {t}" for k, t, _ in all_keys)
        init_values = ", ".join(f"{repr(k)}: {repr(v)}" for k, _, v in all_keys)
        return f"class State(TypedDict):\n{fields}\n\ninitial_state = {{{init_values}}}"

    def emit_computation_node(self, node: CanonicalComputation, all_variables: list[DefinerVariableSchema]) -> str:
        if node.body == ComputationKind.LOGICAL:
            valid_items = [i for i in node.assignments if getattr(i, "target_var_key", None) in self.valid_keys]
            pairs = []
            for i in valid_items:
                expr = getattr(i, "expression", None)
                val_code = ast_expr_to_code(expr) if expr is not None else repr(getattr(i, "value", None))
                pairs.append(f"{repr(i.target_var_key)}: {val_code}")
            return f"def {node.id}(state: State) -> dict:\n    return {{{', '.join(pairs)}}}"

        if node.body == ComputationKind.PASSTHROUGH:
            return f"def {node.id}(state: State) -> dict:\n    return {{}}"

        if node.body == ComputationKind.INTERRUPT:
            payload_keys = [k for k in node.payload_vars if k in self.valid_keys]
            payload_items = ", ".join(f"{repr(k)}: state.get({repr(k)})" for k in payload_keys)
            ret_dict = (
                f"{{{repr(node.resume_var)}: value}}"
                if (node.resume_var and node.resume_var in self.valid_keys)
                else "{}"
            )
            return (
                f"def {node.id}(state: State) -> dict:\n"
                f"    value = interrupt({{{payload_items}}})\n"
                f"    return {ret_dict}"
            )

        if node.body == ComputationKind.AGENTIC:
            inputs = [k for k in node.agentic_inputs if k in self.valid_keys]
            outputs = [k for k in node.agentic_outputs if k in self.valid_keys]

            pydantic_fields = []
            for var_key in outputs:
                var_type = "string"
                var_desc = None
                for v in all_variables:
                    if v.key == var_key:
                        var_type = v.type
                        var_desc = v.description
                        break
                py_type = TYPE_MAP.get(var_type, "str")
                field_val = f" = Field(description={repr(var_desc)})" if var_desc else ""
                pydantic_fields.append(f"    {var_key}: {py_type}{field_val}")

            fields_code = "\n".join(pydantic_fields) if pydantic_fields else "    pass"
            pydantic_cls = f"class {node.id}Output(BaseModel):\n{fields_code}"

            replacements = "\n".join(
                f"    prompt_text = prompt_text.replace({repr(f'{{{k}}}')}, str(state.get({repr(k)})))" for k in inputs
            )
            ret_items = ", ".join(f"{repr(k)}: res.{k}" for k in outputs)

            repl_block = f"{replacements}\n" if replacements else ""
            fn_code = (
                f"def {node.id}(state: State) -> dict:\n"
                f"    client = Groq()\n"
                f"    prompt_text = {repr(node.prompt or '')}\n"
                f"{repl_block}"
                f"    chat_completion = client.beta.chat.completions.parse(\n"
                f"        messages=[{{'role': 'user', 'content': prompt_text}}],\n"
                f"        model='llama3-8b-8192',\n"
                f"        response_format={node.id}Output,\n"
                f"    )\n"
                f"    res = chat_completion.choices[0].message.parsed\n"
                f"    if res is None:\n"
                f"        return {{}}\n"
                f"    return {{{ret_items}}}"
            )
            return f"{pydantic_cls}\n\n{fn_code}"

        return ""

    def emit_router_node(self, node: CanonicalRouter) -> str:
        if node.body == RouterKind.LOGICAL_SWITCH:
            if_branches = []
            for idx, slot in enumerate(node.slots):
                raw = slot.raw_string or f"Slot {idx + 1}"
                expr = slot.expression
                if idx == len(node.slots) - 1 and expr and expr.get("kind") == "literal" and expr.get("value") is True:
                    if_branches.append(f"    else:\n        return {repr(raw)}")
                else:
                    cond_code = ast_expr_to_code(expr, fallback="False")
                    keyword = "if" if idx == 0 else "elif"
                    if_branches.append(f"    {keyword} {cond_code}:\n        return {repr(raw)}")

            if not any(b.strip().startswith("else:") for b in if_branches):
                if_branches.append("    else:\n        return ''")

            branches_code = "\n".join(if_branches)
            return f"def {node.id}(state: State) -> str:\n{branches_code}"

        if node.body == RouterKind.AGENTIC_SWITCH:
            slot_labels = [s.raw_string for s in node.slots if s.raw_string]
            literal_union = ", ".join(repr(label) for label in slot_labels)
            choice_cls = f"class {node.id}Choice(BaseModel):\n    decision: Literal[{literal_union}]"

            inputs = [k for k in node.agentic_inputs if k in self.valid_keys]
            replacements = "\n".join(
                f"    prompt_text = prompt_text.replace({repr(f'{{{k}}}')}, str(state.get({repr(k)})))" for k in inputs
            )
            fallback = slot_labels[0] if slot_labels else ""

            repl_block = f"{replacements}\n" if replacements else ""
            fn_code = (
                f"def {node.id}(state: State) -> dict:\n"
                f"    client = Groq()\n"
                f"    prompt_text = {repr(node.prompt or '')}\n"
                f"{repl_block}"
                f"    chat_completion = client.beta.chat.completions.parse(\n"
                f"        messages=[{{'role': 'user', 'content': prompt_text}}],\n"
                f"        model='llama3-8b-8192',\n"
                f"        response_format={node.id}Choice,\n"
                f"    )\n"
                f"    parsed_msg = chat_completion.choices[0].message\n"
                f"    decision = parsed_msg.parsed.decision if parsed_msg.parsed is not None else {repr(fallback)}\n"
                f"    return {{'__sys_choice_{node.id}': decision}}\n\n"
                f"def __{node.id}_route(state: State) -> str:\n"
                f"    return state.get('__sys_choice_{node.id}')"
            )
            return f"{choice_cls}\n\n{fn_code}"

        return ""

    def emit_retry_node(self, node: CanonicalRetry) -> str:
        counter_var = f"__retry_{node.id}_count"
        count_check = f"state.get({repr(counter_var)}, 0) < {node.max_attempts}"

        retry_branch = f"    elif {count_check}:\n        return 'retry'\n    else:\n        return 'exhausted'"

        if node.valid_expression is not None:
            valid_code = ast_expr_to_code(node.valid_expression, fallback="True")
            body_code = f"    if {valid_code}:\n        return 'valid'\n{retry_branch}"
        else:
            body_code = f"    if {count_check}:\n        return 'retry'\n    else:\n        return 'exhausted'"

        return f"def {node.id}(state: State) -> str:\n{body_code}"

    def emit_workflow(self) -> str:
        lines = [
            "workflow = StateGraph(State)",
        ]

        # 1. Add Executable Nodes
        for n in self.executable_nodes:
            if isinstance(n, CanonicalRouter) and n.body == RouterKind.AGENTIC_SWITCH:
                lines.append(f"workflow.add_node('{n.id}', {n.id})")
            elif isinstance(n, CanonicalComputation):
                lines.append(f"workflow.add_node('{n.id}', {n.id})")

        # 2. Add Direct Edges
        for src, tgt in self.resolved_graph.direct_edges:
            src_ref = "START" if src == "START" else repr(src)
            tgt_ref = "END" if tgt == "END" else repr(tgt)
            lines.append(f"workflow.add_edge({src_ref}, {tgt_ref})")

        # 3. Add Conditional Router Edges
        for cedge in self.resolved_graph.conditional_edges:
            src_ref = "START" if cedge.source_node_id == "START" else repr(cedge.source_node_id)
            slot_map_code = (
                "{"
                + ", ".join(f"{repr(k)}: {'END' if v == 'END' else repr(v)}" for k, v in cedge.slot_mapping.items())
                + "}"
            )
            lines.append(f"workflow.add_conditional_edges({src_ref}, {cedge.router_fn_name}, {slot_map_code})")

        lines.append("app = workflow.compile()")
        return "\n".join(lines)

    def compile(self) -> str:
        sections = [
            self.emit_imports(),
            self.emit_state_typeddict(),
        ]

        for n in self.executable_nodes:
            if isinstance(n, CanonicalComputation):
                sections.append(self.emit_computation_node(n, self.resolved_graph.state))
            elif isinstance(n, CanonicalRouter):
                sections.append(self.emit_router_node(n))
            elif isinstance(n, CanonicalRetry):
                sections.append(self.emit_retry_node(n))

        sections.append(self.emit_workflow())

        raw_code = "\n\n".join(sections)

        # Validate syntax in single pass
        tree = ast.parse(raw_code)
        assert tree is not None

        return raw_code


async def generate_graph_code(flow_data: GraphFlowData) -> str:
    from app.graphs.resolver import SemanticResolver

    canonical = SemanticResolver().resolve(flow_data)  # Layer 1
    raw_code = PureAstLangGraphCompiler(canonical).compile()  # Layer 2
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
