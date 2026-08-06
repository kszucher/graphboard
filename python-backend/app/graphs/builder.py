from __future__ import annotations

from typing import Any

from app.constants import NodeType
from app.graphs.expressions import parse_expression
from app.graphs.schemas import (
    ConnectOp,
    DeleteNodeOp,
    DeleteStateVarOp,
    DisconnectOp,
    GraphOperation,
    UpsertNodeOp,
    UpsertStateVarOp,
    VariableType,
)


class GraphBuilder:
    """A fluent API builder for constructing GraphOperation sequences."""

    def __init__(self) -> None:
        self.patch: list[GraphOperation] = []

    def state(
        self,
        key: str,
        type: VariableType,
        default_value: Any = None,
        id: str | None = None,
        description: str | None = None,
    ) -> GraphBuilder:
        """Adds an UpsertStateVarOp to declare or update a state variable."""
        self.patch.append(
            UpsertStateVarOp(
                op="upsert_state_var",
                id=id,
                key=key,
                type=type,
                default_value=default_value,
                description=description,
            )
        )
        return self

    def start_chain(self, node_id: str, node_type: NodeType, config: dict[str, Any] | None = None) -> ChainContext:
        """Creates the initial node of a chain and returns a ChainContext."""
        self.patch.append(
            UpsertNodeOp(
                op="upsert_node",
                node_id=node_id,
                node_type=node_type,
                config=config or {},
            )
        )
        return ChainContext(self, current_node_id=node_id)

    def delete_node(self, node_id: str) -> GraphBuilder:
        """Deletes a node and all of its connected edges."""
        self.patch.append(DeleteNodeOp(op="delete_node", node_id=node_id))
        return self

    def delete_state_var(self, key: str) -> GraphBuilder:
        """Deletes a state variable. Raises ValidationError if any node still references it."""
        self.patch.append(DeleteStateVarOp(op="delete_state_var", key=key))
        return self

    def disconnect(
        self,
        source: str,
        target: str,
        source_handle: str | None = None,
        target_handle: str | None = None,
    ) -> GraphBuilder:
        """Removes a specific edge between source and target."""
        self.patch.append(
            DisconnectOp(
                op="disconnect",
                source=source,
                source_handle=source_handle,
                target=target,
                target_handle=target_handle,
            )
        )
        return self


class ChainContext:
    """Represents the active node/slot 'cursor' during fluent chaining."""

    def __init__(
        self,
        builder: GraphBuilder,
        current_node_id: str,
        current_slot_id: str | None = None,
    ) -> None:
        self.builder = builder
        self.node_id = current_node_id
        self.slot_id = current_slot_id

    def then_node(
        self,
        node_id: str,
        node_type: NodeType,
        config: dict[str, Any] | None = None,
    ) -> ChainContext:
        """Creates a target node and automatically connects the current cursor (node or slot) to it."""
        self.builder.patch.append(
            UpsertNodeOp(
                op="upsert_node",
                node_id=node_id,
                node_type=node_type,
                config=config or {},
            )
        )

        source_node_id = self.node_id
        source_handle = self.slot_id

        self.builder.patch.append(
            ConnectOp(
                op="connect",
                source=source_node_id,
                source_handle=source_handle,
                target=node_id,
                target_handle=None,
            )
        )
        return ChainContext(self.builder, current_node_id=node_id)

    def then_to(self, target_node_id: str) -> ChainContext:
        """Connects the current cursor to an existing target node."""
        source_node_id = self.node_id
        source_handle = self.slot_id

        self.builder.patch.append(
            ConnectOp(
                op="connect",
                source=source_node_id,
                source_handle=source_handle,
                target=target_node_id,
                target_handle=None,
            )
        )
        return ChainContext(self.builder, current_node_id=target_node_id)

    def slot(self, slot_id: str) -> ChainContext:
        """Positions the cursor on a specific slot ID of the current node."""
        return ChainContext(self.builder, current_node_id=self.node_id, current_slot_id=slot_id)

    def logical_assigner(self, node_id: str, assignments: list[dict[str, Any]]) -> ChainContext:
        """Shortcut to create a LOGICAL_ASSIGNER node."""
        parsed_assignments = []
        for a in assignments:
            parsed_a = a.copy()
            if "expression" in parsed_a:
                parsed_a["expression"] = parse_expression(parsed_a["expression"])
            parsed_assignments.append(parsed_a)
        return self.then_node(
            node_id,
            NodeType.LOGICAL_ASSIGNER,
            {"assignments": parsed_assignments},
        )

    def logical_switch(self, node_id: str, slots: list[dict[str, Any]]) -> ChainContext:
        """Shortcut to create a LOGICAL_SWITCH node."""
        parsed_slots = []
        for s in slots:
            parsed_s = s.copy()
            if "expression" in parsed_s:
                parsed_s["expression"] = parse_expression(parsed_s["expression"])
            parsed_slots.append(parsed_s)
        return self.then_node(
            node_id,
            NodeType.LOGICAL_SWITCH,
            {"slots": parsed_slots},
        )

    def agentic_assigner(
        self,
        node_id: str,
        prompt: str,
        outputs: list[str],
        inputs: list[str] | None = None,
    ) -> ChainContext:
        """Shortcut to create an AGENTIC_ASSIGNER node."""
        return self.then_node(
            node_id,
            NodeType.AGENTIC_ASSIGNER,
            {
                "prompt": prompt,
                "agentic_inputs": inputs or [],
                "agentic_outputs": outputs,
            },
        )

    def agentic_switch(
        self,
        node_id: str,
        agentic_input: str,
        slots: list[dict[str, Any]],
    ) -> ChainContext:
        """Shortcut to create an AGENTIC_SWITCH node."""
        return self.then_node(
            node_id,
            NodeType.AGENTIC_SWITCH,
            {
                "agentic_input": agentic_input,
                "slots": slots,
            },
        )

    def interrupt(
        self,
        node_id: str,
        payload_vars: list[str],
        resume_var: str,
    ) -> ChainContext:
        """Shortcut to create an INTERRUPT node."""
        return self.then_node(
            node_id,
            NodeType.INTERRUPT,
            {
                "payload_vars": payload_vars,
                "resume_var": resume_var,
            },
        )
