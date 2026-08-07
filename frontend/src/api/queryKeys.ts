/**
 * Centralized query key factory for type-safe query keys.
 * This ensures consistency and makes refactoring easier.
 */
export const queryKeys = {
  // User queries
  users: {
    all: ['users'] as const,
    current: () => [...queryKeys.users.all, 'current'] as const,
    activeGraph: (userId: string | null) => [...queryKeys.users.all, userId, 'active-graph'] as const,
  },

  // Graph queries
  graphs: {
    all: ['graphs'] as const,
    byUser: (userId: string | null) => [...queryKeys.graphs.all, userId] as const,
    flow: (graphId: string | null, version?: number | null) =>
      version !== undefined
        ? ([...queryKeys.graphs.all, graphId, 'flow', version] as const)
        : ([...queryKeys.graphs.all, graphId, 'flow'] as const),
    code: (graphId: string | null, version?: number | null) =>
      version !== undefined
        ? ([...queryKeys.graphs.all, graphId, 'code', version] as const)
        : ([...queryKeys.graphs.all, graphId, 'code'] as const),
  },

  // Node queries
  nodes: {
    all: ['nodes'] as const,
    byGraph: (graphId: string) => [...queryKeys.nodes.all, graphId] as const,
  },

  // Edge queries
  edges: {
    all: ['edges'] as const,
    byGraph: (graphId: string) => [...queryKeys.edges.all, graphId] as const,
  },

  // Slot queries
  slots: {
    all: ['slots'] as const,
    byGraph: (graphId: string) => [...queryKeys.slots.all, graphId] as const,
  },
} as const;
