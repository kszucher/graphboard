from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.modules.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    EndNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    NodeRead,
    RagRetrieverNode,
    StartNode,
    expression_to_code,
    get_expression_variables,
)

try:
    import black
except ImportError:
    black = None  # type: ignore[assignment]


TYPE_MAP = {
    "number": "int",
    "boolean": "bool",
    "string": "str",
    "array": "list[Any]",
    "object": "dict[str, Any]",
}
DEFAULT_VALUES: dict[str, Any] = {
    "number": 0,
    "boolean": False,
    "string": "",
    "array": [],
    "object": {},
}

TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), trim_blocks=True, lstrip_blocks=True)


class DirectLangGraphCompiler:
    """Direct 1-Layer Compiler: Visual GraphFlowData to LangGraph Python Script via Jinja2."""

    def __init__(self, flow_data: GraphFlowData, model_name: str | None = None):
        self.flow_data = flow_data
        self.model_name = model_name or settings.copilot_model
        self.all_variables = [v for v in flow_data.state if v.key]
        self.valid_keys = {v.key for v in self.all_variables}
        self.nodes_by_id: dict[str, NodeRead] = {n.id: n for n in flow_data.nodes}
        self.executable_nodes = [n for n in flow_data.nodes if not isinstance(n, (StartNode, EndNode))]

    def visit_imports(self, node: NodeRead) -> set[str]:
        match node:
            case AgenticAssignerNode():
                return {
                    "from pydantic import BaseModel, Field",
                    "from google import genai",
                    "from google.genai import types",
                }
            case AgenticSwitchNode():
                return {
                    "from enum import Enum",
                    "from pydantic import BaseModel, Field",
                    "from google import genai",
                    "from google.genai import types",
                }
            case InterruptNode():
                return {"from langgraph.types import interrupt"}
            case RagRetrieverNode():
                return {"from app.modules.graphs.engine.rag import retrieve_documents"}
            case _:
                return set()

    def emit_imports(self) -> str:
        lines = {
            "import random",
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

    def build_node_code(self, node: NodeRead) -> str:
        match node:
            case LogicalAssignerNode() as n:
                valid_items = [i for i in n.assignments if getattr(i, "target_var_key", None) in self.valid_keys]
                refs: set[str] = set()
                for i in valid_items:
                    refs.update(get_expression_variables(i.expression) & self.valid_keys)
                unpacks = "\n".join(f"    {k} = state.get({repr(k)})" for k in sorted(refs))
                unpack_str = f"{unpacks}\n" if unpacks else ""
                pairs = []
                for i in valid_items:
                    val_code = expression_to_code(i.expression, self.valid_keys, target_var_key=i.target_var_key)
                    pairs.append(f"{repr(i.target_var_key)}: {val_code}")
                return f"def {n.id}(state: State) -> dict:\n{unpack_str}    return {{{', '.join(pairs)}}}"

            case LogicalSwitchNode() as n:
                refs = set()
                for b in n.branches:
                    refs.update(get_expression_variables(b.expression) & self.valid_keys)
                unpacks = "\n".join(f"    {k} = state.get({repr(k)})" for k in sorted(refs))
                unpack_str = f"{unpacks}\n" if unpacks else ""
                if_branches = []
                for idx, branch in enumerate(n.branches):
                    raw = branch.label or f"Branch {idx + 1}"
                    expr_val = branch.expression
                    if idx == len(n.branches) - 1 and (expr_val is True or expr_val == "True" or expr_val is None):
                        if_branches.append(f"    else:\n        return {repr(raw)}")
                    else:
                        cond_code = expression_to_code(expr_val, self.valid_keys, fallback="False")
                        keyword = "if" if idx == 0 else "elif"
                        if_branches.append(f"    {keyword} {cond_code}:\n        return {repr(raw)}")
                if not any(b.strip().startswith("else:") for b in if_branches):
                    if_branches.append("    else:\n        return ''")
                branches_code = "\n".join(if_branches)
                return f"def {n.id}(state: State) -> str:\n{unpack_str}{branches_code}"

            case AgenticAssignerNode() as n:
                inputs = [k for k in n.agentic_inputs if k in self.valid_keys]
                outputs = [k for k in n.agentic_outputs if k in self.valid_keys]
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
                pydantic_cls = f"class {n.id}Output(BaseModel):\n{fields_code}"
                replacements = "\n".join(
                    f"    prompt_text = prompt_text.replace({repr(f'{{{k}}}')}, str(state.get({repr(k)})))"
                    for k in inputs
                )
                ret_items = ", ".join(f"{repr(k)}: res.{k}" for k in outputs)
                repl_block = f"{replacements}\n" if replacements else ""
                fn_code = (
                    f"def {n.id}(state: State) -> dict:\n"
                    f"    client = genai.Client()\n"
                    f"    prompt_text = {repr(n.prompt or '')}\n"
                    f"{repl_block}"
                    f"    response = client.models.generate_content(\n"
                    f"        model={repr(self.model_name)},\n"
                    f"        contents=prompt_text,\n"
                    f"        config=types.GenerateContentConfig(\n"
                    f"            response_mime_type='application/json',\n"
                    f"            response_schema={n.id}Output,\n"
                    f"        ),\n"
                    f"    )\n"
                    f"    try:\n"
                    f"        res = {n.id}Output.model_validate_json(response.text)\n"
                    f"    except Exception:\n"
                    f"        return {{}}\n"
                    f"    if res is None:\n"
                    f"        return {{}}\n"
                    f"    return {{{ret_items}}}"
                )
                return f"{pydantic_cls}\n\n{fn_code}"

            case AgenticSwitchNode() as n:
                branch_labels = [b.label for b in n.branches if b.label]
                enum_members = []
                for idx, label in enumerate(branch_labels):
                    slug = "".join(c if c.isalnum() else "_" for c in label).upper().strip("_")
                    if not slug or slug[0].isdigit():
                        slug = f"OPTION_{idx + 1}"
                    enum_members.append(f"    {slug} = {repr(label)}")
                enum_code = "\n".join(enum_members) if enum_members else "    NONE = ''"
                enum_cls = f"class {n.id}Option(str, Enum):\n{enum_code}"
                choice_cls = f"class {n.id}Choice(BaseModel):\n    decision: {n.id}Option"
                input_key = n.agentic_input if (n.agentic_input and n.agentic_input in self.valid_keys) else ""
                input_declarations = (
                    [f"    input = state.get({repr(input_key)})"] if input_key else ["    input = None"]
                )
                options_list_expr = ", ".join(repr(label) for label in branch_labels)
                input_declarations.append(f"    options = [{options_list_expr}]")
                declarations_code = "\n".join(input_declarations)
                prompt_concatenation = "\n".join(
                    [
                        '        f"Input:\\n"',
                        '        f"{input}\\n"',
                        '        f"\\n"',
                        '        f"Classify the input into one of the following options: {{options}}"',
                    ]
                )
                fallback = branch_labels[0] if branch_labels else ""
                fallback_enum_expr = (
                    f"{n.id}Option.{enum_members[0].split('=')[0].strip()}.value" if enum_members else repr(fallback)
                )
                fn_code = (
                    f"def {n.id}(state: State) -> str:\n"
                    f"{declarations_code}\n"
                    f"    client = genai.Client()\n"
                    f"    prompt_text = (\n"
                    f"{prompt_concatenation}\n"
                    f"    )\n"
                    f"    response = client.models.generate_content(\n"
                    f"        model={repr(self.model_name)},\n"
                    f"        contents=prompt_text,\n"
                    f"        config=types.GenerateContentConfig(\n"
                    f"            response_mime_type='application/json',\n"
                    f"            response_schema={n.id}Choice,\n"
                    f"        ),\n"
                    f"    )\n"
                    f"    try:\n"
                    f"        parsed = {n.id}Choice.model_validate_json(response.text)\n"
                    f"    except Exception:\n"
                    f"        return {fallback_enum_expr}\n"
                    f"    if parsed is not None:\n"
                    f"        return parsed.decision.value\n"
                    f"    return {fallback_enum_expr}"
                )
                return f"{enum_cls}\n\n{choice_cls}\n\n{fn_code}"

            case InterruptNode() as n:
                payload_keys = [k for k in n.payload_vars if k in self.valid_keys]
                payload_items = ", ".join(f"{repr(k)}: state.get({repr(k)})" for k in payload_keys)
                ret_dict = (
                    f"{{{repr(n.resume_var)}: value}}" if (n.resume_var and n.resume_var in self.valid_keys) else "{}"
                )
                return (
                    f"def {n.id}(state: State) -> dict:\n"
                    f"    value = interrupt({{{payload_items}}})\n"
                    f"    return {ret_dict}"
                )

            case RagRetrieverNode() as n:
                query_key = n.query_var if n.query_var in self.valid_keys else ""
                out_key = n.context_output_var if n.context_output_var in self.valid_keys else ""
                return (
                    f"def {n.id}(state: State) -> dict:\n"
                    f"    query = state.get({repr(query_key)}, '')\n"
                    f"    docs = retrieve_documents(query=query, kb={repr(n.knowledge_base)}, top_k={n.top_k})\n"
                    f"    return {{{repr(out_key)}: '\\n\\n'.join(docs)}}"
                )

            case _:
                return ""

    def compile(self) -> str:
        nodes_data = []
        for n in self.executable_nodes:
            code = self.build_node_code(n)
            is_switch = isinstance(n, (LogicalSwitchNode, AgenticSwitchNode))
            nodes_data.append({"id": n.id, "code": code, "is_switch": is_switch})

        def resolve_target(tgt_id: str) -> str:
            if tgt_id in self.nodes_by_id:
                target_node = self.nodes_by_id[tgt_id]
                if isinstance(target_node, StartNode):
                    return "START"
                if isinstance(target_node, EndNode):
                    return "END"
                return repr(tgt_id)
            if tgt_id == "start":
                return "START"
            if tgt_id == "end":
                return "END"
            raise ValidationError(f"Cannot compile graph: target node '{tgt_id}' does not exist in graph.")

        def resolve_source(src_id: str) -> str:
            if src_id in self.nodes_by_id:
                src_node = self.nodes_by_id[src_id]
                if isinstance(src_node, StartNode):
                    return "START"
                if isinstance(src_node, EndNode):
                    raise ValidationError("Cannot compile graph: END node cannot have outgoing edges.")
                return repr(src_id)
            if src_id == "start":
                return "START"
            raise ValidationError(f"Cannot compile graph: source node '{src_id}' does not exist in graph.")

        conditional_edges = []
        for n in self.executable_nodes:
            if isinstance(n, (LogicalSwitchNode, AgenticSwitchNode)):
                slot_map: dict[str, str] = {}
                for branch in n.branches:
                    branch_edge = next(
                        (e for e in self.flow_data.edges if e.source == n.id and e.source_handle == branch.id), None
                    )
                    if branch_edge is not None:
                        slot_map[branch.label] = resolve_target(branch_edge.target)

                if slot_map:
                    slot_map_code = "{" + ", ".join(f"{repr(k)}: {v}" for k, v in slot_map.items()) + "}"
                    conditional_edges.append({"source": n.id, "fn": n.id, "slot_map": slot_map_code})

        direct_edges = []
        for edge in self.flow_data.edges:
            if edge.source_handle is not None:
                continue
            direct_edges.append(
                {
                    "source": resolve_source(edge.source),
                    "target": resolve_target(edge.target),
                }
            )

        template = jinja_env.get_template("langgraph_workflow.py.jinja")
        raw_code = template.render(
            imports=self.emit_imports(),
            state_definition=self.emit_state_typeddict(),
            nodes=nodes_data,
            conditional_edges=conditional_edges,
            direct_edges=direct_edges,
        )

        tree = ast.parse(raw_code)
        built_code = compile(tree, "<compiled_graph>", "exec")
        assert built_code is not None

        return raw_code


async def generate_graph_code(flow_data: GraphFlowData, model_name: str | None = None) -> str:
    raw_code = DirectLangGraphCompiler(flow_data, model_name=model_name).compile()
    if black is not None:
        try:
            return black.format_str(raw_code, mode=black.Mode(line_length=60))
        except Exception:
            pass
    return raw_code
