from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# --- Strict Assigner Expression Models ---


class SetLiteral(BaseModel):
    value: str | int | float | bool | list[Any] | dict[str, Any] | None = Field(
        description="Direct literal value to assign."
    )


class SetVar(BaseModel):
    var: str = Field(description="Source state variable key to copy value from.")


class NumericDelta(BaseModel):
    op: Literal["increment", "decrement", "multiply", "divide"] = Field(
        description="Arithmetic operation on target variable."
    )
    amount: float = Field(description="Amount to adjust.")


class MathOp(BaseModel):
    op: Literal["add", "subtract", "multiply", "divide", "modulo"] = Field(description="Arithmetic operator.")
    left: Any = Field(description="Left operand: scalar literal, {'var': 'name'}, or nested sub-expression.")
    right: Any = Field(description="Right operand: scalar literal, {'var': 'name'}, or nested sub-expression.")


class MathFunc(BaseModel):
    op: Literal["round", "min", "max"] = Field(description="Math function name.")
    val: Any | None = Field(default=None, description="Value for round.")
    ndigits: int | None = Field(default=None, description="Number of decimal digits for round.")
    args: list[Any] | None = Field(default=None, description="Arguments for min/max.")


class RandomNumber(BaseModel):
    op: Literal["random_int", "random_float"] = Field(description="Random number generator.")
    min: float = Field(default=0, description="Minimum value.")
    max: float = Field(default=100, description="Maximum value.")


class StringFormat(BaseModel):
    op: Literal["format"] = "format"
    template: str = Field(description="Template string containing {var_name} placeholders.")
    vars: list[str] | None = Field(
        default=None, description="Optional list of state variable keys to populate placeholders."
    )


class _CollectionBase(BaseModel):
    items: Any = Field(default=None, description="Source list literal or {'var': 'list_var_name'}.")

    @model_validator(mode="before")
    @classmethod
    def alias_list(cls, data: Any) -> Any:
        if isinstance(data, dict) and "list" in data and "items" not in data:
            data["items"] = data["list"]
        return data


class StringJoin(_CollectionBase):
    op: Literal["join"] = "join"
    sep: str = Field(default="\n", description="Separator string.")


class StringSplit(BaseModel):
    op: Literal["split"] = "split"
    text: Any = Field(default=None, description="String literal or {'var': 'str_var_name'} to split.")
    sep: str = Field(default=" ", description="Separator string.")

    @model_validator(mode="before")
    @classmethod
    def alias_str(cls, data: Any) -> Any:
        if isinstance(data, dict) and "str" in data and "text" not in data:
            data["text"] = data["str"]
        return data


class CollectionSample(_CollectionBase):
    op: Literal["sample"] = "sample"
    count: int = Field(default=1, description="Number of random elements to sample.")


class CollectionChoice(_CollectionBase):
    op: Literal["choice"] = "choice"


class CollectionRemove(_CollectionBase):
    op: Literal["remove"] = "remove"
    item: Any = Field(description="Item or list of items ({'var': '...'} or literal) to remove from list.")


class CollectionAppend(_CollectionBase):
    op: Literal["append"] = "append"
    item: Any = Field(description="Item to append.")


class CollectionLength(_CollectionBase):
    op: Literal["length"] = "length"


class CollectionSlice(_CollectionBase):
    op: Literal["slice"] = "slice"
    start: int | None = Field(default=None, description="Start index.")
    end: int | None = Field(default=None, description="End index.")


AssignmentExpr = (
    SetVar
    | SetLiteral
    | NumericDelta
    | MathOp
    | MathFunc
    | RandomNumber
    | StringFormat
    | StringJoin
    | StringSplit
    | CollectionSample
    | CollectionChoice
    | CollectionRemove
    | CollectionAppend
    | CollectionLength
    | CollectionSlice
)


class StrictAssignment(BaseModel):
    target_var_key: str = Field(description="Target variable key to write into.")
    assignment: AssignmentExpr = Field(
        description="Assignment logic: literal, variable reference, math, string format/join, or collection transformation."
    )


# --- Strict Closed-Schema Condition Models ---


class ComparisonCondition(BaseModel):
    var: str = Field(description="Left-hand state variable key to evaluate.")
    op: Literal["equals", "not_equals", "gt", "gte", "lt", "lte", "in"] = Field(description="Comparison operator.")
    literal_value: str | int | float | bool | list[str] | None = Field(
        default=None, description="Literal value to match against (use for static comparisons)."
    )
    compare_var: str | None = Field(
        default=None, description="Right-hand state variable key to compare against (for var-to-var comparisons)."
    )


class ConditionGroup(BaseModel):
    logic: Literal["ALL", "ANY"] = Field(default="ALL", description="Evaluate ALL (AND) or ANY (OR) of the conditions.")
    conditions: list[ComparisonCondition] = Field(
        default_factory=list, description="List of atomic comparison conditions."
    )


class LogicalSwitchBranch(BaseModel):
    label: str = Field(description="Branch identifier label (e.g. 'Yes', 'High_Score', 'default').")
    condition: ConditionGroup | None = Field(
        default=None, description="Condition group to match. Set to null for default/fallback branch."
    )
    target: str = Field(description="Downstream target node ID (or 'end').")


