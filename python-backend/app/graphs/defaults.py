from __future__ import annotations

from app.constants import NodeType
from app.graphs import mutations
from app.graphs.schemas import (
    ConnectOp,
    GraphFlowData,
    GraphOperation,
    UpsertNodeOp,
    UpsertStateVarOp,
)


def build_default_trivia_graph_flow_data() -> GraphFlowData:
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    patch: list[GraphOperation] = [
        # 1. State Variables
        UpsertStateVarOp(op="upsert_state_var", id="v1", key="score", type="number", default_value=0),
        UpsertStateVarOp(
            op="upsert_state_var", id="v2", key="more_questions", type="boolean", default_value=True
        ),
        UpsertStateVarOp(
            op="upsert_state_var", id="v3", key="current_question", type="string", default_value=""
        ),
        UpsertStateVarOp(op="upsert_state_var", id="v4", key="user_answer", type="string", default_value=""),
        UpsertStateVarOp(op="upsert_state_var", id="v5", key="parsed_answer", type="string", default_value=""),
        UpsertStateVarOp(op="upsert_state_var", id="v6", key="is_correct", type="boolean", default_value=False),
        UpsertStateVarOp(op="upsert_state_var", id="v7", key="correct_answer", type="string", default_value="A"),
        UpsertStateVarOp(
            op="upsert_state_var", id="v8", key="audience_poll_result", type="string", default_value=""
        ),
        UpsertStateVarOp(
            op="upsert_state_var", id="v9", key="phone_call_advice", type="string", default_value=""
        ),
        # 2. Nodes
        UpsertNodeOp(op="upsert_node", node_id="start", node_type=NodeType.START),
        UpsertNodeOp(
            op="upsert_node",
            node_id="init_game",
            node_type=NodeType.LOGICAL_ASSIGNER,
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
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="loop_questions",
            node_type=NodeType.LOGICAL_SWITCH,
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
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="gen_question",
            node_type=NodeType.AGENTIC_ASSIGNER,
            config={
                "prompt": "Generate a fun trivia question for the player and set correct_answer to option A, B, C, or D.",
                "agentic_inputs": [],
                "agentic_outputs": ["current_question", "correct_answer"],
            },
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="ask_question",
            node_type=NodeType.INTERRUPT,
            config={"payload_vars": ["current_question"], "resume_var": "user_answer"},
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="parse_answer",
            node_type=NodeType.LOGICAL_ASSIGNER,
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
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="lifeline_switch",
            node_type=NodeType.AGENTIC_SWITCH,
            config={
                "agentic_input": "user_answer",
                "slots": [
                    {"id": "lifeline_switch_submit", "raw_string": "Submit"},
                    {"id": "lifeline_switch_lifeline", "raw_string": "Lifeline"},
                ],
            },
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="choose_lifeline",
            node_type=NodeType.AGENTIC_SWITCH,
            config={
                "agentic_input": "user_answer",
                "slots": [
                    {"id": "choose_lifeline_audience", "raw_string": "Audience"},
                    {"id": "choose_lifeline_phone", "raw_string": "Phone"},
                ],
            },
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="audience_votes",
            node_type=NodeType.AGENTIC_ASSIGNER,
            config={
                "prompt": "Poll audience for advice on question: '{current_question}'.",
                "agentic_inputs": ["current_question"],
                "agentic_outputs": ["audience_poll_result"],
            },
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="phone_advice",
            node_type=NodeType.AGENTIC_ASSIGNER,
            config={
                "prompt": "Call a friend for advice on question: '{current_question}'.",
                "agentic_inputs": ["current_question"],
                "agentic_outputs": ["phone_call_advice"],
            },
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="check_correct",
            node_type=NodeType.LOGICAL_ASSIGNER,
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
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="result_switch",
            node_type=NodeType.LOGICAL_SWITCH,
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
        ),
        UpsertNodeOp(
            op="upsert_node",
            node_id="increment_score",
            node_type=NodeType.LOGICAL_ASSIGNER,
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
        ),
        UpsertNodeOp(op="upsert_node", node_id="end", node_type=NodeType.END),
        # 3. Edges
        ConnectOp(op="connect", source_id="start", target_id="init_game"),
        ConnectOp(op="connect", source_id="init_game", target_id="loop_questions"),
        ConnectOp(
            op="connect",
            source_id="loop_questions_yes",
            target_id="gen_question",
            source_type="slot",
            target_type="node",
        ),
        ConnectOp(
            op="connect",
            source_id="loop_questions_no",
            target_id="end",
            source_type="slot",
            target_type="node",
        ),
        ConnectOp(op="connect", source_id="gen_question", target_id="ask_question"),
        ConnectOp(op="connect", source_id="ask_question", target_id="parse_answer"),
        ConnectOp(op="connect", source_id="parse_answer", target_id="lifeline_switch"),
        ConnectOp(
            op="connect",
            source_id="lifeline_switch_submit",
            target_id="check_correct",
            source_type="slot",
            target_type="node",
        ),
        ConnectOp(
            op="connect",
            source_id="lifeline_switch_lifeline",
            target_id="choose_lifeline",
            source_type="slot",
            target_type="node",
        ),
        ConnectOp(
            op="connect",
            source_id="choose_lifeline_audience",
            target_id="audience_votes",
            source_type="slot",
            target_type="node",
        ),
        ConnectOp(
            op="connect",
            source_id="choose_lifeline_phone",
            target_id="phone_advice",
            source_type="slot",
            target_type="node",
        ),
        ConnectOp(op="connect", source_id="audience_votes", target_id="ask_question"),
        ConnectOp(op="connect", source_id="phone_advice", target_id="ask_question"),
        ConnectOp(op="connect", source_id="check_correct", target_id="result_switch"),
        ConnectOp(
            op="connect",
            source_id="result_switch_correct",
            target_id="increment_score",
            source_type="slot",
            target_type="node",
        ),
        ConnectOp(
            op="connect",
            source_id="result_switch_wrong",
            target_id="end",
            source_type="slot",
            target_type="node",
        ),
        ConnectOp(op="connect", source_id="increment_score", target_id="loop_questions"),
    ]

    return mutations.apply_patch(flow, patch)
