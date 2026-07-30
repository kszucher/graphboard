import { queryOptions, useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';
import { queryKeys } from '../queryKeys';

export const graphQueries = {
  byUser: (userId: string | null) => queryOptions({
    queryKey: queryKeys.graphs.byUser(userId),
    queryFn: async () => {
      const res = await apiClient.GET('/graphs/user/{user_id}', {
        params: { path: { user_id: userId ?? '' } },
      });
      if ('error' in res) throw res.error;
      return res.data ?? [];
    },
    enabled: Boolean(userId),
  }),
  flow: (graphId: string | null) => queryOptions({
    queryKey: queryKeys.graphs.flow(graphId),
    queryFn: async () => {
      const res = await apiClient.GET('/graphs/{graph_id}/flow', {
        params: { path: { graph_id: graphId ?? '' } },
      });
      if ('error' in res) throw res.error;
      return res.data ?? null;
    },
    enabled: Boolean(graphId),
  }),
  code: (graphId: string | null) => queryOptions({
    queryKey: queryKeys.graphs.code(graphId),
    queryFn: async () => {
      const res = await apiClient.GET('/graphs/{graph_id}/code', {
        params: { path: { graph_id: graphId ?? '' } },
      });
      if ('error' in res) throw res.error;
      return res.data ?? null;
    },
    enabled: Boolean(graphId),
  }),
};

export const useUserGraphs = (userId: string | null) => {
  return useQuery(graphQueries.byUser(userId));
};

export const useGraphCode = (graphId: string | null) => {
  return useQuery(graphQueries.code(graphId));
};
