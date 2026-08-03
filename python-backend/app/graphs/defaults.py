from __future__ import annotations

import uuid as py_uuid
from typing import Literal

from app.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    DefinerVariableSchema,
    EdgeRead,
    EndNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    NodeRead,
    SlotRead,
    StartNode,
)


def build_default_trivia_graph_flow_data() -> GraphFlowData:
    nodes: list[NodeRead] = [
        StartNode(id="start"),
        LogicalAssignerNode(
            id="init_game",
            assignments=[
                LogicalAssignmentSchema(
                    id="init_score",
                    target_var_key="score",
                    value_type="number",
                    expression={"kind": "literal", "value": 0},
                ),
                LogicalAssignmentSchema(
                    id="init_more",
                    target_var_key="more_questions",
                    value_type="boolean",
                    expression={"kind": "literal", "value": True},
                ),
                LogicalAssignmentSchema(
                    id="init_correct_answer",
                    target_var_key="correct_answer",
                    value_type="string",
                    expression={"kind": "literal", "value": "A"},
                ),
            ],
        ),
        LogicalSwitchNode(
            id="loop_questions",
            slots=[
                SlotRead(
                    id="loop_questions_yes",
                    raw_string="Yes",
                    expression={"kind": "stateRef", "varKey": "more_questions"},
                ),
                SlotRead(
                    id="loop_questions_no",
                    raw_string="No",
                    expression={
                        "kind": "unaryOp",
                        "op": "not",
                        "expr": {"kind": "stateRef", "varKey": "more_questions"},
                    },
                ),
            ],
        ),
        AgenticAssignerNode(
            id="gen_question",
            prompt="Generate a fun trivia question for the player and set correct_answer to option A, B, C, or D.",
            agentic_inputs=[],
            agentic_outputs=["current_question", "correct_answer"],
        ),
        InterruptNode(
            id="ask_question",
            payload_vars=["current_question"],
            resume_var="user_answer",
        ),
        LogicalAssignerNode(
            id="parse_answer",
            assignments=[
                LogicalAssignmentSchema(
                    id="parse_extract",
                    target_var_key="parsed_answer",
                    value_type="string",
                    expression={"kind": "stateRef", "varKey": "user_answer"},
                )
            ],
        ),
        AgenticSwitchNode(
            id="lifeline_switch",
            prompt="Determine if user wants to submit answer or use a lifeline from user_answer: '{user_answer}'.",
            agentic_inputs=["user_answer"],
            slots=[
                SlotRead(id="lifeline_switch_submit", raw_string="Submit"),
                SlotRead(id="lifeline_switch_lifeline", raw_string="Lifeline"),
            ],
        ),
        AgenticSwitchNode(
            id="choose_lifeline",
            prompt="Determine which lifeline user selected from user_answer: '{user_answer}'.",
            agentic_inputs=["user_answer"],
            slots=[
                SlotRead(id="choose_lifeline_audience", raw_string="Audience"),
                SlotRead(id="choose_lifeline_phone", raw_string="Phone"),
            ],
        ),
        AgenticAssignerNode(
            id="audience_votes",
            prompt="Poll audience for advice on question: '{current_question}'.",
            agentic_inputs=["current_question"],
            agentic_outputs=["audience_poll_result"],
        ),
        AgenticAssignerNode(
            id="phone_advice",
            prompt="Call a friend for advice on question: '{current_question}'.",
            agentic_inputs=["current_question"],
            agentic_outputs=["phone_call_advice"],
        ),
        LogicalAssignerNode(
            id="check_correct",
            assignments=[
                LogicalAssignmentSchema(
                    id="validate_check",
                    target_var_key="is_correct",
                    value_type="boolean",
                    expression={
                        "kind": "binaryOp",
                        "op": "==",
                        "left": {"kind": "stateRef", "varKey": "parsed_answer"},
                        "right": {"kind": "stateRef", "varKey": "correct_answer"},
                    },
                )
            ],
        ),
        LogicalSwitchNode(
            id="result_switch",
            slots=[
                SlotRead(
                    id="result_switch_correct",
                    raw_string="correct",
                    expression={"kind": "stateRef", "varKey": "is_correct"},
                ),
                SlotRead(
                    id="result_switch_wrong",
                    raw_string="wrong",
                    expression={"kind": "unaryOp", "op": "not", "expr": {"kind": "stateRef", "varKey": "is_correct"}},
                ),
            ],
        ),
        LogicalAssignerNode(
            id="increment_score",
            assignments=[
                LogicalAssignmentSchema(
                    id="add_score",
                    target_var_key="score",
                    value_type="number",
                    expression={
                        "kind": "binaryOp",
                        "op": "+",
                        "left": {"kind": "stateRef", "varKey": "score"},
                        "right": {"kind": "literal", "value": 1},
                    },
                )
            ],
        ),
        EndNode(id="end"),
    ]

    def make_edge(
        edge_id_str: str,
        src_id: str,
        src_type: Literal["node", "slot"],
        tgt_id: str,
        tgt_type: Literal["node", "slot"] = "node",
    ) -> EdgeRead:
        return EdgeRead(
            id=py_uuid.uuid5(py_uuid.NAMESPACE_DNS, edge_id_str),
            source_id=src_id,
            source_type=src_type,
            target_id=tgt_id,
            target_type=tgt_type,
        )

    edges = [
        make_edge("start->init_game", "start", "node", "init_game"),
        make_edge("init_game->loop_questions", "init_game", "node", "loop_questions"),
        make_edge("loop_questions_yes->gen_question", "loop_questions_yes", "slot", "gen_question"),
        make_edge("loop_questions_no->end", "loop_questions_no", "slot", "end"),
        make_edge("gen_question->ask_question", "gen_question", "node", "ask_question"),
        make_edge("ask_question->parse_answer", "ask_question", "node", "parse_answer"),
        make_edge("parse_answer->lifeline_switch", "parse_answer", "node", "lifeline_switch"),
        make_edge("lifeline_switch_submit->check_correct", "lifeline_switch_submit", "slot", "check_correct"),
        make_edge("lifeline_switch_lifeline->choose_lifeline", "lifeline_switch_lifeline", "slot", "choose_lifeline"),
        make_edge("choose_lifeline_audience->audience_votes", "choose_lifeline_audience", "slot", "audience_votes"),
        make_edge("choose_lifeline_phone->phone_advice", "choose_lifeline_phone", "slot", "phone_advice"),
        make_edge("audience_votes->ask_question", "audience_votes", "node", "ask_question"),
        make_edge("phone_advice->ask_question", "phone_advice", "node", "ask_question"),
        make_edge("check_correct->result_switch", "check_correct", "node", "result_switch"),
        make_edge("result_switch_correct->increment_score", "result_switch_correct", "slot", "increment_score"),
        make_edge("result_switch_wrong->end", "result_switch_wrong", "slot", "end"),
        make_edge("increment_score->loop_questions", "increment_score", "node", "loop_questions"),
    ]

    state = [
        DefinerVariableSchema(id="v1", key="score", type="number", default_value=0),
        DefinerVariableSchema(id="v2", key="more_questions", type="boolean", default_value=True),
        DefinerVariableSchema(id="v3", key="current_question", type="string", default_value=""),
        DefinerVariableSchema(id="v4", key="user_answer", type="string", default_value=""),
        DefinerVariableSchema(id="v5", key="parsed_answer", type="string", default_value=""),
        DefinerVariableSchema(id="v6", key="is_correct", type="boolean", default_value=False),
        DefinerVariableSchema(id="v7", key="correct_answer", type="string", default_value="A"),
        DefinerVariableSchema(id="v8", key="audience_poll_result", type="string", default_value=""),
        DefinerVariableSchema(id="v9", key="phone_call_advice", type="string", default_value=""),
    ]

    return GraphFlowData(nodes=nodes, edges=edges, state=state)
