import type { Edge, Node } from '@xyflow/react';
import type { ElkEdgeSection } from 'elkjs';
import type { components } from '../api/generated/schema';

export type ApiNode =
  Omit<components['schemas']['GraphFlowRead']['nodes'][number], 'variables' | 'assignments' | 'slots'>
  & {
  is_input: boolean;
  is_output: boolean;
  slots?: ApiSlot[] | null;
  variables?: DefinerVariable[] | null;
  assignments?: LogicalAssignment[] | null;
  prompt?: string | null;
  agentic_inputs?: string[] | null;
  agentic_input?: string | null;
  agentic_outputs?: string[] | null;
  payload_vars?: string[] | null;
  resume_var?: string | null;
  max_attempts?: number | null;
  valid_expression?: ASTExpression | null;
  traversalIndex?: number;
};

export type ApiSlot = Omit<components['schemas']['SlotRead'], 'expression'> & {
  expression?: ASTExpression | null;
  target_var_key?: string | null;
};

export type NodeType =
  | 'START'
  | 'END'
  | 'LOGICAL_SWITCH'
  | 'LOGICAL_ASSIGNER'
  | 'AGENTIC_ASSIGNER'
  | 'INTERRUPT'
  | 'AGENTIC_SWITCH';

export interface DefinerVariable {
  id: string;
  key: string;
  type: 'boolean' | 'string' | 'number' | 'float';
  default_value?: unknown;
  description?: string | null;
}

export interface LogicalAssignment {
  id: string;
  target_var_key: string;
  expression?: ASTExpression | null;
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
