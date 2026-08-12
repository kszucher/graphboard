import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import { queryKeys } from '../queryKeys';

export const useInitiateCopilot = (graphId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ prompt }: { prompt: string }): Promise<{ applied: boolean; validation_error?: string | null }> => {
      const res = await apiClient.POST('/copilot/{graph_id}/initiate', {
        params: {
          path: { graph_id: graphId },
        },
        body: { prompt },
      });
      if ('error' in res) throw res.error;
      return res.data as { applied: boolean; validation_error?: string | null };
    },
    onSuccess: (data) => {
      if (data.applied) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.flow(graphId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.code(graphId) });
      }
    },
  });
};
