import { useReactFlow } from '@xyflow/react';
import { useEffect } from 'react';
import type { AppFlowEdge, AppFlowNode } from '../../canvas/types';
import { getNextDownstreamNodeId, getNextUpstreamNodeId, getSiblingNodeId } from '../../domain/graph/traversal';

export const useGraphKeyboardShortcuts = () => {
  const { getNodes, getEdges, setNodes } = useReactFlow();

  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return;
      }

      const nodes = getNodes() as AppFlowNode[];
      const edges = getEdges() as AppFlowEdge[];
      const selectedNodeId = nodes.find(n => n.selected)?.id || null;

      if (selectedNodeId !== null) {
        // Topological Node Traversal
        if (['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
          e.preventDefault();
          e.stopPropagation();

          let targetId: string | null = null;

          if (e.key === 'ArrowRight') {
            targetId = getNextDownstreamNodeId(selectedNodeId, nodes, edges);
          } else if (e.key === 'ArrowLeft') {
            targetId = getNextUpstreamNodeId(selectedNodeId, nodes, edges);
          } else if (e.key === 'ArrowUp') {
            targetId = getSiblingNodeId(selectedNodeId, 'above', nodes, edges);
          } else if (e.key === 'ArrowDown') {
            targetId = getSiblingNodeId(selectedNodeId, 'below', nodes, edges);
          }

          if (targetId) {
            setNodes(nds => nds.map(n => ({ ...n, selected: n.id === targetId })));
          }
          return;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown, true);
    return () => {
      window.removeEventListener('keydown', handleKeyDown, true);
    };
  }, [
    getNodes,
    getEdges,
    setNodes,
  ]);
};
