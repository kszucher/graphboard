import { PlusIcon } from '@radix-ui/react-icons';
import { DropdownMenu } from '@radix-ui/themes';
import { useCallback, useMemo } from 'react';
import { useDeleteEdge, useDeleteNode, useInsertNode, useShortcircuitNode } from '../../api/mutations';
import { useGraphQuery } from '../../api/queries';
import { fromApiPayload } from '../../domain/graph/mappers';
import { getIncomingEdgeOptions, getOutgoingEdgeOptions } from '../../domain/graph/traversal';
import { useCurrentGraphId } from '../../hooks/graph/useCurrentGraphId';
import type { InsertableNodeType, NodeType } from '../types';


const INSERTABLE_NODE_TYPES: { type: InsertableNodeType; label: string }[] = [
  { type: 'STEP', label: 'Step' },
  { type: 'SWITCH', label: 'Switch' },
  { type: 'DEFINER', label: 'Definer' },
  { type: 'LOGICAL_ASSIGNER', label: 'Logical Assigner' },
  { type: 'AGENTIC_ASSIGNER', label: 'Agentic Assigner' },
];

interface FlowNodeActionsContentProps {
  nodeId: string;
  onRenameClick: () => void;
}

export const FlowNodeActionsContent = ({ nodeId, onRenameClick }: FlowNodeActionsContentProps) => {
  const graphId = useCurrentGraphId();
  const { data } = useGraphQuery(graphId);
  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    return fromApiPayload(data.nodes, data.edges);
  }, [data]);

  const { mutateAsync: deleteNode } = useDeleteNode(graphId);
  const { mutateAsync: shortcircuitNode } = useShortcircuitNode(graphId);
  const { mutateAsync: deleteEdge } = useDeleteEdge(graphId);
  const { mutateAsync: insertNode } = useInsertNode(graphId);

  const nodeData = useMemo(() => {
    return nodes.find(n => n.id === nodeId)?.data?.node;
  }, [nodes, nodeId]);

  const isInput = nodeData?.is_input ?? false;
  const isOutput = nodeData?.is_output ?? false;

  const outgoingEdgeOptions = useMemo(() => {
    return getOutgoingEdgeOptions(nodeId, edges, nodes);
  }, [nodeId, edges, nodes]);

  const incomingEdgeOptions = useMemo(() => {
    return getIncomingEdgeOptions(nodeId, edges, nodes);
  }, [nodeId, edges, nodes]);

  const hasOutgoingEdges = useMemo(() => {
    return edges.some(e => e.sourceHandle === nodeId);
  }, [edges, nodeId]);

  const hasIncomingEdges = useMemo(() => {
    return edges.some(e => e.targetHandle === nodeId);
  }, [edges, nodeId]);

  const showAddBefore = isInput && !hasIncomingEdges;
  const showAddAfter = isOutput && !hasOutgoingEdges;

  const handleDelete = useCallback(() => {
    if (nodeData) void deleteNode(nodeData.id);
  }, [nodeData, deleteNode]);

  const handleShortcircuit = useCallback(() => {
    if (nodeData) void shortcircuitNode(nodeData.id);
  }, [nodeData, shortcircuitNode]);

  const handleInsert = useCallback(
    (nodeType: InsertableNodeType, direction: 'before' | 'after') => {
      void insertNode({ connectorId: nodeId, nodeType, direction });
    },
    [insertNode, nodeId]
  );

  if (!nodeData) return null;

  const isSentinel = nodeData.node_type === 'START' || nodeData.node_type === 'END' || nodeData.node_type === 'DEFINER';

  const canShortcircuit = nodeData
    ? (['STEP', 'LOGICAL_ASSIGNER', 'AGENTIC_ASSIGNER'] as NodeType[]).includes(nodeData.node_type)
    : false;

  const renderAddConnectedSubmenu = (direction: 'before' | 'after') => {
    const isAfter = direction === 'after';
    const label = isAfter ? 'Add Connected Node After' : 'Add Connected Node Before';
    return (
      <DropdownMenu.Sub>
        <DropdownMenu.SubTrigger>
          <PlusIcon style={{ marginRight: 8 }}/> {label}
        </DropdownMenu.SubTrigger>
        <DropdownMenu.SubContent>
          {INSERTABLE_NODE_TYPES.map(item => (
            <DropdownMenu.Item key={item.type} onClick={() => handleInsert(item.type, direction)}>
              {item.label}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.SubContent>
      </DropdownMenu.Sub>
    );
  };

  const renderDeleteSubmenu = (direction: 'incoming' | 'outgoing') => {
    const isOutgoing = direction === 'outgoing';
    const label = isOutgoing ? 'Delete Outgoing Edge' : 'Delete Incoming Edge';
    const hasEdges = isOutgoing ? hasOutgoingEdges : hasIncomingEdges;
    const options = isOutgoing ? outgoingEdgeOptions : incomingEdgeOptions;
    return (
      <DropdownMenu.Sub>
        <DropdownMenu.SubTrigger disabled={!hasEdges}>
          {label}
        </DropdownMenu.SubTrigger>
        <DropdownMenu.SubContent>
          {options.map(opt => (
            <DropdownMenu.Item
              key={opt.edgeId}
              onClick={() => {
                void deleteEdge(opt.edgeId);
              }}
              color="red"
            >
              {opt.label}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.SubContent>
      </DropdownMenu.Sub>
    );
  };

  return (
    <>
      {!isSentinel && (
        <>
          {showAddBefore && renderAddConnectedSubmenu('before')}
          {showAddAfter && renderAddConnectedSubmenu('after')}
          {(showAddBefore || showAddAfter) && <DropdownMenu.Separator/>}

          {renderDeleteSubmenu('incoming')}
          {renderDeleteSubmenu('outgoing')}

          <DropdownMenu.Separator/>
        </>
      )}

      {!isSentinel && canShortcircuit && (
        <DropdownMenu.Item onClick={handleShortcircuit}>
          {'Shortcircuit'}
        </DropdownMenu.Item>
      )}
      {!isSentinel && (
        <DropdownMenu.Item onClick={onRenameClick}>
          {'Rename'}
        </DropdownMenu.Item>
      )}
      {!isSentinel && (
        <DropdownMenu.Item onClick={handleDelete}>
          {'Delete'}
        </DropdownMenu.Item>
      )}
    </>
  );
};
