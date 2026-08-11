import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import { queryKeys } from '../queryKeys';
import type { components } from '../generated/schema';

export type CopilotStatusResponse = components['schemas']['CopilotStatusResponse'];

export const useInitiateCopilot = (graphId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ prompt }: { prompt: string }): Promise<CopilotStatusResponse> => {
      const res = await apiClient.POST('/copilot/{graph_id}/initiate', {
        params: {
          path: { graph_id: graphId },
        },
        body: { prompt },
      });
      if ('error' in res) throw res.error;
      return res.data as CopilotStatusResponse;
    },
    onSuccess: (data) => {
      if (data.applied) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.flow(graphId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.graphs.code(graphId) });
      }
    },
  });
};
