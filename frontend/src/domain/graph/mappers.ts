import type { components } from '../../api/generated/schema';
import type { ApiNode, ApiSlot, AppFlowEdge, AppFlowNode } from '../../canvas/types';

type ApiEdge = components['schemas']['EdgeRead'];
type RawNode = components['schemas']['NodeRead'];

export const fromApiPayload = (
  nodes: RawNode[],
  edges: ApiEdge[],
  prevNodes: AppFlowNode[] = [],
  prevEdges: AppFlowEdge[] = [],
  defaultTransition = 'transform 400ms cubic-bezier(0.4, 0, 0.2, 1)'
): { nodes: AppFlowNode[]; edges: AppFlowEdge[] } => {
  const slotToNodeId: Record<string, string> = {};
  nodes.forEach(n => {
    (n.slots || []).forEach(s => {
      slotToNodeId[s.id] = n.id;
    });
  });

  // Stitch renames: match added/removed nodes to map positions/dimensions
  const newNodeIds = nodes.map(n => n.id);
  const oldNodeIds = prevNodes.map(n => n.id);
  const addedId = newNodeIds.find(id => !oldNodeIds.includes(id));
  const removedId = oldNodeIds.find(id => !newNodeIds.includes(id));

  const getPrevNode = (nodeId: string) => {
    const lookupId = nodeId === addedId ? removedId : nodeId;
    return prevNodes.find(n => n.id === lookupId);
  };

  const rfNodes: AppFlowNode[] = nodes.map(n => {
    const prevNode = getPrevNode(n.id);
    const is_input = n.node_type !== 'START';
    const is_output = n.node_type !== 'END' && n.node_type !== 'SWITCH';
    // Cast the raw node to ApiNode — slots/expressions are cast here at the boundary
    const apiNode: ApiNode = {
      ...(n as ApiNode),
      slots: (n.slots || []) as ApiSlot[],
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
      const sourceNodeId = edge.source_type === 'slot' ? slotToNodeId[edge.source_id] : edge.source_id;
      const targetNodeId = edge.target_type === 'slot' ? slotToNodeId[edge.target_id] : edge.target_id;

      if (!sourceNodeId || !targetNodeId) return null;

      const prevEdge = prevEdges.find(e => e.id === edge.id);

      return {
        id: edge.id ?? `${edge.source_id}-${edge.target_id}`,
        source: sourceNodeId,
        target: targetNodeId,
        sourceHandle: edge.source_id,
        targetHandle: edge.target_id,
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
