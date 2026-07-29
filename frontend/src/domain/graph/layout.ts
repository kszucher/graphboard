import type { ElkExtendedEdge, ElkNode, ElkPort, LayoutOptions } from 'elkjs';
import ELK from 'elkjs/lib/elk-api.js';
import type { AppFlowEdge, AppFlowNode } from '../../canvas/types';

const elk = new ELK({
  workerFactory: () =>
    new Worker(
      new URL('elkjs/lib/elk-worker.min.js', import.meta.url),
      { type: 'classic' }
    ),
});

export const NODE_PADDING = 6;
const ROW_HEIGHT = 30;

const ELK_LAYOUT_OPTIONS: LayoutOptions = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.randomSeed': '42',
  'elk.portConstraints': 'FIXED_POS',
  'elk.spacing.nodeNode': '45',
  'elk.spacing.edgeEdge': '29',
  'elk.spacing.edgeNode': '30',
  'elk.layered.spacing.nodeNodeBetweenLayers': '60',
  'elk.layered.spacing.edgeEdgeBetweenLayers': '30',
  'elk.layered.spacing.edgeNodeBetweenLayers': '30',
  'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
  'elk.layered.thoroughness': '30',
  'org.eclipse.elk.layered.nodePlacement.bk.edgeStraightening': 'NONE',
  'org.eclipse.elk.layered.nodePlacement.favorStraightEdges': 'false',
  'org.eclipse.elk.layered.cycleBreaking.strategy': 'DEPTH_FIRST',
  'org.eclipse.elk.layered.feedbackEdges': 'true',
};

const rowCenter = (rowIndex: number) =>
  NODE_PADDING / 2 + ROW_HEIGHT * rowIndex + ROW_HEIGHT / 2;

const getUniqueHandles = (
  edges: AppFlowEdge[],
  key: 'sourceHandle' | 'targetHandle'
): string[] => {
  return Array.from(
    new Set(edges.map((e) => e[key]).filter((id): id is string => !!id))
  );
};

const buildElkNodes = (
  nodes: AppFlowNode[],
  edges: AppFlowEdge[]
): ElkNode[] => {
  const incomingMap: Record<string, AppFlowEdge[]> = {};
  const outgoingMap: Record<string, AppFlowEdge[]> = {};
  edges.forEach((e) => {
    (incomingMap[e.target] ??= []).push(e);
    (outgoingMap[e.source] ??= []).push(e);
  });

  return nodes.map((node) => {
    const nodeType = node.data?.node?.node_type ?? '';
    const nodeSlots = node.data?.node?.slots ?? [];
    const isStart = nodeType === 'START';
    const isEnd = nodeType === 'END';

    const nodeWidth = node.measured?.width ?? node.width ?? 150;
    const nodeHeight = node.measured?.height ?? node.height ?? (ROW_HEIGHT * (1 + nodeSlots.length) + NODE_PADDING);

    const ports: ElkPort[] = [];

    // WEST ports (incoming)
    getUniqueHandles(incomingMap[node.id] ?? [], 'targetHandle')
      .forEach((handleId) => {
        const slotIdx = nodeSlots.findIndex((s) => s.id === handleId);
        const rowIdx = handleId === node.id ? 0 : (slotIdx !== -1 ? 1 + slotIdx : 1);
        ports.push({
          id: `${node.id}-target-${handleId}`,
          x: -NODE_PADDING,
          y: rowCenter(rowIdx),
          width: 0,
          height: 0,
          layoutOptions: { 'port.side': 'WEST' },
        });
      });

    // EAST ports (outgoing)
    getUniqueHandles(outgoingMap[node.id] ?? [], 'sourceHandle')
      .forEach((handleId) => {
        const slotIdx = nodeSlots.findIndex((s) => s.id === handleId);
        const rowIdx = handleId === node.id ? 0 : (slotIdx !== -1 ? 1 + slotIdx : 1);
        ports.push({
          id: `${node.id}-source-${handleId}`,
          x: nodeWidth + NODE_PADDING,
          y: rowCenter(rowIdx),
          width: 0,
          height: 0,
          layoutOptions: { 'port.side': 'EAST' },
        });
      });

    const layoutOptions: LayoutOptions = { 'elk.portConstraints': 'FIXED_POS' };
    if (isStart) layoutOptions['org.eclipse.elk.layered.layering.layerConstraint'] = 'FIRST';
    if (isEnd) layoutOptions['org.eclipse.elk.layered.layering.layerConstraint'] = 'LAST';

    return { id: node.id, width: nodeWidth, height: nodeHeight, ports, layoutOptions };
  });
};

const buildElkEdges = (edges: AppFlowEdge[]): ElkExtendedEdge[] =>
  edges.map((edge) => ({
    id: edge.id,
    sources: [`${edge.source}-source-${edge.sourceHandle}`],
    targets: [`${edge.target}-target-${edge.targetHandle}`],
  }));

const getLayoutedElements = async (
  nodes: AppFlowNode[],
  edges: AppFlowEdge[]
): Promise<{
  positions: Record<string, { x: number; y: number }>;
  edgeSections: Record<string, ElkExtendedEdge>;
}> => {
  const startTime = performance.now();
  const layoutedGraph = await elk.layout({
    id: 'root',
    layoutOptions: ELK_LAYOUT_OPTIONS,
    children: buildElkNodes(nodes, edges),
    edges: buildElkEdges(edges),
  });
  const duration = performance.now() - startTime;
  console.log(`[ELK Layout] took ${duration.toFixed(2)}ms`);

  const positions: Record<string, { x: number; y: number }> = {};
  layoutedGraph.children?.forEach((n) => {
    positions[n.id] = { x: n.x ?? 0, y: n.y ?? 0 };
  });

  const edgeSections: Record<string, ElkExtendedEdge> = {};
  layoutedGraph.edges?.forEach((e) => {
    edgeSections[e.id] = e;
  });

  return { positions, edgeSections };
};

export const runLayout = async (
  nodes: AppFlowNode[],
  edges: AppFlowEdge[]
): Promise<{ nodes: AppFlowNode[]; edges: AppFlowEdge[] }> => {
  if (nodes.length === 0) return { nodes, edges };
  try {
    const layout = await getLayoutedElements(nodes, edges);

    const updatedNodes = nodes.map(n => {
      const newPos = layout.positions[n.id] || n.position;
      const posChanged = Math.abs(newPos.x - n.position.x) > 0.01 || Math.abs(newPos.y - n.position.y) > 0.01;

      if (!posChanged) {
        return n;
      }

      return {
        ...n,
        position: newPos,
      };
    });

    const updatedEdges = edges.map(e => {
      const elkEdge = layout.edgeSections[e.id];
      const sections = elkEdge?.sections ?? [];

      const sectionsChanged = JSON.stringify(e.data?.sections) !== JSON.stringify(sections);

      if (!sectionsChanged) {
        return e;
      }

      return {
        ...e,
        data: {
          ...e.data,
          sections,
        },
      };
    });

    return { nodes: updatedNodes, edges: updatedEdges };
  } catch (err) {
    console.error('Failed to run ELK layout:', err);
    return { nodes, edges };
  }
};
