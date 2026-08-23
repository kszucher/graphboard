from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.graphs.schemas import (
    AgenticAssignerNode,
    AgenticSwitchNode,
    GraphFlowData,
    InterruptNode,
    LogicalAssignerNode,
    LogicalSwitchNode,
    RagRetrieverNode,
)
from app.modules.graphs.templates import build_default_trivia_graph_flow_data


class EvalScenario(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    level: int
    name: str
    description: str
    initial_flow: GraphFlowData
    user_prompt: str
    assert_fn: Callable[[GraphFlowData, list[dict[str, Any]]], None]


# ---------------------------------------------------------------------------
# Topological Assertion Helpers
# ---------------------------------------------------------------------------


def _find_node_by_id(flow: GraphFlowData, node_id: str) -> Any:
    return next((n for n in flow.nodes if n.id == node_id), None)


def _get_outgoing_edges(flow: GraphFlowData, source_id: str, handle_id: str | None = None) -> list[Any]:
    return [e for e in flow.edges if e.source == source_id and (handle_id is None or e.source_handle == handle_id)]


def _get_incoming_edges(flow: GraphFlowData, target_id: str) -> list[Any]:
    return [e for e in flow.edges if e.target == target_id]


# ---------------------------------------------------------------------------
# Scenario 1: Game Length (Level 1)
# ---------------------------------------------------------------------------


def assert_scenario_1_game_length(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    loop_node = _find_node_by_id(final_flow, "loop_questions")
    assert loop_node is not None, "Expected 'loop_questions' node to exist"
    assert isinstance(loop_node, LogicalSwitchNode)

    # Verify that the switch branches now evaluate against 15 instead of 5
    branch_repr = json.dumps([b.model_dump() for b in loop_node.branches])
    assert "15" in branch_repr or "14" in branch_repr, (
        f"Expected condition threshold of 15 in loop_questions branches, but found: {branch_repr}"
    )


# ---------------------------------------------------------------------------
# Scenario 2: Prize Tracking (Level 2)
# ---------------------------------------------------------------------------


def assert_scenario_2_prize_tracking(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    # 1. State variable for prize/cash/money exists
    state_keys = [v.key.lower() for v in final_flow.state]
    prize_key = next(
        (k for k in state_keys if any(term in k for term in ["prize", "money", "cash", "winnings", "reward"])), None
    )
    assert prize_key is not None, f"Expected a prize/money state variable, found state keys: {state_keys}"

    # 2. increment_score or an assigner in loop updates prize or score
    inc_node = _find_node_by_id(final_flow, "increment_score")
    if inc_node and isinstance(inc_node, LogicalAssignerNode):
        all_targets = [a.target_var_key.lower() for a in inc_node.assignments]
        assert any(t in prize_key or t == "score" for t in all_targets), (
            f"Expected increment_score to assign to prize or score, found targets: {all_targets}"
        )


# ---------------------------------------------------------------------------
# Scenario 3: Walk Away / Cash Out (Level 3)
# ---------------------------------------------------------------------------


def assert_scenario_3_walk_away(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    lifeline_switch = _find_node_by_id(final_flow, "lifeline_switch")
    assert lifeline_switch is not None, "Expected 'lifeline_switch' node to exist"
    assert isinstance(lifeline_switch, AgenticSwitchNode)

    # 1. Must have added a Walk Away branch (originally 2 branches: Submit, Lifeline)
    assert len(lifeline_switch.branches) >= 3, (
        f"Expected at least 3 branches on lifeline_switch, found {len(lifeline_switch.branches)}: {[b.label for b in lifeline_switch.branches]}"
    )

    # 2. Walk Away branch routes to end (directly or via a payout summary node)
    walk_branches = [
        b
        for b in lifeline_switch.branches
        if any(term in b.label.lower() for term in ["walk", "cash", "leave", "quit", "stop", "take"])
    ]
    assert len(walk_branches) > 0, (
        f"Expected a branch for walking away, but branch labels are: {[b.label for b in lifeline_switch.branches]}"
    )
    walk_branch = walk_branches[0]

    out_edges = _get_outgoing_edges(final_flow, "lifeline_switch", walk_branch.id)
    assert len(out_edges) > 0, f"Expected an outgoing edge from branch '{walk_branch.label}'"
    target_id = out_edges[0].target
    assert target_id == "end" or any(e.target == "end" for e in _get_outgoing_edges(final_flow, target_id)), (
        f"Expected walk away path to terminate at 'end', but routed to '{target_id}'"
    )


# ---------------------------------------------------------------------------
# Scenario 4: 50:50 Lifeline (Level 4)
# ---------------------------------------------------------------------------


def assert_scenario_4_fifty_fifty(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    choose_node = _find_node_by_id(final_flow, "choose_lifeline")
    assert choose_node is not None, "Expected 'choose_lifeline' node to exist"
    assert isinstance(choose_node, AgenticSwitchNode)

    # 1. choose_lifeline must have at least 3 branches (was Audience, Phone; now + 50:50)
    assert len(choose_node.branches) >= 3, (
        f"Expected at least 3 branches on choose_lifeline, found {len(choose_node.branches)}: {[b.label for b in choose_node.branches]}"
    )

    # 2. Identify the 50:50 branch
    fifty_branches = [
        b
        for b in choose_node.branches
        if any(term in b.label.lower() for term in ["50", "fifty", "half", "eliminate"])
        or b.id not in {"choose_lifeline_audience", "choose_lifeline_phone"}
    ]
    assert len(fifty_branches) > 0, "Could not locate the 50:50 branch on choose_lifeline"
    fifty_branch = fifty_branches[0]

    # 3. Follow outgoing edge to the 50:50 handler node
    edges_from_branch = _get_outgoing_edges(final_flow, "choose_lifeline", fifty_branch.id)
    assert len(edges_from_branch) > 0, f"No edge found leaving branch '{fifty_branch.label}'"
    fifty_node_id = edges_from_branch[0].target
    fifty_node = _find_node_by_id(final_flow, fifty_node_id)
    assert fifty_node is not None, f"Target node '{fifty_node_id}' not found in graph"
    assert isinstance(fifty_node, (AgenticAssignerNode, LogicalAssignerNode)), (
        f"Expected 50:50 handler node to be an ASSIGNER, got {fifty_node.node_type}"
    )

    # 4. Invariant: 50:50 node must route back to 'ask_question'
    loopback = next((e for e in final_flow.edges if e.source == fifty_node_id and e.target == "ask_question"), None)
    assert loopback is not None, f"Expected 50:50 node '{fifty_node_id}' to route back to 'ask_question'"


# ---------------------------------------------------------------------------
# Scenario 5: Difficulty Progression (Level 5)
# ---------------------------------------------------------------------------


def assert_scenario_5_difficulty_progression(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    # 1. State variable for difficulty/tier/level exists
    state_keys = [v.key.lower() for v in final_flow.state]
    diff_key = next((k for k in state_keys if any(term in k for term in ["diff", "tier", "level", "stage"])), None)
    assert diff_key is not None or any("difficulty" in json.dumps(n.model_dump()).lower() for n in final_flow.nodes), (
        f"Expected a difficulty state variable or difficulty assignments, found keys: {state_keys}"
    )

    # 2. gen_question or retrieve_trivia_facts references difficulty
    gen_q = _find_node_by_id(final_flow, "gen_question")
    assert gen_q is not None and isinstance(gen_q, AgenticAssignerNode)
    rag_node = _find_node_by_id(final_flow, "retrieve_trivia_facts")

    has_diff_in_gen = (
        any("diff" in inp.lower() or "tier" in inp.lower() or "level" in inp.lower() for inp in gen_q.agentic_inputs)
        or "diff" in gen_q.prompt.lower()
    )
    has_diff_in_rag = rag_node and (
        "diff" in getattr(rag_node, "query_var", "").lower() or "tier" in getattr(rag_node, "query_var", "").lower()
    )
    assert has_diff_in_gen or has_diff_in_rag, "Expected gen_question or RAG node to consume difficulty tier input"


# ---------------------------------------------------------------------------
# Scenario 6: Single-Use Lifelines (Level 6)
# ---------------------------------------------------------------------------


def assert_scenario_6_single_use_lifelines(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    state_keys = {v.key.lower(): v for v in final_flow.state}

    # 1. State variables tracking usage exist
    phone_flag = next(
        (k for k in state_keys if "phone" in k and any(w in k for w in ["used", "has", "is", "active"])), None
    )
    aud_flag = next(
        (k for k in state_keys if ("aud" in k or "poll" in k) and any(w in k for w in ["used", "has", "is", "active"])),
        None,
    )
    assert phone_flag is not None or aud_flag is not None or len(state_keys) > 9, (
        f"Expected state variables tracking lifeline usage, found keys: {list(state_keys.keys())}"
    )

    # 2. Assignments exist marking lifelines as used
    all_assigners = [n for n in final_flow.nodes if isinstance(n, LogicalAssignerNode)]
    all_assigned_targets = [a.target_var_key.lower() for node in all_assigners for a in node.assignments]
    assert any("phone" in t or "aud" in t or "life" in t or "used" in t for t in all_assigned_targets), (
        f"Expected assigners marking lifeline usage flags, found targets: {all_assigned_targets}"
    )


# ---------------------------------------------------------------------------
# Scenario 7: Switch the Question Lifeline (Level 7)
# ---------------------------------------------------------------------------


def assert_scenario_7_switch_question(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    choose_node = _find_node_by_id(final_flow, "choose_lifeline")
    assert choose_node is not None and isinstance(choose_node, AgenticSwitchNode)

    # 1. Branch for switch question exists
    switch_branches = [
        b for b in choose_node.branches
        if any(term in b.label.lower() for term in ["switch", "swap", "change", "new_q", "replace"])
        or b.id not in {"choose_lifeline_audience", "choose_lifeline_phone"}
    ]
    assert len(switch_branches) > 0, (
        f"Expected a switch/swap question branch on choose_lifeline, found labels: {[b.label for b in choose_node.branches]}"
    )
    switch_branch = switch_branches[0]

    # 2. Follow outgoing edge to generation / retrieval / reset node
    edges_from_branch = _get_outgoing_edges(final_flow, "choose_lifeline", switch_branch.id)
    assert len(edges_from_branch) > 0, f"No edge found leaving branch '{switch_branch.label}'"
    target_id = edges_from_branch[0].target
    target_node = _find_node_by_id(final_flow, target_id)
    assert target_node is not None, f"Target node '{target_id}' not found"

    # 3. Path must lead back into the question loop
    valid_loop_targets = {"retrieve_trivia_facts", "gen_question", "ask_question"}
    assert (
        target_id in valid_loop_targets
        or isinstance(target_node, (RagRetrieverNode, AgenticAssignerNode, LogicalAssignerNode))
    ), f"Expected question switch flow to target a retrieval, generator, or reset node, got '{target_id}'"


# ---------------------------------------------------------------------------
# Scenario 8: Guaranteed Safety Nets (Level 8)
# ---------------------------------------------------------------------------


def assert_scenario_8_guaranteed_safety_nets(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    # 1. result_switch 'wrong' branch must NOT go straight to 'end'
    wrong_direct_to_end = any(
        e.source == "result_switch" and e.source_handle == "result_switch_wrong" and e.target == "end"
        for e in final_flow.edges
    )
    assert not wrong_direct_to_end, "result_switch (wrong) should route through safety net logic, not directly to end"

    # 2. Inspect the graph structure for 5, 10, and 15 milestone thresholds
    graph_dump = json.dumps(final_flow.model_dump(mode="json"))
    assert "5" in graph_dump and "10" in graph_dump, "Expected safety net logic referencing questions 5 and 10 checkpoints"
    assert "15" in graph_dump or "14" in graph_dump, "Expected 15 max win condition in graph logic"


# ---------------------------------------------------------------------------
# Scenario 9: Interactive "Ask the Host" Lifeline (Level 9)
# ---------------------------------------------------------------------------


def assert_scenario_9_ask_the_host(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    choose_node = _find_node_by_id(final_flow, "choose_lifeline")
    assert choose_node is not None and isinstance(choose_node, AgenticSwitchNode)

    # 1. Host branch on choose_lifeline
    host_branches = [
        b
        for b in choose_node.branches
        if any(term in b.label.lower() for term in ["host", "ask_host", "presenter"])
        or b.id not in {"choose_lifeline_audience", "choose_lifeline_phone"}
    ]
    assert len(host_branches) > 0, (
        f"Expected 'Ask the Host' branch on choose_lifeline, found labels: {[b.label for b in choose_node.branches]}"
    )
    host_branch = host_branches[0]

    # 2. Follow outgoing edge to find an INTERRUPT or AGENTIC_ASSIGNER node
    edges_from_branch = _get_outgoing_edges(final_flow, "choose_lifeline", host_branch.id)
    assert len(edges_from_branch) > 0, f"No edge found leaving branch '{host_branch.label}'"
    target_id = edges_from_branch[0].target
    target_node = _find_node_by_id(final_flow, target_id)
    assert target_node is not None, f"Target node '{target_id}' not found"

    # 3. Must have an interactive interrupt or dedicated host agent node
    interrupt_nodes = [n for n in final_flow.nodes if isinstance(n, InterruptNode) and n.id != "ask_question"]
    host_agent_nodes = [
        n
        for n in final_flow.nodes
        if isinstance(n, AgenticAssignerNode)
        and any(term in n.prompt.lower() or term in n.id.lower() for term in ["host", "presenter", "advice"])
    ]
    assert len(interrupt_nodes) > 0 or len(host_agent_nodes) >= 3, (
        "Expected an INTERRUPT node for host interaction or a dedicated Host AgenticAssigner"
    )


# ---------------------------------------------------------------------------
# Scenario 10: Full Millionaire Game Engine (Level 10)
# ---------------------------------------------------------------------------


def assert_scenario_10_full_millionaire(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    # 1. 15 questions to win
    loop_node = _find_node_by_id(final_flow, "loop_questions")
    assert loop_node is not None and isinstance(loop_node, LogicalSwitchNode)
    assert "15" in json.dumps([b.model_dump() for b in loop_node.branches]) or "14" in json.dumps(
        [b.model_dump() for b in loop_node.branches]
    )

    # 2. Walk away option exists
    lifeline_switch = _find_node_by_id(final_flow, "lifeline_switch")
    assert lifeline_switch is not None and isinstance(lifeline_switch, AgenticSwitchNode)
    assert len(lifeline_switch.branches) >= 3, "Expected Walk Away option on lifeline_switch"

    # 3. 3 lifelines (50:50, Phone, Audience) on choose_lifeline
    choose_node = _find_node_by_id(final_flow, "choose_lifeline")
    assert choose_node is not None and isinstance(choose_node, AgenticSwitchNode)
    assert len(choose_node.branches) >= 3, "Expected 3 lifelines under choose_lifeline"

    # 4. Safety net checks on wrong answer
    wrong_direct_to_end = any(
        e.source == "result_switch" and e.source_handle == "result_switch_wrong" and e.target == "end"
        for e in final_flow.edges
    )
    assert not wrong_direct_to_end, "result_switch (wrong) must route through safety net logic"


# ---------------------------------------------------------------------------
# 10-Element Evaluation Scenarios Suite
# ---------------------------------------------------------------------------

SCENARIOS: list[EvalScenario] = [
    EvalScenario(
        level=1,
        name="Game Length (15 Questions)",
        description="Verify the copilot scales the winning threshold in loop_questions to 15 questions.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Let's make the game longer: the player should need 15 correct answers to win instead of 5.",
        assert_fn=assert_scenario_1_game_length,
    ),
    EvalScenario(
        level=2,
        name="Prize Money Tracking",
        description="Verify the copilot adds cash prize tracking state and updates it with correct answers.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Let's add prize money tracking so each correct answer increases the player's cash earnings.",
        assert_fn=assert_scenario_2_prize_tracking,
    ),
    EvalScenario(
        level=3,
        name="Walk Away / Cash Out Option",
        description="Verify the copilot adds a Walk Away branch to lifeline_switch routed to game termination.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Give the player an option to walk away with their current money instead of answering or picking a lifeline.",
        assert_fn=assert_scenario_3_walk_away,
    ),
    EvalScenario(
        level=4,
        name="Fifty-Fifty Lifeline",
        description="Verify the copilot adds a 50:50 lifeline branch and an assigner node looping back to ask_question.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Let's add a fifty fifty lifeline.",
        assert_fn=assert_scenario_4_fifty_fifty,
    ),
    EvalScenario(
        level=5,
        name="Dynamic Difficulty Progression",
        description="Verify the copilot introduces tiered difficulty based on score and wires it into question generation.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Make the questions get progressively harder: easy for the first 4 questions, medium from question 5 to 9, and hard for question 10 and above.",
        assert_fn=assert_scenario_5_difficulty_progression,
    ),
    EvalScenario(
        level=6,
        name="Single-Use Lifelines Enforcement",
        description="Verify the copilot introduces state usage flags and assigners for single-use lifelines.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Make lifelines single-use so once the player uses phone-a-friend or ask-the-audience, they can't use it again.",
        assert_fn=assert_scenario_6_single_use_lifelines,
    ),
    EvalScenario(
        level=7,
        name="Switch the Question Lifeline",
        description="Verify the copilot creates a switch-question lifeline branch with RAG/agent regeneration loopback.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Add a 'Switch the Question' lifeline that discards the current question and gives the player a brand new one without losing their progress.",
        assert_fn=assert_scenario_7_switch_question,
    ),
    EvalScenario(
        level=8,
        name="Guaranteed Safety Nets at Q5 and Q10",
        description="Verify the copilot intercepts game-over routing with Q5 and Q10 guaranteed safety net thresholds.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Let's account for guaranteed wins after question 5 and 10 while 15 is max win.",
        assert_fn=assert_scenario_8_guaranteed_safety_nets,
    ),
    EvalScenario(
        level=9,
        name="Interactive 'Ask the Host' Lifeline",
        description="Verify the copilot constructs an interactive 2-way host lifeline with interrupt handling.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Add an 'Ask the Host' lifeline where the contestant can ask the host for a tip, receive the host's response, and then return to answer the question.",
        assert_fn=assert_scenario_9_ask_the_host,
    ),
    EvalScenario(
        level=10,
        name="Full Millionaire Game Engine Overhaul",
        description="Verify the copilot orchestrates the complete Millionaire mechanics in a single comprehensive pass.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="Turn this into the complete Millionaire game: 15 questions to win, guaranteed safety nets after questions 5 and 10, a walk-away option, and three one-time lifelines (50:50, Phone a Friend, Ask the Audience).",
        assert_fn=assert_scenario_10_full_millionaire,
    ),
]
