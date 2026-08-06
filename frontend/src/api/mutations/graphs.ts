import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, getClientId } from '../client';
import { queryKeys } from '../queryKeys';


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

export const useRunGraph = (graphId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (version: number | null = null) => {
      const res = await apiClient.POST('/graphs/{graph_id}/run', {
        params: {
          path: { graph_id: graphId },
          query: version !== null ? { version } : undefined,
        },
      });
      if ('error' in res) throw res.error;
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.flow(graphId) });
    }
  });
};
