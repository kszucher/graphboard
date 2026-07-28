import { QueryClient, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, getClientId } from '../../api/client';
import { queryKeys } from '../../api/queryKeys';
import type { NodeType, ASTExpression } from '../../canvas/types';

const handleMutationSuccess = (
  queryClient: QueryClient,
  graphId: string,
  data: unknown
) => {
  if (data && typeof data === 'object') {
    queryClient.setQueryData(queryKeys.graphs.flow(graphId), data);
  }
  void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.flow(graphId) });
};

export const useAddNode = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (nodeType: NodeType) => {
      const res = await apiClient.POST('/graphs/{graph_id}/nodes', {
        params: { path: { graph_id: graphId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { node_type: nodeType }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useInsertNode = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      connectorId,
      nodeType,
      direction
    }: {
      connectorId: string;
      nodeType: NodeType;
      direction: 'before' | 'after';
    }) => {
      const res = await apiClient.POST('/graphs/{graph_id}/nodes', {
        params: { path: { graph_id: graphId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { node_type: nodeType, connector_id: connectorId, direction }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useInsertNodeOnEdge = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      sourceHandle,
      nodeType,
    }: {
      sourceHandle: string;
      nodeType: NodeType;
    }) => {
      const res = await apiClient.POST('/graphs/{graph_id}/nodes', {
        params: { path: { graph_id: graphId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { node_type: nodeType, connector_id: sourceHandle, direction: 'after' }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useDeleteNode = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (nodeId: string) => {
      const res = await apiClient.DELETE('/graphs/{graph_id}/nodes/{node_id}', {
        params: { path: { graph_id: graphId, node_id: nodeId } },
        headers: { 'X-Client-Id': getClientId() },
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useShortcircuitNode = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (nodeId: string) => {
      const res = await apiClient.POST('/graphs/{graph_id}/nodes/{node_id}/shortcircuit', {
        params: { path: { graph_id: graphId, node_id: nodeId } },
        headers: { 'X-Client-Id': getClientId() },
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useUpdateNode = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      nodeId,
      updates
    }: {
      nodeId: string;
      updates: { is_input?: boolean; is_output?: boolean; new_id?: string };
    }) => {
      const res = await apiClient.PATCH('/graphs/{graph_id}/nodes/{node_id}', {
        params: { path: { graph_id: graphId, node_id: nodeId } },
        headers: { 'X-Client-Id': getClientId() },
        body: updates
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useDeleteEdge = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (edgeId: string) => {
      const res = await apiClient.DELETE('/graphs/{graph_id}/edges/{edge_id}', {
        params: { path: { graph_id: graphId, edge_id: edgeId } },
        headers: { 'X-Client-Id': getClientId() },
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useCreateSlot = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ nodeId, index }: { nodeId: string; index: number }) => {
      const res = await apiClient.POST('/graphs/{graph_id}/nodes/{node_id}/slots', {
        params: { path: { graph_id: graphId, node_id: nodeId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { index }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useDeleteSlot = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (slotId: string) => {
      const res = await apiClient.DELETE('/graphs/{graph_id}/slots/{slot_id}', {
        params: { path: { graph_id: graphId, slot_id: slotId } },
        headers: { 'X-Client-Id': getClientId() },
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useUpdateSlot = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      slotId,
      rawString,
      expression,
    }: {
      slotId: string;
      rawString?: string;
      expression?: ASTExpression | null;
    }) => {
      const res = await apiClient.PATCH('/graphs/{graph_id}/slots/{slot_id}', {
        params: { path: { graph_id: graphId, slot_id: slotId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { raw_string: rawString, expression } as unknown as never
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useMoveSlot = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      slotId,
      direction
    }: {
      slotId: string;
      direction: 'up' | 'down' | 'top' | 'bottom';
    }) => {
      const res = await apiClient.POST('/graphs/{graph_id}/slots/{slot_id}/move', {
        params: { path: { graph_id: graphId, slot_id: slotId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { direction }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useUndo = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await apiClient.POST('/graphs/{graph_id}/history/undo', {
        params: { path: { graph_id: graphId } },
        headers: { 'X-Client-Id': getClientId() }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useRedo = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await apiClient.POST('/graphs/{graph_id}/history/redo', {
        params: { path: { graph_id: graphId } },
        headers: { 'X-Client-Id': getClientId() }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useCreateEdge = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      source: string;
      target: string;
      sourceHandle: string;
      targetHandle: string;
    }) => {
      const res = await apiClient.POST('/graphs/{graph_id}/edges', {
        params: { path: { graph_id: graphId } },
        headers: { 'X-Client-Id': getClientId() },
        body: {
          source: payload.source,
          target: payload.target,
          source_handle: payload.sourceHandle,
          target_handle: payload.targetHandle
        }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useReconnectEdge = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      edgeId: string;
      source: string;
      target: string;
      sourceHandle: string;
      targetHandle: string;
    }) => {
      const res = await apiClient.PATCH('/graphs/{graph_id}/edges/{edge_id}/reconnect', {
        params: { path: { graph_id: graphId, edge_id: payload.edgeId } },
        headers: { 'X-Client-Id': getClientId() },
        body: {
          source: payload.source,
          target: payload.target,
          source_handle: payload.sourceHandle,
          target_handle: payload.targetHandle
        }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useRunGraph = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await apiClient.POST('/graphs/{graph_id}/run', {
        params: { path: { graph_id: graphId } }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.flow(graphId) });
    }
  });
};

export const useCreateDefinerVariable = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      nodeId,
      key,
      type,
      defaultValue,
    }: {
      nodeId: string;
      key: string;
      type: 'boolean' | 'string' | 'number' | 'float';
      defaultValue?: unknown;
    }) => {
      const res = await apiClient.POST('/graphs/{graph_id}/nodes/{node_id}/definer/variables', {
        params: { path: { graph_id: graphId, node_id: nodeId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { key, type, default_value: defaultValue }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useUpdateDefinerVariable = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      varId,
      type,
      defaultValue,
    }: {
      varId: string;
      type?: 'boolean' | 'string' | 'number' | 'float';
      defaultValue?: unknown;
    }) => {
      const res = await apiClient.PATCH('/graphs/{graph_id}/definer/variables/{var_id}', {
        params: { path: { graph_id: graphId, var_id: varId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { type, default_value: defaultValue }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useDeleteDefinerVariable = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (varId: string) => {
      const res = await apiClient.DELETE('/graphs/{graph_id}/definer/variables/{var_id}', {
        params: { path: { graph_id: graphId, var_id: varId } },
        headers: { 'X-Client-Id': getClientId() }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useCreateLogicalAssignment = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      nodeId,
      targetVarKey,
      valueType = 'string',
      value,
      expression,
    }: {
      nodeId: string;
      targetVarKey: string;
      valueType?: 'boolean' | 'string' | 'number' | 'float';
      value?: unknown;
      expression?: ASTExpression | null;
    }) => {
      const res = await apiClient.POST('/graphs/{graph_id}/nodes/{node_id}/logical/assignments', {
        params: { path: { graph_id: graphId, node_id: nodeId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { target_var_key: targetVarKey, value_type: valueType, value, expression }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

export const useUpdateLogicalAssignment = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      assignmentId,
      targetVarKey,
      valueType,
      value,
      expression,
    }: {
      assignmentId: string;
      targetVarKey?: string;
      valueType?: 'boolean' | 'string' | 'number' | 'float';
      value?: unknown;
      expression?: ASTExpression | null;
    }) => {
      const res = await apiClient.PATCH('/graphs/{graph_id}/logical/assignments/{assignment_id}', {
        params: { path: { graph_id: graphId, assignment_id: assignmentId } },
        headers: { 'X-Client-Id': getClientId() },
        body: { target_var_key: targetVarKey, value_type: valueType, value, expression }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};


export const useDeleteLogicalAssignment = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (assignmentId: string) => {
      const res = await apiClient.DELETE('/graphs/{graph_id}/logical/assignments/{assignment_id}', {
        params: { path: { graph_id: graphId, assignment_id: assignmentId } },
        headers: { 'X-Client-Id': getClientId() }
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: (data) => {
      handleMutationSuccess(queryClient, graphId, data);
    }
  });
};

