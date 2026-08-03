"""=============================================================================
1-LAYER DIRECT LANGGRAPH COMPILER
=============================================================================
Translates GraphFlowData (visual nodes, edges, and state variables) directly into
executable Python LangGraph code strings with single-pass AST validation.
============================================================================="""

from __future__ import annotations

import ast
import asyncio
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from app.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    DefinerVariableSchema,
    EndNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    NodeRead,
    StartNode,
)

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


class DirectLangGraphCompiler:
    """Direct 1-Layer Compiler: Visual GraphFlowData to LangGraph Python Script."""

    def __init__(self, flow_data: GraphFlowData):
        self.flow_data = flow_data
        self.all_variables = [v for v in flow_data.state if v.key]
        self.valid_keys = {v.key for v in self.all_variables}
        self.nodes_by_id: dict[str, NodeRead] = {n.id: n for n in flow_data.nodes}
        self.executable_nodes = [n for n in flow_data.nodes if not isinstance(n, (StartNode, EndNode))]

    def emit_imports(self) -> str:
        has_agentic = any(isinstance(n, (AgenticAssignerNode, AgenticSwitchNode)) for n in self.executable_nodes)
        has_agentic_switch = any(isinstance(n, AgenticSwitchNode) for n in self.executable_nodes)
        has_interrupt = any(isinstance(n, InterruptNode) for n in self.executable_nodes)

        lines = [
            "from typing import TypedDict, Literal, Any",
            "from langgraph.graph import StateGraph, START, END",
        ]
        if has_agentic_switch:
            lines.append("from enum import Enum")
        if has_agentic:
            lines.extend(["from pydantic import BaseModel, Field", "from groq import Groq"])
        if has_interrupt:
            lines.append("from langgraph.types import interrupt")

        return "\n".join(lines)

    def emit_state_typeddict(self) -> str:
        all_keys: list[tuple[str, str, Any]] = [
            (
                v.key,
                TYPE_MAP.get(v.type, "str"),
                v.default_value if v.default_value is not None else DEFAULT_VALUES.get(v.type, ""),
            )
            for v in self.all_variables
        ]

        if not all_keys:
            return "class State(TypedDict):\n    pass\n\ninitial_state: State = {}"

        fields = "\n".join(f"    {k}: {t}" for k, t, _ in all_keys)
        init_values = ", ".join(f"{repr(k)}: {repr(v)}" for k, _, v in all_keys)
        return f"class State(TypedDict):\n{fields}\n\ninitial_state = {{{init_values}}}"

    def emit_node_code(self, node: NodeRead, all_variables: list[DefinerVariableSchema]) -> str:
        if isinstance(node, LogicalAssignerNode):
            valid_items = [i for i in node.assignments if getattr(i, "target_var_key", None) in self.valid_keys]
            pairs = []
            for i in valid_items:
                expr = getattr(i, "expression", None)
                val_code = ast_expr_to_code(expr) if expr is not None else repr(getattr(i, "value", None))
                pairs.append(f"{repr(i.target_var_key)}: {val_code}")
            return f"def {node.id}(state: State) -> dict:\n    return {{{', '.join(pairs)}}}"

        if isinstance(node, AgenticAssignerNode):
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

        if isinstance(node, LogicalSwitchNode):
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

        if isinstance(node, AgenticSwitchNode):
            slot_labels = [s.raw_string for s in node.slots if s.raw_string]
            enum_members = []
            for idx, label in enumerate(slot_labels):
                slug = "".join(c if c.isalnum() else "_" for c in label).upper()
                slug = slug.strip("_")
                if not slug or slug[0].isdigit():
                    slug = f"OPTION_{idx + 1}"
                enum_members.append(f"    {slug} = {repr(label)}")

            enum_code = "\n".join(enum_members) if enum_members else "    NONE = ''"
            enum_cls = f"class {node.id}Option(str, Enum):\n{enum_code}"
            choice_cls = f"class {node.id}Choice(BaseModel):\n    decision: {node.id}Option"

            inputs = [k for k in node.agentic_inputs if k in self.valid_keys]
            replacements = "\n".join(
                f"    prompt_text = prompt_text.replace({repr(f'{{{k}}}')}, str(state.get({repr(k)})))" for k in inputs
            )
            fallback = slot_labels[0] if slot_labels else ""
            fallback_enum_expr = (
                f"{node.id}Option.{enum_members[0].split('=')[0].strip()}.value"
                if enum_members
                else repr(fallback)
            )
            repl_block = f"{replacements}\n" if replacements else ""

            fn_code = (
                f"def {node.id}(state: State) -> str:\n"
                f"    client = Groq()\n"
                f"    prompt_text = {repr(node.prompt or '')}\n"
                f"{repl_block}"
                f"    chat_completion = client.beta.chat.completions.parse(\n"
                f"        messages=[{{'role': 'user', 'content': prompt_text}}],\n"
                f"        model='llama3-8b-8192',\n"
                f"        response_format={node.id}Choice,\n"
                f"    )\n"
                f"    parsed = chat_completion.choices[0].message.parsed\n"
                f"    if parsed is not None:\n"
                f"        return parsed.decision.value\n"
                f"    return {fallback_enum_expr}"
            )
            return f"{enum_cls}\n\n{choice_cls}\n\n{fn_code}"

        if isinstance(node, InterruptNode):
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

        return ""

    def emit_workflow(self) -> str:
        lines = [
            "workflow = StateGraph(State)",
        ]

        # 1. Add Executable Nodes to Graph (Only computation nodes: LogicalAssigner, AgenticAssigner, Interrupt)
        for n in self.executable_nodes:
            if isinstance(n, (LogicalAssignerNode, AgenticAssignerNode, InterruptNode)):
                lines.append(f"workflow.add_node('{n.id}', {n.id})")

        # 2. Build Slot Map & Route lookup
        all_slots: dict[str, tuple[str, str]] = {}  # slot_id -> (router_node_id, raw_string)
        for n in self.executable_nodes:
            if isinstance(n, (LogicalSwitchNode, AgenticSwitchNode)):
                for s in n.slots:
                    if s.id:
                        all_slots[s.id] = (n.id, s.raw_string)

        def resolve_target(tgt_id: str) -> str:
            if tgt_id in self.nodes_by_id:
                target_node = self.nodes_by_id[tgt_id]
                if isinstance(target_node, StartNode):
                    return "START"
                if isinstance(target_node, EndNode):
                    return "END"
            if tgt_id == "start":
                return "START"
            if tgt_id == "end":
                return "END"
            return tgt_id

        # 3. Process Edges
        router_incoming_sources: dict[str, list[str]] = {}
        for edge in self.flow_data.edges:
            target_id = edge.target_id
            if target_id in self.nodes_by_id:
                tnode = self.nodes_by_id[target_id]
                if isinstance(tnode, (LogicalSwitchNode, AgenticSwitchNode)):
                    src_id = edge.source_id
                    if src_id in all_slots:
                        src_id = all_slots[src_id][0]
                    elif src_id in self.nodes_by_id and isinstance(self.nodes_by_id[src_id], StartNode):
                        src_id = "START"
                    elif src_id == "start":
                        src_id = "START"
                    router_incoming_sources.setdefault(tnode.id, []).append(src_id)

        # Emit conditional edges for LogicalSwitchNode & AgenticSwitchNode
        for n in self.executable_nodes:
            if isinstance(n, (LogicalSwitchNode, AgenticSwitchNode)):
                slot_map: dict[str, str] = {}
                for slot in n.slots:
                    slot_edge = next((e for e in self.flow_data.edges if e.source_id == slot.id), None)
                    if slot_edge is not None:
                        tgt = resolve_target(slot_edge.target_id)
                        slot_map[slot.raw_string] = tgt

                if slot_map:
                    sources = router_incoming_sources.get(n.id, [n.id])
                    slot_map_code = (
                        "{"
                        + ", ".join(f"{repr(k)}: {'END' if v == 'END' else repr(v)}" for k, v in slot_map.items())
                        + "}"
                    )
                    for src in sources:
                        src_ref = "START" if src == "START" else repr(src)
                        lines.append(f"workflow.add_conditional_edges({src_ref}, {n.id}, {slot_map_code})")

        # Emit Direct Edges
        for edge in self.flow_data.edges:
            if edge.source_id in all_slots or edge.source_type == "slot":
                continue
            target_node = self.nodes_by_id.get(edge.target_id)
            if isinstance(target_node, (LogicalSwitchNode, AgenticSwitchNode)):
                continue

            src = (
                "START"
                if (
                    edge.source_id == "start"
                    or (edge.source_id in self.nodes_by_id and isinstance(self.nodes_by_id[edge.source_id], StartNode))
                )
                else edge.source_id
            )
            tgt = resolve_target(edge.target_id)
            src_ref = "START" if src == "START" else repr(src)
            tgt_ref = "END" if tgt == "END" else repr(tgt)
            lines.append(f"workflow.add_edge({src_ref}, {tgt_ref})")

        lines.append("app = workflow.compile()")
        return "\n".join(lines)

    def compile(self) -> str:
        sections = [
            self.emit_imports(),
            self.emit_state_typeddict(),
        ]

        for n in self.executable_nodes:
            node_code = self.emit_node_code(n, self.flow_data.state)
            if node_code:
                sections.append(node_code)

        sections.append(self.emit_workflow())

        raw_code = "\n\n".join(sections)

        # Validate syntax in single pass
        tree = ast.parse(raw_code)
        assert tree is not None

        return raw_code


async def generate_graph_code(flow_data: GraphFlowData) -> str:
    raw_code = DirectLangGraphCompiler(flow_data).compile()
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
