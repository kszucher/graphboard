import pytest

from app.constants import NodeType
from app.exceptions import ValidationError
from app.graphs import operations
from app.graphs.schemas import (
    DefinerVariableSchema,
    GraphFlowData,
    LogicalAssignmentSchema,
    NodeRead,
)


def test_validate_default_value_type() -> None:
    # Number validation
    assert operations.validate_default_value_type("number", 42) == 42
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("number", "100")
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("number", 42.5)
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("number", "not_a_number")

    # Float validation
    assert operations.validate_default_value_type("float", 4.2) == 4.2
    assert operations.validate_default_value_type("float", 42) == 42.0
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("float", "3.14")
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("float", "not_a_float")

    # Boolean validation
    assert operations.validate_default_value_type("boolean", True) is True
    assert operations.validate_default_value_type("boolean", False) is False
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("boolean", "true")
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("boolean", "1")
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("boolean", "T")
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("boolean", "yes")

    # String validation
    assert operations.validate_default_value_type("string", "hello") == "hello"
    with pytest.raises(ValidationError):
        operations.validate_default_value_type("string", 123)

    # None and empty string fallback
    assert operations.validate_default_value_type("number", None) is None
    assert operations.validate_default_value_type("number", "") is None


def test_create_definer_variable_success() -> None:
    flow = GraphFlowData(
        nodes=[],
        edges=[],
        state=[],
    )

    updated = operations.create_definer_variable(
        flow, key="user_age", var_type="number", default_value=25, description="User's age"
    )

    vars_list = operations.get_all_definer_variables(updated)
    assert len(vars_list) == 1
    var = vars_list[0]
    assert var.key == "user_age"
    assert var.type == "number"
    assert var.default_value == 25
    assert var.description == "User's age"


def test_create_definer_variable_naming_rules() -> None:
    flow = GraphFlowData(
        nodes=[],
        edges=[],
        state=[],
    )

    # Snake case violations
    with pytest.raises(ValidationError, match="must be valid snake_case"):
        operations.create_definer_variable(flow, "UserAge")
    with pytest.raises(ValidationError, match="must be valid snake_case"):
        operations.create_definer_variable(flow, "user-age")
    with pytest.raises(ValidationError, match="must be valid snake_case"):
        operations.create_definer_variable(flow, "1_user_age")
    with pytest.raises(ValidationError, match="must be valid snake_case"):
        operations.create_definer_variable(flow, "user age")

    # Python keyword violations
    with pytest.raises(ValidationError, match="cannot be a Python keyword"):
        operations.create_definer_variable(flow, "def")
    with pytest.raises(ValidationError, match="cannot be a Python keyword"):
        operations.create_definer_variable(flow, "class")

    # Duplicate variable keys
    operations.create_definer_variable(flow, "x")
    with pytest.raises(ValidationError, match="already exists"):
        operations.create_definer_variable(flow, "x")


def test_update_definer_variable() -> None:
    flow = GraphFlowData(
        nodes=[],
        edges=[],
        state=[DefinerVariableSchema(id="var_x", key="x", type="number", default_value=1, description="old desc")],
    )

    updated = operations.update_definer_variable(
        flow, var_id="var_x", updates={"type": "float", "default_value": 3.5, "description": "new desc"}
    )

    variables = updated.state
    assert variables is not None
    var = variables[0]
    assert var.type == "float"
    assert var.default_value == 3.5
    assert var.description == "new desc"


def test_delete_definer_variable() -> None:
    flow = GraphFlowData(
        nodes=[],
        edges=[],
        state=[DefinerVariableSchema(id="var_x", key="x", type="number", default_value=1)],
    )

    updated = operations.delete_definer_variable(flow, "var_x")
    variables = updated.state
    assert variables is not None
    assert len(variables) == 0


