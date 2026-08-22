from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.graphs.defaults import build_default_trivia_graph_flow_data
from app.modules.graphs.nodes import (
    Branch,
    EndNode,
    LogicalAssignerNode,
    LogicalAssignmentSchema,
    LogicalSwitchNode,
    StartNode,
)
from app.modules.graphs.schemas import (
    DefinerVariableSchema,
    EdgeRead,
    GraphFlowData,
)


class EvalScenario(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    initial_flow: GraphFlowData
    user_prompt: str
    assert_fn: Callable[[GraphFlowData, list[dict[str, Any]]], None]


def make_empty_flow() -> GraphFlowData:
    return GraphFlowData(
        nodes=[
            StartNode(id="start"),
            EndNode(id="end"),
        ],
        edges=[],
        state=[],
    )


def make_scenario_2_initial_flow() -> GraphFlowData:
    return GraphFlowData(
        nodes=[
            StartNode(id="start"),
            EndNode(id="end"),
            LogicalAssignerNode(
                id="init_vars",
                assignments=[
                    LogicalAssignmentSchema(
                        id="asgn_score",
                        target_var_key="score",
                        expression=0,
                    )
                ],
            ),
        ],
        edges=[
            EdgeRead(source="start", target="init_vars"),
            EdgeRead(source="init_vars", target="end"),
        ],
        state=[DefinerVariableSchema(id="v_score", key="score", type="number", default_value=0)],
    )


def assert_scenario_1(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    node_ids = {n.id for n in final_flow.nodes}
    assert "init_vars" in node_ids, f"Expected node 'init_vars' to be created, but got: {node_ids}"

    node = next(n for n in final_flow.nodes if n.id == "init_vars")
    assert isinstance(node, LogicalAssignerNode)

    assert len(node.assignments) > 0, "Expected assignments to be populated"
    assignment = node.assignments[0]
    assert assignment.target_var_key == "score", f"Expected target 'score', got '{assignment.target_var_key}'"

    edges = [(e.source, e.target) for e in final_flow.edges]
    assert ("start", "init_vars") in edges, f"Expected edge (start, init_vars), got: {edges}"
    assert ("init_vars", "end") in edges, f"Expected edge (init_vars, end), got: {edges}"


def assert_scenario_2(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    keys = {v.key for v in final_flow.state}
    assert "points" in keys, f"Expected variable 'points' in state, got: {keys}"
    assert "score" not in keys, f"Expected variable 'score' to be renamed and removed, but it's still in: {keys}"

    node = next(n for n in final_flow.nodes if n.id == "init_vars")
    assert isinstance(node, LogicalAssignerNode)
    assert node.assignments[0].target_var_key == "points", (
        f"Expected assignment target 'points', got: {node.assignments[0].target_var_key}"
    )


def assert_scenario_3(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    node_ids = {n.id for n in final_flow.nodes}
    assert "check_score" in node_ids, f"Expected 'check_score' node, got: {node_ids}"

    node = next(n for n in final_flow.nodes if n.id == "check_score")
    assert isinstance(node, LogicalSwitchNode)

    branches = node.branches
    assert len(branches) > 0, "Expected at least one branch"
    branch = branches[0]
    assert isinstance(branch, Branch)
    assert branch.label == "High", f"Expected branch label 'High', got: {branch.label}"

    assert branch.expression is not None
    expr_str = str(branch.expression)
    assert "score" in expr_str, f"Expected 'score' in expression: {expr_str}"
    assert "10" in expr_str, f"Expected '10' in expression: {expr_str}"

    edges = [(e.source, e.target) for e in final_flow.edges]
    assert ("init_vars", "check_score") in edges, f"Expected edge (init_vars, check_score), got: {edges}"


def assert_scenario_4(final_flow: GraphFlowData, ops: list[dict[str, Any]]) -> None:
    # 1. State variable 'question_retries' exists and defaults to 0
    vars_map = {v.key: v for v in final_flow.state}
    assert "question_retries" in vars_map, f"Expected state variable 'question_retries', but found: {vars_map.keys()}"
    assert vars_map["question_retries"].default_value == 0

    # 2. Node 'inc_retries' exists and is a LOGICAL_ASSIGNER incrementing question_retries
    node_inc = next((n for n in final_flow.nodes if n.id == "inc_retries"), None)
    assert node_inc is not None, "Expected node 'inc_retries' to exist"
    assert isinstance(node_inc, LogicalAssignerNode)
    assert len(node_inc.assignments) == 1
    asgn = node_inc.assignments[0]
    assert asgn.target_var_key == "question_retries"
    assert asgn.expression is not None

    # 3. Node 'check_retries' exists and is a LOGICAL_SWITCH with branches
    node_check = next((n for n in final_flow.nodes if n.id == "check_retries"), None)
    assert node_check is not None, "Expected node 'check_retries' to exist"
    assert isinstance(node_check, LogicalSwitchNode)
    branch_labels = {b.label for b in node_check.branches}
    assert "Retry" in branch_labels
    assert "GameOver" in branch_labels

    # 4. Check new edges exist:
    edges = [(e.source, e.target) for e in final_flow.edges]
    assert ("inc_retries", "check_retries") in edges
    assert ("check_retries", "ask_question") in edges
    assert ("check_retries", "end") in edges

    # Check that original result_switch -> end is gone, and replaced with result_switch -> inc_retries
    assert ("result_switch", "end") not in edges
    assert ("result_switch", "inc_retries") in edges


SCENARIOS: list[EvalScenario] = [
    EvalScenario(
        name="Add Logical Assigner Node",
        description="Verify the agent can add a logical assigner node and connect it correctly between start and end.",
        initial_flow=make_empty_flow(),
        user_prompt="Add a node named 'init_vars' of type LOGICAL_ASSIGNER that sets score to 0. Connect START to it, and connect it to END.",
        assert_fn=assert_scenario_1,
    ),
    EvalScenario(
        name="Rename State Variable",
        description="Verify that renaming a state variable propagates through assignment nodes and declarations.",
        initial_flow=make_scenario_2_initial_flow(),
        user_prompt="Rename the score variable to points.",
        assert_fn=assert_scenario_2,
    ),
    EvalScenario(
        name="Add Logical Switch Node",
        description="Verify the agent can create a logical switch node with branches and connect to it.",
        initial_flow=make_scenario_2_initial_flow(),
        user_prompt="Add a logical switch named 'check_score' with a branch 'High' when score is greater than 10, and connect init_vars to check_score.",
        assert_fn=assert_scenario_3,
    ),
    EvalScenario(
        name="Parallel Retries Loop-back (Hard Scenario)",
        description="Verify that the agent can perform complex rewiring to add retries loop-back to the game loop.",
        initial_flow=build_default_trivia_graph_flow_data(),
        user_prompt="""We want to add a retry limit feature.
1. Disconnect result_switch (branch 'wrong') from end, and connect it to a new LOGICAL_ASSIGNER node named 'inc_retries' that increments a new state variable 'question_retries' (default 0) by 1.
2. Connect inc_retries to a new LOGICAL_SWITCH node named 'check_retries'.
3. In check_retries, add a branch 'Retry' for when 'question_retries' is less than 3, and connect it to 'ask_question'.
4. Add a branch 'GameOver' for when 'question_retries' is greater than or equal to 3, and connect it to 'end'.
""",
        assert_fn=assert_scenario_4,
    ),
]
