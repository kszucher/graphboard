import pytest

from app.graphs import operations
from app.graphs.schemas import (
    DefinerOperationSchema,
    DefinerVariableSchema,
    GraphFlowData,
    LogicalAssignmentSchema,
    LogicalOperationSchema,
    NodeRead,
    OperationsContainerSchema,
)


def test_validate_and_coerce_default():
    # Number coercion
    assert operations.validate_and_coerce_default("number", 42) == 42
    assert operations.validate_and_coerce_default("number", "100") == 100
    with pytest.raises(ValueError):
        operations.validate_and_coerce_default("number", "not_a_number")

    # Float coercion
    assert operations.validate_and_coerce_default("float", 4.2) == 4.2
    assert operations.validate_and_coerce_default("float", "3.14") == 3.14
    with pytest.raises(ValueError):
        operations.validate_and_coerce_default("float", "not_a_float")

    # Boolean coercion
    assert operations.validate_and_coerce_default("boolean", True) is True
    assert operations.validate_and_coerce_default("boolean", "true") is True
    assert operations.validate_and_coerce_default("boolean", "1") is True
    assert operations.validate_and_coerce_default("boolean", "T") is True
    assert operations.validate_and_coerce_default("boolean", "yes") is True
    assert operations.validate_and_coerce_default("boolean", "false") is False
    assert operations.validate_and_coerce_default("boolean", "0") is False

    # String coercion
    assert operations.validate_and_coerce_default("string", "hello") == "hello"
    assert operations.validate_and_coerce_default("string", 123) == "123"

    # None and empty string fallback
    assert operations.validate_and_coerce_default("number", None) is None
    assert operations.validate_and_coerce_default("number", "") is None


def test_create_definer_variable_success():
    flow = GraphFlowData(
        nodes=[NodeRead(id="definer_1", node_type="DEFINER", ref_id="op_definer_1")],
        edges=[],
        operations=OperationsContainerSchema(definer=[DefinerOperationSchema(id="op_definer_1", variables=[])]),
    )

    updated = operations.create_definer_variable(
        flow, node_id="definer_1", key="user_age", var_type="number", default_value="25", description="User's age"
    )

    vars_list = operations.get_all_definer_variables(updated)
    assert len(vars_list) == 1
    var = vars_list[0]
    assert var.key == "user_age"
    assert var.type == "number"
    assert var.default_value == 25
    assert var.description == "User's age"


def test_create_definer_variable_naming_rules():
    flow = GraphFlowData(
        nodes=[NodeRead(id="definer_1", node_type="DEFINER", ref_id="op_definer_1")],
        edges=[],
        operations=OperationsContainerSchema(definer=[DefinerOperationSchema(id="op_definer_1", variables=[])]),
    )

    # Snake case violations
    with pytest.raises(ValueError, match="must be valid snake_case"):
        operations.create_definer_variable(flow, "definer_1", "UserAge")
    with pytest.raises(ValueError, match="must be valid snake_case"):
        operations.create_definer_variable(flow, "definer_1", "user-age")
    with pytest.raises(ValueError, match="must be valid snake_case"):
        operations.create_definer_variable(flow, "definer_1", "1_user_age")
    with pytest.raises(ValueError, match="must be valid snake_case"):
        operations.create_definer_variable(flow, "definer_1", "user age")

    # Python keyword violations
    with pytest.raises(ValueError, match="cannot be a Python keyword"):
        operations.create_definer_variable(flow, "definer_1", "def")
    with pytest.raises(ValueError, match="cannot be a Python keyword"):
        operations.create_definer_variable(flow, "definer_1", "class")

    # Duplicate variable keys
    operations.create_definer_variable(flow, "definer_1", "x")
    with pytest.raises(ValueError, match="already exists"):
        operations.create_definer_variable(flow, "definer_1", "x")


def test_update_definer_variable():
    flow = GraphFlowData(
        nodes=[NodeRead(id="definer_1", node_type="DEFINER", ref_id="op_definer_1")],
        edges=[],
        operations=OperationsContainerSchema(
            definer=[
                DefinerOperationSchema(
                    id="op_definer_1",
                    variables=[
                        DefinerVariableSchema(
                            id="var_x", key="x", type="number", default_value=1, description="old desc"
                        )
                    ],
                )
            ]
        ),
    )

    updated = operations.update_definer_variable(
        flow, var_id="var_x", updates={"type": "float", "default_value": "3.5", "description": "new desc"}
    )

    var = updated.operations.definer[0].variables[0]
    assert var.type == "float"
    assert var.default_value == 3.5
    assert var.description == "new desc"