def test_create_logical_assignment_success() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="assigner_1", node_type=NodeType.LOGICAL_ASSIGNER, assignments=[]),
        ],
        edges=[],
        state=[DefinerVariableSchema(id="var_x", key="x", type="number", default_value=0)],
    )

    # Assign value 42 to x
    updated = operations.create_logical_assignment(
        flow, node_id="assigner_1", target_var_key="x", value_type="number", value=42
    )

    assignments = updated.nodes[0].assignments
    assert assignments is not None
    assert len(assignments) == 1
    assert assignments[0].target_var_key == "x"
    assert assignments[0].value == 42

    # Verify updating the same key updates in-place
    updated = operations.create_logical_assignment(
        updated, node_id="assigner_1", target_var_key="x", value_type="number", value=100
    )
    assignments = updated.nodes[0].assignments
    assert assignments is not None
    assert len(assignments) == 1
    assert assignments[0].value == 100


def test_create_logical_assignment_invalid_variable() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="assigner_1", node_type=NodeType.LOGICAL_ASSIGNER, assignments=[]),
        ],
        edges=[],
        state=[],
    )

    # Attempt assignment to undefined variable 'y'
    with pytest.raises(ValidationError, match="is not defined in state schema"):
        operations.create_logical_assignment(flow, "assigner_1", "y", "number", 42)


def test_update_logical_assignment() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(
                id="assigner_1",
                node_type=NodeType.LOGICAL_ASSIGNER,
                assignments=[LogicalAssignmentSchema(id="asgn_1", target_var_key="x", value_type="number", value=10)],
            ),
        ],
        edges=[],
        state=[
            DefinerVariableSchema(id="var_x", key="x", type="number", default_value=0),
            DefinerVariableSchema(id="var_y", key="y", type="string", default_value=""),
        ],
    )

    # Update value and expression
    updated = operations.update_logical_assignment(
        flow, assignment_id="asgn_1", updates={"value": 20, "expression": {"kind": "literal", "value": 20}}
    )
    assignments = updated.nodes[0].assignments
    assert assignments is not None
    asgn = assignments[0]
    assert asgn.value == 20
    assert asgn.expression == {"kind": "literal", "value": 20}

    # Update target variable key
    updated = operations.update_logical_assignment(
        flow, assignment_id="asgn_1", updates={"target_var_key": "y", "value_type": "string", "value": "hello"}
    )
    assert asgn.target_var_key == "y"
    assert asgn.value == "hello"

    # Fail update when new target key doesn't exist
    with pytest.raises(ValidationError, match="is not defined in state schema"):
        operations.update_logical_assignment(flow, "asgn_1", {"target_var_key": "non_existent"})


def test_delete_logical_assignment() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(
                id="assigner_1",
                node_type=NodeType.LOGICAL_ASSIGNER,
                assignments=[LogicalAssignmentSchema(id="asgn_1", target_var_key="x", value=10)],
            )
        ],
        edges=[],
        state=[],
    )

    updated = operations.delete_logical_assignment(flow, "asgn_1")
    assignments = updated.nodes[0].assignments
    assert assignments is not None
    assert len(assignments) == 0


def test_agentic_assigner_cascade_rename_and_blocked_delete() -> None:
    flow = GraphFlowData(
        nodes=[
            NodeRead(
                id="agentic_1",
                node_type=NodeType.AGENTIC_ASSIGNER,
                prompt="Prompt with {x}",
                agentic_inputs=["x"],
                agentic_outputs=["x"],
            ),
        ],
        edges=[],
        state=[
            DefinerVariableSchema(id="var_x", key="x", type="number", default_value=0),
        ],
    )

    # 1. Test Rename cascades to prompt, inputs, and outputs
    updated = operations.update_definer_variable(flow, var_id="var_x", updates={"key": "new_x"})
    agentic_node = updated.nodes[0]
    assert agentic_node.prompt == "Prompt with {new_x}"
    assert agentic_node.agentic_inputs == ["new_x"]
    assert agentic_node.agentic_outputs == ["new_x"]

    # 2. Test Blocked Delete when referenced
    with pytest.raises(ValidationError, match="referenced as an input"):
        operations.delete_definer_variable(updated, var_id="var_x")

    # Clear inputs and test output block
    agentic_node.agentic_inputs = []
    with pytest.raises(ValidationError, match="referenced as an output"):
        operations.delete_definer_variable(updated, var_id="var_x")
