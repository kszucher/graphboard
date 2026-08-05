import { QueryClient, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, getClientId } from '../client';
import { queryKeys } from '../queryKeys';

const handleMutationSuccess = (
  queryClient: QueryClient,
  graphId: string,
  data: unknown
) => {
  if (data && typeof data === 'object') {
    queryClient.setQueryData(queryKeys.graphs.flow(graphId), data);
  }
  void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.flow(graphId) });
  void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.code(graphId) });
};

export const useCreateGraph = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ userId, graphName }: { userId: string; graphName: string }) => {
      const res = await apiClient.POST('/graphs/', {
        headers: { 'X-Client-Id': getClientId() },
        body: { user_id: userId, graph_name: graphName },
      });
      if ('error' in res) throw res.error;
      return res.data as string;
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.byUser(variables.userId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.activeGraph(variables.userId) });
    },
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