def test_delete_definer_variable():
    flow = GraphFlowData(
        nodes=[],
        edges=[],
        operations=OperationsContainerSchema(
            definer=[
                DefinerOperationSchema(
                    id="op_definer_1",
                    variables=[DefinerVariableSchema(id="var_x", key="x", type="number", default_value=1)],
                )
            ]
        ),
    )

    updated = operations.delete_definer_variable(flow, "var_x")
    assert len(updated.operations.definer[0].variables) == 0


def test_create_logical_assignment_success():
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="definer_1", node_type="DEFINER", ref_id="op_def_1"),
            NodeRead(id="assigner_1", node_type="LOGICAL_ASSIGNER", ref_id="op_assign_1"),
        ],
        edges=[],
        operations=OperationsContainerSchema(
            definer=[
                DefinerOperationSchema(
                    id="op_def_1",
                    variables=[DefinerVariableSchema(id="var_x", key="x", type="number", default_value=0)],
                )
            ],
            logical=[LogicalOperationSchema(id="op_assign_1", assignments=[])],
        ),
    )

    # Assign value 42 to x
    updated = operations.create_logical_assignment(
        flow, node_id="assigner_1", target_var_key="x", value_type="number", value="42"
    )

    assignments = updated.operations.logical[0].assignments
    assert len(assignments) == 1
    assert assignments[0].target_var_key == "x"
    assert assignments[0].value == 42

    # Verify updating the same key updates in-place
    updated = operations.create_logical_assignment(
        updated, node_id="assigner_1", target_var_key="x", value_type="number", value="100"
    )
    assert len(assignments) == 1
    assert assignments[0].value == 100


def test_create_logical_assignment_invalid_variable():
    flow = GraphFlowData(
        nodes=[
            NodeRead(id="definer_1", node_type="DEFINER", ref_id="op_def_1"),
            NodeRead(id="assigner_1", node_type="LOGICAL_ASSIGNER", ref_id="op_assign_1"),
        ],
        edges=[],
        operations=OperationsContainerSchema(
            definer=[DefinerOperationSchema(id="op_def_1", variables=[])],
            logical=[LogicalOperationSchema(id="op_assign_1", assignments=[])],
        ),
    )

    # Attempt assignment to undefined variable 'y'
    with pytest.raises(ValueError, match="is not defined in state schema"):
        operations.create_logical_assignment(flow, "assigner_1", "y", "number", 42)


def test_update_logical_assignment():
    flow = GraphFlowData(
        nodes=[],
        edges=[],
        operations=OperationsContainerSchema(
            definer=[
                DefinerOperationSchema(
                    id="op_def_1",
                    variables=[
                        DefinerVariableSchema(id="var_x", key="x", type="number", default_value=0),
                        DefinerVariableSchema(id="var_y", key="y", type="string", default_value=""),
                    ],
                )
            ],
            logical=[
                LogicalOperationSchema(
                    id="op_assign_1",
                    assignments=[
                        LogicalAssignmentSchema(id="asgn_1", target_var_key="x", value_type="number", value=10)
                    ],
                )
            ],
        ),
    )

    # Update value and expression
    updated = operations.update_logical_assignment(
        flow, assignment_id="asgn_1", updates={"value": "20", "expression": {"kind": "literal", "value": 20}}
    )
    asgn = updated.operations.logical[0].assignments[0]
    assert asgn.value == 20
    assert asgn.expression == {"kind": "literal", "value": 20}

    # Update target variable key
    updated = operations.update_logical_assignment(
        flow, assignment_id="asgn_1", updates={"target_var_key": "y", "value_type": "string", "value": "hello"}
    )
    assert asgn.target_var_key == "y"
    assert asgn.value == "hello"

    # Fail update when new target key doesn't exist
    with pytest.raises(ValueError, match="is not defined in state schema"):
        operations.update_logical_assignment(flow, "asgn_1", {"target_var_key": "non_existent"})


def test_delete_logical_assignment():
    flow = GraphFlowData(
        nodes=[],
        edges=[],
        operations=OperationsContainerSchema(
            logical=[
                LogicalOperationSchema(
                    id="op_assign_1", assignments=[LogicalAssignmentSchema(id="asgn_1", target_var_key="x", value=10)]
                )
            ]
        ),
    )

    updated = operations.delete_logical_assignment(flow, "asgn_1")
    assert len(updated.operations.logical[0].assignments) == 0
