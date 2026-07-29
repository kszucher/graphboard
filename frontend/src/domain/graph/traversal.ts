import type { AppFlowEdge, AppFlowNode } from '../../canvas/types';

interface EdgeOption {
  edgeId: string;
  label: string;
}

export const getOutgoingEdgeOptions = (
  connectorId: string,
  edges: AppFlowEdge[],
  nodes: AppFlowNode[]
): EdgeOption[] => {
  const outgoingEdges = edges.filter(e => e.sourceHandle === connectorId);
  return outgoingEdges.map(edge => {
    const targetNode = nodes.find(n => n.id === edge.target);
    return {
      edgeId: edge.id,
      label: `To ${targetNode?.id || edge.target}`,
    };
  });
};

export const getIncomingEdgeOptions = (
  connectorId: string,
  edges: AppFlowEdge[],
  nodes: AppFlowNode[]
): EdgeOption[] => {
  const incomingEdges = edges.filter(e => e.targetHandle === connectorId);
  return incomingEdges.map(edge => {
    const sourceNode = nodes.find(n => n.id === edge.source);
    return {
      edgeId: edge.id,
      label: `From ${sourceNode?.id || edge.source}`,
    };
  });
};

export const getNextDownstreamNodeId = (
  currentNodeId: string,
  nodes: AppFlowNode[],
  edges: AppFlowEdge[]
): string | null => {
  const currentNode = nodes.find(n => n.id === currentNodeId);
  if (!currentNode) return null;

  const slots = currentNode.data.node.slots || [];
  for (const slot of slots) {
    const edge = edges.find(eg => eg.source === currentNodeId && eg.sourceHandle === slot.id);
    if (edge) return edge.target;
  }

  const nodeEdge = edges.find(eg => eg.source === currentNodeId && eg.sourceHandle === currentNodeId);
  if (nodeEdge) return nodeEdge.target;

  const anyEdge = edges.find(eg => eg.source === currentNodeId);
  return anyEdge ? anyEdge.target : null;
};

export const getNextUpstreamNodeId = (
  currentNodeId: string,
  _nodes: AppFlowNode[],
  edges: AppFlowEdge[]
): string | null => {
  const incomingEdge = edges.find(eg => eg.target === currentNodeId);
  return incomingEdge ? incomingEdge.source : null;
};

export const getSiblingNodeId = (
  currentNodeId: string,
  position: 'above' | 'below',
  nodes: AppFlowNode[],
  edges: AppFlowEdge[]
): string | null => {
  // Traces upstream to find the nearest ancestor slot ID
  const getBranchOriginSlotId = (nodeId: string): string | null => {
    let curr = nodeId;
    while (curr) {
      const edge = edges.find(e => e.target === curr);
      if (!edge) return null;
      if (edge.sourceHandle && edge.sourceHandle !== edge.source) return edge.sourceHandle;
      curr = edge.source;
    }
    return null;
  };

  const mySlotId = getBranchOriginSlotId(currentNodeId);
  if (!mySlotId) return null;

  // Sibling node candidates share the same parent node, but originate from a different slot
  const parentNode = nodes.find(n => n.data?.node?.slots?.some(s => s.id === mySlotId));
  const slots = parentNode?.data?.node?.slots || [];
  const mySlotIndex = slots.findIndex(s => s.id === mySlotId);

  const candidates = nodes
    .map(node => {
      const slotId = getBranchOriginSlotId(node.id);
      return { nodeId: node.id, slotIndex: slots.findIndex(s => s.id === slotId) };
    })
    .filter(c => c.slotIndex !== -1 && c.slotIndex !== mySlotIndex);

  if (position === 'above') {
    const above = candidates.filter(c => c.slotIndex < mySlotIndex);
    return above.sort((a, b) => b.slotIndex - a.slotIndex)[0]?.nodeId || null;
  } else {
    const below = candidates.filter(c => c.slotIndex > mySlotIndex);
    return below.sort((a, b) => a.slotIndex - b.slotIndex)[0]?.nodeId || null;
  }
};
