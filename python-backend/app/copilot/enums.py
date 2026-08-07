from enum import Enum


class PlannerAction(str, Enum):
    DECLARE_VARIABLE = "declare_variable"
    DELETE_VARIABLE = "delete_variable"
    MODIFY_VARIABLE = "modify_variable"
    
    ADD_NODE = "add_node"
    DELETE_NODE = "delete_node"
    
    ADD_ROUTING_BRANCH = "add_routing_branch"
    DELETE_ROUTING_BRANCH = "delete_routing_branch"
    
    ADD_VARIABLE_ASSIGNMENT = "add_variable_assignment"
    DELETE_VARIABLE_ASSIGNMENT = "delete_variable_assignment"
    
    CONFIGURE_NODE = "configure_node"
    
    CONNECT_NODES = "connect_nodes"
    DISCONNECT_NODES = "disconnect_nodes"
