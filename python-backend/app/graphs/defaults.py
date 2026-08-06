from __future__ import annotations

from app.constants import NodeType
from app.graphs import mutations
from app.graphs.schemas import GraphFlowData
from app.copilot.tools import translate_tool_call_to_operations, sort_operations_by_dependency


def build_default_trivia_graph_flow_data() -> GraphFlowData:
    flow = GraphFlowData(nodes=[], edges=[], state=[])

    args = {
        "operations": [
            # 1. State Variables (use actual types for default_value)
            {"op": "upsert_state_var", "key": "score", "type": "number", "default_value": 0, "id": "v1"},
            {"op": "upsert_state_var", "key": "more_questions", "type": "boolean", "default_value": True, "id": "v2"},
            {"op": "upsert_state_var", "key": "current_question", "type": "string", "default_value": "", "id": "v3"},
            {"op": "upsert_state_var", "key": "user_answer", "type": "string", "default_value": "", "id": "v4"},
            {"op": "upsert_state_var", "key": "parsed_answer", "type": "string", "default_value": "", "id": "v5"},
            {"op": "upsert_state_var", "key": "is_correct", "type": "boolean", "default_value": False, "id": "v6"},
            {"op": "upsert_state_var", "key": "correct_answer", "type": "string", "default_value": "A", "id": "v7"},
            {
                "op": "upsert_state_var",
                "key": "audience_poll_result",
                "type": "string",
                "default_value": "",
                "id": "v8",
            },
            {"op": "upsert_state_var", "key": "phone_call_advice", "type": "string", "default_value": "", "id": "v9"},
            # 2. Nodes
            {"op": "upsert_node", "node_id": "start", "node_type": "START"},
            {"op": "upsert_node", "node_id": "end", "node_type": "END"},
            {
                "op": "upsert_node",
                "node_id": "init_game",
                "node_type": "LOGICAL_ASSIGNER",
                "config": {
                    "assignments": [
                        {"target_var_key": "score", "expression": "0"},
                        {"target_var_key": "more_questions", "expression": "True"},
                        {"target_var_key": "correct_answer", "expression": "'A'"},
                    ]
                },
            },
            {
                "op": "upsert_node",
                "node_id": "loop_questions",
                "node_type": "LOGICAL_SWITCH",
                "config": {
                    "slots": [
                        {"raw_string": "Yes", "expression": "more_questions"},
                        {"raw_string": "No", "expression": "not more_questions"},
                    ]
                },
            },
            {
                "op": "upsert_node",
                "node_id": "gen_question",
                "node_type": "AGENTIC_ASSIGNER",
                "config": {
                    "prompt": "Generate a fun trivia question for the player and set correct_answer to option A, B, C, or D.",
                    "agentic_inputs": [],
                    "agentic_outputs": ["current_question", "correct_answer"],
                },
            },
            {
                "op": "upsert_node",
                "node_id": "ask_question",
                "node_type": "INTERRUPT",
                "config": {
                    "payload_vars": ["current_question"],
                    "resume_var": "user_answer",
                },
            },
            {
                "op": "upsert_node",
                "node_id": "parse_answer",
                "node_type": "LOGICAL_ASSIGNER",
                "config": {"assignments": [{"target_var_key": "parsed_answer", "expression": "user_answer"}]},
            },
            {
                "op": "upsert_node",
                "node_id": "lifeline_switch",
                "node_type": "AGENTIC_SWITCH",
                "config": {
                    "agentic_input": "user_answer",
                    "slots": [
                        {"raw_string": "Submit"},
                        {"raw_string": "Lifeline"},
                    ],
                },
            },
            {
                "op": "upsert_node",
                "node_id": "choose_lifeline",
                "node_type": "AGENTIC_SWITCH",
                "config": {
                    "agentic_input": "user_answer",
                    "slots": [
                        {"raw_string": "Audience"},
                        {"raw_string": "Phone"},
                    ],
                },
            },
            {
                "op": "upsert_node",
                "node_id": "audience_votes",
                "node_type": "AGENTIC_ASSIGNER",
                "config": {
                    "prompt": "Poll audience for advice on question: '{current_question}'.",
                    "agentic_inputs": ["current_question"],
                    "agentic_outputs": ["audience_poll_result"],
                },
            },
            {
                "op": "upsert_node",
                "node_id": "phone_advice",
                "node_type": "AGENTIC_ASSIGNER",
                "config": {
                    "prompt": "Call a friend for advice on question: '{current_question}'.",
                    "agentic_inputs": ["current_question"],
                    "agentic_outputs": ["phone_call_advice"],
                },
            },
            {
                "op": "upsert_node",
                "node_id": "check_correct",
                "node_type": "LOGICAL_ASSIGNER",
                "config": {
                    "assignments": [{"target_var_key": "is_correct", "expression": "parsed_answer == correct_answer"}]
                },
            },
            {
                "op": "upsert_node",
                "node_id": "result_switch",
                "node_type": "LOGICAL_SWITCH",
                "config": {
                    "slots": [
                        {"raw_string": "correct", "expression": "is_correct"},
                        {"raw_string": "wrong", "expression": "not is_correct"},
                    ]
                },
            },
            {
                "op": "upsert_node",
                "node_id": "increment_score",
                "node_type": "LOGICAL_ASSIGNER",
                "config": {"assignments": [{"target_var_key": "score", "expression": "score + 1"}]},
            },
            # 3. Connections
            {"op": "connect", "source": "start", "target": "init_game"},
            {"op": "connect", "source": "init_game", "target": "loop_questions"},
            {"op": "connect", "source": "loop_questions", "case": "No", "target": "end"},
            {"op": "connect", "source": "loop_questions", "case": "Yes", "target": "gen_question"},
            {"op": "connect", "source": "gen_question", "target": "ask_question"},
            {"op": "connect", "source": "ask_question", "target": "parse_answer"},
            {"op": "connect", "source": "parse_answer", "target": "lifeline_switch"},
            {"op": "connect", "source": "lifeline_switch", "case": "Lifeline", "target": "choose_lifeline"},
            {"op": "connect", "source": "lifeline_switch", "case": "Submit", "target": "check_correct"},
            {"op": "connect", "source": "choose_lifeline", "case": "Audience", "target": "audience_votes"},
            {"op": "connect", "source": "choose_lifeline", "case": "Phone", "target": "phone_advice"},
            {"op": "connect", "source": "audience_votes", "target": "ask_question"},
            {"op": "connect", "source": "phone_advice", "target": "ask_question"},
            {"op": "connect", "source": "check_correct", "target": "result_switch"},
            {"op": "connect", "source": "result_switch", "case": "wrong", "target": "end"},
            {"op": "connect", "source": "result_switch", "case": "correct", "target": "increment_score"},
            {"op": "connect", "source": "increment_score", "target": "loop_questions"},
        ]
    }

    ops = translate_tool_call_to_operations(args)
    sorted_ops = sort_operations_by_dependency(ops)
    return mutations.apply_patch(flow, sorted_ops)