class AgenticSwitchBranch(BaseModel):
    label: str = Field(description="Classification case label (e.g. 'Audience', 'Phone', 'FiftyFifty').")
    target: str = Field(description="Downstream target node ID (or 'end').")


# --- Variable & Agentic Output Models ---


class AgenticOutputVar(BaseModel):
    key: str = Field(description="Output variable name.")
    type: Literal["string", "number", "boolean", "array", "object"] = Field(description="Variable type.")


class UpsertVariable(BaseModel):
    key: str = Field(description="Variable key to create or update.")
    type: Literal["string", "number", "boolean", "array", "object"] = Field(description="Variable type.")
    default_value: Any | None = Field(
        default=None,
        description="Optional default value. Must be explicitly set to null/none if not present.",
    )
    description: str | None = Field(
        default=None,
        description="Optional variable description. Must be explicitly set to null/none if not present.",
    )


# --- Polymorphic Node Configurations ---


class LogicalAssignerConfig(BaseModel):
    assignments: list[StrictAssignment] = Field(min_length=1, description="List of variable assignments to execute.")


class AgenticAssignerConfig(BaseModel):
    prompt: str = Field(description="Prompt template instruction with optional {var} placeholders.")
    agentic_inputs: list[str] = Field(
        default_factory=list, description="Variables passed to the agent context. Pass [] if empty."
    )
    agentic_outputs: list[AgenticOutputVar] = Field(
        default_factory=list, description="Output variables generated by the agent. Pass [] if empty."
    )


class RagRetrieverConfig(BaseModel):
    query_var: str = Field(description="Variable containing the search query string.")
    context_output_var: str = Field(description="Variable to output the retrieved context string.")
    knowledge_base: str = Field(description="Target knowledge base identifier.")
    top_k: int = Field(default=3, description="Number of context records to retrieve.")


class InterruptConfig(BaseModel):
    resume_var: str = Field(description="Variable to write resume value to.")
    payload_vars: list[str] = Field(
        default_factory=list, description="Variables to send in the interrupt payload. Pass [] if empty."
    )


class LogicalSwitchConfig(BaseModel):
    branches: list[LogicalSwitchBranch] = Field(
        default_factory=list, description="List of conditional branches with their condition rules and targets."
    )


class AgenticSwitchConfig(BaseModel):
    agentic_input: str = Field(description="Input variable key to classify/route upon.")
    branches: list[AgenticSwitchBranch] = Field(
        default_factory=list, description="List of classification cases and their targets."
    )


# --- Core Gold Standard Tools ---


class UpsertNode(BaseModel):
    id: str = Field(description="Unique node ID, or 'start' to set graph entrypoint.")
    node_type: (
        Literal[
            "LOGICAL_ASSIGNER",
            "AGENTIC_ASSIGNER",
            "RAG_RETRIEVER",
            "INTERRUPT",
            "LOGICAL_SWITCH",
            "AGENTIC_SWITCH",
        ]
        | None
    ) = Field(
        default=None,
        description="Type of the node. Required when creating new nodes; optional when retargeting existing nodes.",
    )
    config: (
        LogicalAssignerConfig
        | AgenticAssignerConfig
        | RagRetrieverConfig
        | InterruptConfig
        | LogicalSwitchConfig
        | AgenticSwitchConfig
        | None
    ) = Field(
        default=None,
        description="Node type-specific configuration object. Optional when updating existing node target only.",
    )
    target: str | None = Field(
        default=None,
        description="Downstream target node ID (or 'end') for linear nodes and 'start'. Leave null for switch nodes.",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_config_by_node_type(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ntype = data.get("node_type")
            config = data.get("config")
            type_map: dict[str, type[BaseModel]] = {
                "LOGICAL_ASSIGNER": LogicalAssignerConfig,
                "AGENTIC_ASSIGNER": AgenticAssignerConfig,
                "RAG_RETRIEVER": RagRetrieverConfig,
                "INTERRUPT": InterruptConfig,
                "LOGICAL_SWITCH": LogicalSwitchConfig,
                "AGENTIC_SWITCH": AgenticSwitchConfig,
            }
            if ntype in type_map and isinstance(config, dict):
                # Validate explicitly against the exact config class for pinpoint error attribution
                validated_config = type_map[ntype].model_validate(config)
                data["config"] = validated_config
        return data


class UpsertSwitchBranch(BaseModel):
    node_id: str = Field(description="ID of the switch node to add or update the branch on.")
    label: str = Field(description="Branch label/case name.")
    target: str = Field(description="Downstream target node ID (or 'end').")
    condition: ConditionGroup | None = Field(
        default=None,
        description="Condition group for LOGICAL_SWITCH. Leave null for default branch or AGENTIC_SWITCH.",
    )


class DeleteEntity(BaseModel):
    kind: Literal["node", "variable", "switch_branch"] = Field(description="Kind of entity to delete.")
    id: str = Field(description="Node ID, variable key, or branch label to delete.")
    parent_id: str | None = Field(
        default=None,
        description="Parent switch node ID when kind='switch_branch'. Leave null for node/variable.",
    )


class RenameEntity(BaseModel):
    kind: Literal["node", "variable"] = Field(description="Kind of entity to rename.")
    old_name: str = Field(description="Current name/ID.")
    new_name: str = Field(description="New name/ID.")
