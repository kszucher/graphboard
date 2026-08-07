from app.constants import NodeType
from app.copilot.enums import PlannerAction
from app.graphs.schemas import GraphFlowData


def serialize_flow_to_code(flow: GraphFlowData) -> str:
    """Serializes GraphFlowData into a human-readable mock Python representation for LLMs."""
    lines = []

    # 1. State Variables
    for var in flow.state:
        desc_str = f", description={repr(var.description)}" if var.description else ""
        default_str = f", default_value={repr(var.default_value)}" if var.default_value is not None else ""
        lines.append(
            f"{PlannerAction.DECLARE_VARIABLE.value}(key={repr(var.key)}, type={repr(var.type)}{default_str}{desc_str})"
        )

    if flow.state:
        lines.append("")

    # 2. Nodes and their settings/configurations
    for node in flow.nodes:
        # Declare the node
        lines.append(f"{PlannerAction.ADD_NODE.value}(node_id={repr(node.id)}, type={repr(node.node_type.value)})")

        # Configure/decorate based on type
        if node.node_type == NodeType.LOGICAL_ASSIGNER:
            for a in getattr(node, "assignments", []):
                lines.append(
                    f"{PlannerAction.ADD_VARIABLE_ASSIGNMENT.value}(node_id={repr(node.id)}, "
                    f"target_var_key={repr(a.target_var_key)}, expression={repr(a.expression or '')})"
                )
        elif node.node_type == NodeType.AGENTIC_ASSIGNER:
            lines.append(
                f"{PlannerAction.CONFIGURE_NODE.value}(node_id={repr(node.id)}, prompt={repr(node.prompt)}, "
                f"inputs={node.agentic_inputs}, outputs={node.agentic_outputs})"
            )
        elif node.node_type == NodeType.LOGICAL_SWITCH:
            for s in getattr(node, "slots", []):
                lines.append(
                    f"{PlannerAction.ADD_ROUTING_BRANCH.value}(node_id={repr(node.id)}, "
                    f"case={repr(s.raw_string)}, expression={repr(s.expression or '')})"
                )
        elif node.node_type == NodeType.AGENTIC_SWITCH:
            lines.append(
                f"{PlannerAction.CONFIGURE_NODE.value}(node_id={repr(node.id)}, agentic_input={repr(node.agentic_input)})"
            )
            for s in getattr(node, "slots", []):
                lines.append(
                    f"{PlannerAction.ADD_ROUTING_BRANCH.value}(node_id={repr(node.id)}, case={repr(s.raw_string)})"
                )
        elif node.node_type == NodeType.INTERRUPT:
            lines.append(
                f"{PlannerAction.CONFIGURE_NODE.value}(node_id={repr(node.id)}, payload_vars={node.payload_vars}, "
                f"resume_var={repr(node.resume_var)})"
            )

    if flow.nodes:
        lines.append("")

    # 3. Connections
    for edge in flow.edges:
        source_node = next((n for n in flow.nodes if n.id == edge.source), None)
        case_val = None
        if source_node and hasattr(source_node, "slots") and edge.source_handle:
            slot = next((s for s in getattr(source_node, "slots", []) if s.id == edge.source_handle), None)
            if slot:
                case_val = slot.raw_string

        case_str = f", case={repr(case_val)}" if case_val else ""
        lines.append(
            f"{PlannerAction.CONNECT_NODES.value}(source={repr(edge.source)}, target={repr(edge.target)}{case_str})"
        )

    return "\n".join(lines)
