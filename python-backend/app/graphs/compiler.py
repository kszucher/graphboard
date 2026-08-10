"""=============================================================================
1-LAYER DIRECT LANGGRAPH COMPILER
=============================================================================
Translates GraphFlowData (visual nodes, edges, and state variables) directly into
executable Python LangGraph code strings with single-pass AST validation.
============================================================================="""

from __future__ import annotations

import ast
from typing import Any

from app.graphs.expressions import expression_to_code
from app.graphs.nodes import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    EndNode,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    NodeRead,
    StartNode,
)
from app.graphs.schemas import (
    GraphFlowData,
)

try:
    import black
except ImportError:
    black = None  # type: ignore[assignment]


TYPE_MAP = {"number": "int", "float": "float", "boolean": "bool", "string": "str"}
DEFAULT_VALUES: dict[str, Any] = {"number": 0, "float": 0.0, "boolean": False, "string": ""}


class DirectLangGraphCompiler:
    """Direct 1-Layer Compiler: Visual GraphFlowData to LangGraph Python Script."""

    def __init__(self, flow_data: GraphFlowData):
        self.flow_data = flow_data
        self.all_variables = [v for v in flow_data.state if v.key]
        self.valid_keys = {v.key for v in self.all_variables}
        self.nodes_by_id: dict[str, NodeRead] = {n.id: n for n in flow_data.nodes}
        self.executable_nodes = [n for n in flow_data.nodes if not isinstance(n, (StartNode, EndNode))]

    def visit(self, node: NodeRead) -> Any:
        """Dynamic visitor dispatcher based on Node type name."""
        snake_name = f"{node.node_type.value.lower()}_node"
        method_name = f"visit_{snake_name}"
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    @staticmethod
    def generic_visit(_node: NodeRead) -> Any:
        return ""

    def visit_imports(self, node: NodeRead) -> set[str]:
        """Query imports required by a specific node class."""
        snake_name = f"{node.node_type.value.lower()}_node"
        method_name = f"imports_{snake_name}"
        from collections.abc import Callable

        visitor: Callable[[NodeRead], set[str]] = getattr(self, method_name, lambda n: set())
        return visitor(node)

    @staticmethod
    def imports_agentic_assigner_node(_node: AgenticAssignerNode) -> set[str]:
        return {"from pydantic import BaseModel, Field", "from groq import Groq"}

    @staticmethod
    def imports_agentic_switch_node(_node: AgenticSwitchNode) -> set[str]:
        return {"from enum import Enum", "from pydantic import BaseModel, Field", "from groq import Groq"}

    @staticmethod
    def imports_interrupt_node(_node: InterruptNode) -> set[str]:
        return {"from langgraph.types import interrupt"}

    def emit_imports(self) -> str:
        lines = {
            "from typing import TypedDict, Literal, Any",
            "from langgraph.graph import StateGraph, START, END",
        }
        for n in self.executable_nodes:
            lines.update(self.visit_imports(n))

        return "\n".join(sorted(list(lines)))

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

    def visit_logical_assigner_node(self, node: LogicalAssignerNode) -> str:
        valid_items = [i for i in node.assignments if getattr(i, "target_var_key", None) in self.valid_keys]
        pairs = []
        for i in valid_items:
            expr = getattr(i, "expression", None)
            val_code = expression_to_code(expr, self.valid_keys)
            pairs.append(f"{repr(i.target_var_key)}: {val_code}")
        return f"def {node.id}(state: State) -> dict:\n    return {{{', '.join(pairs)}}}"

    def visit_agentic_assigner_node(self, node: AgenticAssignerNode) -> str:
        inputs = [k for k in node.agentic_inputs if k in self.valid_keys]
        outputs = [k for k in node.agentic_outputs if k in self.valid_keys]

        pydantic_fields = []
        for var_key in outputs:
            var_type = "string"
            var_desc = None
            for v in self.flow_data.state:
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

    def visit_logical_switch_node(self, node: LogicalSwitchNode) -> str:
        if_branches = []
        for idx, slot in enumerate(node.slots):
            raw = slot.raw_string or f"Slot {idx + 1}"
            expr = slot.expression
            if idx == len(node.slots) - 1 and expr == "True":
                if_branches.append(f"    else:\n        return {repr(raw)}")
            else:
                cond_code = expression_to_code(expr, self.valid_keys, fallback="False")
                keyword = "if" if idx == 0 else "elif"
                if_branches.append(f"    {keyword} {cond_code}:\n        return {repr(raw)}")

        if not any(b.strip().startswith("else:") for b in if_branches):
            if_branches.append("    else:\n        return ''")

        branches_code = "\n".join(if_branches)
        return f"def {node.id}(state: State) -> str:\n{branches_code}"

    def visit_agentic_switch_node(self, node: AgenticSwitchNode) -> str:
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

        input_key = node.agentic_input if (node.agentic_input and node.agentic_input in self.valid_keys) else ""
        input_declarations = []
        if input_key:
            input_declarations.append(f"    input = state.get({repr(input_key)})")
        else:
            input_declarations.append("    input = None")

        options_list_expr = ", ".join(repr(label) for label in slot_labels)
        input_declarations.append(f"    options = [{options_list_expr}]")
        declarations_code = "\n".join(input_declarations)

        prompt_lines = [
            '        f"Input:\\n"',
            '        f"{input}\\n"',
            '        f"\\n"',
            '        f"Classify the input into one of the following options: {{options}}"',
        ]
        prompt_concatenation = "\n".join(prompt_lines)

        fallback = slot_labels[0] if slot_labels else ""
        fallback_enum_expr = (
            f"{node.id}Option.{enum_members[0].split('=')[0].strip()}.value" if enum_members else repr(fallback)
        )

        fn_code = (
            f"def {node.id}(state: State) -> str:\n"
            f"{declarations_code}\n"
            f"    client = Groq()\n"
            f"    prompt_text = (\n"
            f"{prompt_concatenation}\n"
            f"    )\n"
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

    def visit_interrupt_node(self, node: InterruptNode) -> str:
        payload_keys = [k for k in node.payload_vars if k in self.valid_keys]
        payload_items = ", ".join(f"{repr(k)}: state.get({repr(k)})" for k in payload_keys)
        ret_dict = (
            f"{{{repr(node.resume_var)}: value}}" if (node.resume_var and node.resume_var in self.valid_keys) else "{}"
        )
        return (
            f"def {node.id}(state: State) -> dict:\n    value = interrupt({{{payload_items}}})\n    return {ret_dict}"
        )

    def emit_node_code(self, node: NodeRead) -> str:
        from typing import cast

        return cast(str, self.visit(node))

    def emit_workflow(self) -> str:
        lines = [
            "workflow = StateGraph(State)",
        ]

        # 1. Add Executable Nodes to Graph (Only computation nodes: LogicalAssigner, AgenticAssigner, Interrupt)
        for n in self.executable_nodes:
            if isinstance(n, (LogicalAssignerNode, AgenticAssignerNode, InterruptNode)):
                lines.append(f"workflow.add_node('{n.id}', {n.id})")

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

        # 2. Process Edges
        router_incoming_sources: dict[str, list[str]] = {}
        for edge in self.flow_data.edges:
            target_id = edge.target
            if target_id in self.nodes_by_id:
                tnode = self.nodes_by_id[target_id]
                if isinstance(tnode, (LogicalSwitchNode, AgenticSwitchNode)):
                    src_id = edge.source
                    if src_id in self.nodes_by_id and isinstance(self.nodes_by_id[src_id], StartNode):
                        src_id = "START"
                    elif src_id == "start":
                        src_id = "START"
                    router_incoming_sources.setdefault(tnode.id, []).append(src_id)

        # Emit conditional edges for LogicalSwitchNode & AgenticSwitchNode
        for n in self.executable_nodes:
            if isinstance(n, (LogicalSwitchNode, AgenticSwitchNode)):
                slot_map: dict[str, str] = {}
                for slot in n.slots:
                    slot_edge = next(
                        (e for e in self.flow_data.edges if e.source == n.id and e.source_handle == slot.id), None
                    )
                    if slot_edge is not None:
                        tgt = resolve_target(slot_edge.target)
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
            if edge.source_handle is not None:
                continue
            target_node = self.nodes_by_id.get(edge.target)
            if isinstance(target_node, (LogicalSwitchNode, AgenticSwitchNode)):
                continue

            src = (
                "START"
                if (
                    edge.source == "start"
                    or (edge.source in self.nodes_by_id and isinstance(self.nodes_by_id[edge.source], StartNode))
                )
                else edge.source
            )
            tgt = resolve_target(edge.target)
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
            node_code = self.emit_node_code(n)
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
