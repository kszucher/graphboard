import type { components } from '../../api/generated/schema';
import type { ApiNode, ApiSlot, AppFlowEdge, AppFlowNode } from '../../canvas/types';

type ApiEdge = components['schemas']['EdgeRead'];
type RawNode = components['schemas']['GraphFlowRead']['nodes'][number];

export const fromApiPayload = (
  nodes: RawNode[],
  edges: ApiEdge[],
  prevNodes: AppFlowNode[] = [],
  prevEdges: AppFlowEdge[] = [],
  defaultTransition = 'transform 400ms cubic-bezier(0.4, 0, 0.2, 1)'
): { nodes: AppFlowNode[]; edges: AppFlowEdge[] } => {
  const slotToNodeId: Record<string, string> = {};
  nodes.forEach(n => {
    ('slots' in n && Array.isArray(n.slots) ? n.slots : []).forEach((s: components['schemas']['SlotRead']) => {
      slotToNodeId[s.id] = n.id;
    });
  });

  const getPrevNode = (nodeId: string) => {
    return prevNodes.find(n => n.id === nodeId);
  };

  const rfNodes: AppFlowNode[] = nodes.map(n => {
    const prevNode = getPrevNode(n.id);
    const is_input = n.node_type !== 'START';
    const is_output = n.node_type !== 'END' && !['LOGICAL_SWITCH', 'AGENTIC_SWITCH'].includes(n.node_type);
    // Cast the raw node to ApiNode — slots/expressions are cast here at the boundary
    const apiNode: ApiNode = {
      ...(n as ApiNode),
      slots: ('slots' in n && Array.isArray(n.slots) ? n.slots : []) as ApiSlot[],
      is_input,
      is_output,
    };
    return {
      id: n.id,
      type: 'custom' as const,
      position: prevNode?.position || { x: 0, y: 0 },
      measured: prevNode?.measured,
      selected: prevNode?.selected ?? false,
      style: {
        transition: defaultTransition,
      },
      data: { node: apiNode },
    };
  });

  const rfEdges: AppFlowEdge[] = edges
    .map(edge => {
      const sourceNodeId = edge.source;
      const targetNodeId = edge.target;

      if (!sourceNodeId || !targetNodeId) return null;

      const prevEdge = prevEdges.find(e => e.id === edge.id);

      return {
        id: edge.id ?? `${edge.source}-${edge.target}`,
        source: sourceNodeId,
        target: targetNodeId,
        sourceHandle: edge.source_handle || edge.source,
        targetHandle: edge.target_handle || edge.target,
        type: 'custom' as const,
        animated: true,
        data: {
          sections: prevEdge?.data?.sections || [],
        },
      };
    })
    .filter((e): e is NonNullable<typeof e> => e !== null);

  return { nodes: rfNodes, edges: rfEdges };
};
