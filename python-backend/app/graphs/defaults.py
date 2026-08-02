from __future__ import annotations

import uuid as py_uuid
from typing import Literal

from app.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    ConfirmNode,
    DefinerVariableSchema,
    EdgeRead,
    EndNode,
    ExtractNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    NodeRead,
    RetryNode,
    ReviewNode,
    SlotRead,
    StartNode,
    SwitchNode,
    ValidateNode,
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
        SwitchNode(
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
        ExtractNode(
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
        RetryNode(
            id="parse_retry",
            max_attempts=3,
            valid_expression={
                "kind": "binaryOp",
                "op": "!=",
                "left": {"kind": "stateRef", "varKey": "parsed_answer"},
                "right": {"kind": "literal", "value": ""},
            },
            slots=[
                SlotRead(id="parse_retry_valid", raw_string="valid"),
                SlotRead(id="parse_retry_retry", raw_string="retry"),
                SlotRead(id="parse_retry_exhausted", raw_string="exhausted"),
            ],
        ),
        LogicalAssignerNode(
            id="reset_parse_retry",
            assignments=[
                LogicalAssignmentSchema(
                    id="reset_parse_counter",
                    target_var_key="__retry_parse_retry_count",
                    value_type="number",
                    expression={"kind": "literal", "value": 0},
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
                SlotRead(id="choose_lifeline_fifty", raw_string="50-50"),
                SlotRead(id="choose_lifeline_audience", raw_string="Audience"),
                SlotRead(id="choose_lifeline_phone", raw_string="Phone"),
            ],
        ),
        LogicalAssignerNode(id="fifty_fifty", assignments=[]),
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
        ConfirmNode(
            id="confirm_answer",
            payload_vars=["parsed_answer"],
            slots=[
                SlotRead(id="confirm_answer_confirmed", raw_string="confirmed"),
                SlotRead(id="confirm_answer_rejected", raw_string="rejected"),
                SlotRead(id="confirm_answer_unclear", raw_string="unclear"),
            ],
        ),
        RetryNode(
            id="confirm_retry",
            max_attempts=2,
            valid_expression=None,
            slots=[
                SlotRead(id="confirm_retry_valid", raw_string="valid"),
                SlotRead(id="confirm_retry_retry", raw_string="retry"),
                SlotRead(id="confirm_retry_exhausted", raw_string="exhausted"),
            ],
        ),
        LogicalAssignerNode(
            id="reset_confirm_retry",
            assignments=[
                LogicalAssignmentSchema(
                    id="reset_confirm_counter",
                    target_var_key="__retry_confirm_retry_count",
                    value_type="number",
                    expression={"kind": "literal", "value": 0},
                )
            ],
        ),
        ValidateNode(
            id="validate_step",
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
        SwitchNode(
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
        ReviewNode(id="show_result"),
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
        make_edge("parse_answer->parse_retry", "parse_answer", "node", "parse_retry"),
        make_edge("parse_retry_valid->reset_parse_retry", "parse_retry_valid", "slot", "reset_parse_retry"),
        make_edge("reset_parse_retry->lifeline_switch", "reset_parse_retry", "node", "lifeline_switch"),
        make_edge("parse_retry_retry->ask_question", "parse_retry_retry", "slot", "ask_question"),
        make_edge("parse_retry_exhausted->end", "parse_retry_exhausted", "slot", "end"),
        make_edge("lifeline_switch_submit->confirm_answer", "lifeline_switch_submit", "slot", "confirm_answer"),
        make_edge("lifeline_switch_lifeline->choose_lifeline", "lifeline_switch_lifeline", "slot", "choose_lifeline"),
        make_edge("choose_lifeline_fifty->fifty_fifty", "choose_lifeline_fifty", "slot", "fifty_fifty"),
        make_edge("choose_lifeline_audience->audience_votes", "choose_lifeline_audience", "slot", "audience_votes"),
        make_edge("choose_lifeline_phone->phone_advice", "choose_lifeline_phone", "slot", "phone_advice"),
        make_edge("fifty_fifty->ask_question", "fifty_fifty", "node", "ask_question"),
        make_edge("audience_votes->ask_question", "audience_votes", "node", "ask_question"),
        make_edge("phone_advice->ask_question", "phone_advice", "node", "ask_question"),
        make_edge(
            "confirm_answer_confirmed->reset_confirm_retry", "confirm_answer_confirmed", "slot", "reset_confirm_retry"
        ),
        make_edge("reset_confirm_retry->validate_step", "reset_confirm_retry", "node", "validate_step"),
        make_edge("confirm_answer_rejected->ask_question", "confirm_answer_rejected", "slot", "ask_question"),
        make_edge("confirm_answer_unclear->confirm_retry", "confirm_answer_unclear", "slot", "confirm_retry"),
        make_edge("confirm_retry_retry->confirm_answer", "confirm_retry_retry", "slot", "confirm_answer"),
        make_edge("confirm_retry_exhausted->ask_question", "confirm_retry_exhausted", "slot", "ask_question"),
        make_edge("validate_step->result_switch", "validate_step", "node", "result_switch"),
        make_edge("result_switch_correct->increment_score", "result_switch_correct", "slot", "increment_score"),
        make_edge("result_switch_wrong->show_result", "result_switch_wrong", "slot", "show_result"),
        make_edge("increment_score->loop_questions", "increment_score", "node", "loop_questions"),
        make_edge("show_result->end", "show_result", "node", "end"),
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
