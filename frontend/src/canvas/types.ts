import type { Edge, Node } from '@xyflow/react';
import type { ElkEdgeSection } from 'elkjs';
import type { components } from '../api/generated/schema';

export type ApiNode = Omit<components['schemas']['NodeRead'], 'code'> & {
  code?: string | null;
  selected?: boolean;
  traversalIndex?: number;
};

export type ApiSlot = components['schemas']['SlotRead'] & {
  expression?: ASTExpression | null;
  target_var_key?: string | null;
};

export type NodeType = components['schemas']['NodeType'];
export type InsertableNodeType = Exclude<NodeType, 'START' | 'END'>;

export interface DefinerVariable {
  id: string;
  key: string;
  type: 'boolean' | 'string' | 'number' | 'float';
  default_value?: unknown;
  description?: string | null;
}

export interface DefinerOperation {
  id: string;
  variables: DefinerVariable[];
}

export interface LogicalAssignment {
  id: string;
  target_var_key: string;
  value_type: 'boolean' | 'string' | 'number' | 'float';
  value?: unknown;
  expression?: ASTExpression | null;
}

export interface LogicalOperation {
  id: string;
  assignments: LogicalAssignment[];
}

export interface OperationsContainer {
  definer: DefinerOperation[];
  agentic?: unknown[];
  logical?: LogicalOperation[];
  switch?: unknown[];
}

export type StateVariable = DefinerVariable;


export interface Diagnostic {
  line: number;
  column: number;
  code: string;
  message: string;
  severity: 'error' | 'warning';
  node_id?: string | null;
  slot_id?: string | null;
}

export type ASTExpression =
  | { kind: 'literal'; value: string | number | boolean | null }
  | { kind: 'stateRef'; varKey: string }
  | {
  kind: 'binaryOp';
  op: '==' | '!=' | '>' | '<' | '>=' | '<=' | '+' | '-' | '*' | '/' | 'and' | 'or';
  left: ASTExpression;
  right: ASTExpression;
}
  | { kind: 'unaryOp'; op: 'not' | '-'; expr: ASTExpression };

export type AppFlowNode = Node<{
  node: ApiNode;
}, 'custom'>;

export type AppFlowEdge = Edge<{
  sections?: ElkEdgeSection[];
}, 'custom'>;
