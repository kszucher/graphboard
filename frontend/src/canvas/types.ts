import type { Edge, Node } from '@xyflow/react';
import type { ElkEdgeSection } from 'elkjs';
import type { components } from '../api/generated/schema';

export type ApiNode =
  Omit<components['schemas']['GraphFlowRead']['nodes'][number], 'variables' | 'assignments' | 'branches'>
  & {
  is_input: boolean;
  is_output: boolean;
  branches?: ApiSlot[] | null;
  variables?: DefinerVariable[] | null;
  assignments?: LogicalAssignment[] | null;
  prompt?: string | null;
  agentic_inputs?: string[] | null;
  agentic_input?: string | null;
  agentic_outputs?: string[] | null;
  payload_vars?: string[] | null;
  resume_var?: string | null;
  max_attempts?: number | null;
  valid_expression?: string | null;
  query_var?: string | null;
  context_output_var?: string | null;
  knowledge_base?: string | null;
  top_k?: number | null;
  traversalIndex?: number;
};

export type ApiSlot = {
  id: string;
  label: string;
  expression?: string | null;
  target_var_key?: string | null;
};

export type NodeType =
  | 'START'
  | 'END'
  | 'LOGICAL_SWITCH'
  | 'LOGICAL_ASSIGNER'
  | 'AGENTIC_ASSIGNER'
  | 'INTERRUPT'
  | 'AGENTIC_SWITCH'
  | 'RAG_RETRIEVER';

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
  expression?: string | null;
}

export type AppFlowNode = Node<{
  node: ApiNode;
}, 'custom'>;

export type AppFlowEdge = Edge<{
  sections?: ElkEdgeSection[];
}, 'custom'>;
