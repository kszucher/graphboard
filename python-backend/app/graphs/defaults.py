from __future__ import annotations

from app.constants import NodeType
from app.graphs import mutations
from app.graphs.builder import GraphBuilder
from app.graphs.schemas import GraphFlowData


def build_default_trivia_graph_flow_data() -> GraphFlowData:
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    b = GraphBuilder()

    # 1. State Variables
    b.state("score", "number", 0, id="v1")
    b.state("more_questions", "boolean", True, id="v2")
    b.state("current_question", "string", "", id="v3")
    b.state("user_answer", "string", "", id="v4")
    b.state("parsed_answer", "string", "", id="v5")
    b.state("is_correct", "boolean", False, id="v6")
    b.state("correct_answer", "string", "A", id="v7")
    b.state("audience_poll_result", "string", "", id="v8")
    b.state("phone_call_advice", "string", "", id="v9")

    # 2. Nodes & Connections
    start = b.start_chain("start", NodeType.START)

    init_game = start.then_node(
        "init_game",
        NodeType.LOGICAL_ASSIGNER,
        config={
            "assignments": [
                {
                    "id": "init_score",
                    "target_var_key": "score",
                    "value_type": "number",
                    "expression": {"kind": "literal", "value": 0},
                },
                {
                    "id": "init_more",
                    "target_var_key": "more_questions",
                    "value_type": "boolean",
                    "expression": {"kind": "literal", "value": True},
                },
                {
                    "id": "init_correct_answer",
                    "target_var_key": "correct_answer",
                    "value_type": "string",
                    "expression": {"kind": "literal", "value": "A"},
                },
            ]
        },
    )

    loop_questions = init_game.then_node(
        "loop_questions",
        NodeType.LOGICAL_SWITCH,
        config={
            "slots": [
                {
                    "id": "loop_questions_yes",
                    "raw_string": "Yes",
                    "expression": {"kind": "stateRef", "varKey": "more_questions"},
                },
                {
                    "id": "loop_questions_no",
                    "raw_string": "No",
                    "expression": {
                        "kind": "unaryOp",
                        "op": "not",
                        "expr": {"kind": "stateRef", "varKey": "more_questions"},
                    },
                },
            ]
        },
    )

    # loop_questions_no -> end
    loop_questions.slot("loop_questions_no").then_node("end", NodeType.END)

    # loop_questions_yes -> gen_question
    gen_question = loop_questions.slot("loop_questions_yes").then_node(
        "gen_question",
        NodeType.AGENTIC_ASSIGNER,
        config={
            "prompt": "Generate a fun trivia question for the player and set correct_answer to option A, B, C, or D.",
            "agentic_inputs": [],
            "agentic_outputs": ["current_question", "correct_answer"],
        },
    )

    ask_question = gen_question.then_node(
        "ask_question",
        NodeType.INTERRUPT,
        config={"payload_vars": ["current_question"], "resume_var": "user_answer"},
    )

    parse_answer = ask_question.then_node(
        "parse_answer",
        NodeType.LOGICAL_ASSIGNER,
        config={
            "assignments": [
                {
                    "id": "parse_extract",
                    "target_var_key": "parsed_answer",
                    "value_type": "string",
                    "expression": {"kind": "stateRef", "varKey": "user_answer"},
                }
            ]
        },
    )

    lifeline_switch = parse_answer.then_node(
        "lifeline_switch",
        NodeType.AGENTIC_SWITCH,
        config={
            "agentic_input": "user_answer",
            "slots": [
                {"id": "lifeline_switch_submit", "raw_string": "Submit"},
                {"id": "lifeline_switch_lifeline", "raw_string": "Lifeline"},
            ],
        },
    )

    # lifeline_switch_lifeline -> choose_lifeline
    choose_lifeline = lifeline_switch.slot("lifeline_switch_lifeline").then_node(
        "choose_lifeline",
        NodeType.AGENTIC_SWITCH,
        config={
            "agentic_input": "user_answer",
            "slots": [
                {"id": "choose_lifeline_audience", "raw_string": "Audience"},
                {"id": "choose_lifeline_phone", "raw_string": "Phone"},
            ],
        },
    )

    # choose_lifeline_audience -> audience_votes -> ask_question
    choose_lifeline.slot("choose_lifeline_audience").then_node(
        "audience_votes",
        NodeType.AGENTIC_ASSIGNER,
        config={
            "prompt": "Poll audience for advice on question: '{current_question}'.",
            "agentic_inputs": ["current_question"],
            "agentic_outputs": ["audience_poll_result"],
        },
    ).then_to("ask_question")

    # choose_lifeline_phone -> phone_advice -> ask_question
    choose_lifeline.slot("choose_lifeline_phone").then_node(
        "phone_advice",
        NodeType.AGENTIC_ASSIGNER,
        config={
            "prompt": "Call a friend for advice on question: '{current_question}'.",
            "agentic_inputs": ["current_question"],
            "agentic_outputs": ["phone_call_advice"],
        },
    ).then_to("ask_question")

    # lifeline_switch_submit -> check_correct
    check_correct = lifeline_switch.slot("lifeline_switch_submit").then_node(
        "check_correct",
        NodeType.LOGICAL_ASSIGNER,
        config={
            "assignments": [
                {
                    "id": "validate_check",
                    "target_var_key": "is_correct",
                    "value_type": "boolean",
                    "expression": {
                        "kind": "binaryOp",
                        "op": "==",
                        "left": {"kind": "stateRef", "varKey": "parsed_answer"},
                        "right": {"kind": "stateRef", "varKey": "correct_answer"},
                    },
                }
            ]
        },
    )

    result_switch = check_correct.then_node(
        "result_switch",
        NodeType.LOGICAL_SWITCH,
        config={
            "slots": [
                {
                    "id": "result_switch_correct",
                    "raw_string": "correct",
                    "expression": {"kind": "stateRef", "varKey": "is_correct"},
                },
                {
                    "id": "result_switch_wrong",
                    "raw_string": "wrong",
                    "expression": {
                        "kind": "unaryOp",
                        "op": "not",
                        "expr": {"kind": "stateRef", "varKey": "is_correct"},
                    },
                },
            ]
        },
    )

    # result_switch_wrong -> end
    result_switch.slot("result_switch_wrong").then_to("end")

    # result_switch_correct -> increment_score -> loop_questions
    result_switch.slot("result_switch_correct").then_node(
        "increment_score",
        NodeType.LOGICAL_ASSIGNER,
        config={
            "assignments": [
                {
                    "id": "add_score",
                    "target_var_key": "score",
                    "value_type": "number",
                    "expression": {
                        "kind": "binaryOp",
                        "op": "+",
                        "left": {"kind": "stateRef", "varKey": "score"},
                        "right": {"kind": "literal", "value": 1},
                    },
                }
            ]
        },
    ).then_to("loop_questions")

    return mutations.apply_patch(flow, b.patch)
