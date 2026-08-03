import { ArrowDownIcon, ArrowUpIcon, PlusIcon, TrashIcon } from '@radix-ui/react-icons';
import { DropdownMenu } from '@radix-ui/themes';
import { useCallback, useMemo } from 'react';
import { useCreateSlot, useDeleteEdge, useDeleteSlot, useInsertNode, useMoveSlot, } from '../../api/mutations';
import { useGraphQuery } from '../../api/queries';
import { fromApiPayload } from '../../domain/graph/mappers';
import { getIncomingEdgeOptions, getOutgoingEdgeOptions } from '../../domain/graph/traversal';
import { useCurrentGraphId } from '../../hooks/graph/useCurrentGraphId';
import { type ApiSlot, INSERTABLE_NODE_ITEMS, type InsertableNodeType } from '../types';

interface SlotActionsContentProps {
  slotId: string;
}

export const FlowNodeSlotActionsContent = ({
  slotId,
}: SlotActionsContentProps) => {
  const graphId = useCurrentGraphId();
  const { data } = useGraphQuery(graphId);
  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    return fromApiPayload(data.nodes, data.edges);
  }, [data]);

  const { mutateAsync: createSlot } = useCreateSlot(graphId);
  const { mutateAsync: deleteSlot } = useDeleteSlot(graphId);
  const { mutateAsync: moveSlot } = useMoveSlot(graphId);
  const { mutateAsync: deleteEdge } = useDeleteEdge(graphId);
  const { mutateAsync: insertNode } = useInsertNode(graphId);

  const node = useMemo(() => {
    return nodes.find(n => n.data.node.slots?.some((s: ApiSlot) => s.id === slotId));
  }, [nodes, slotId]);

  const slot = useMemo(() => {
    return node?.data.node.slots?.find((s: ApiSlot) => s.id === slotId);
  }, [node, slotId]);

  const mySlots = useMemo(() => {
    return node ? (node.data.node.slots ?? []) : [];
  }, [node]);

  const indexInNode = useMemo(() => {
    if (!slot) return -1;
    return mySlots.findIndex((s: ApiSlot) => s.id === slotId);
  }, [mySlots, slotId, slot]);

  const canMoveUp = useMemo(() => {
    if (indexInNode === -1) return false;
    return indexInNode > 0;
  }, [indexInNode]);

  const canMoveDown = useMemo(() => {
    if (indexInNode === -1) return false;
    return indexInNode < mySlots.length - 1;
  }, [indexInNode, mySlots.length]);

  const canDelete = useMemo(() => {
    return mySlots.length > 1;
  }, [mySlots]);

  const outgoingEdgeOptions = useMemo(() => {
    return getOutgoingEdgeOptions(slotId, edges, nodes);
  }, [slotId, edges, nodes]);

  const incomingEdgeOptions = useMemo(() => {
    return getIncomingEdgeOptions(slotId, edges, nodes);
  }, [slotId, edges, nodes]);

  const hasOutgoingEdges = useMemo(() => {
    return edges.some(e => e.sourceHandle === slotId);
  }, [edges, slotId]);

  const hasIncomingEdges = useMemo(() => {
    return edges.some(e => e.targetHandle === slotId);
  }, [edges, slotId]);

  const showAddConnected = !hasOutgoingEdges;

  const handleInsert = useCallback(
    (nodeType: InsertableNodeType) => {
      void insertNode({ connectorId: slotId, nodeType, direction: 'after' });
    },
    [insertNode, slotId]
  );

  const handleMoveTop = useCallback(() => {
    void moveSlot({ slotId, direction: 'top' });
  }, [slotId, moveSlot]);

  const handleMoveUp = useCallback(() => {
    void moveSlot({ slotId, direction: 'up' });
  }, [slotId, moveSlot]);

  const handleMoveDown = useCallback(() => {
    void moveSlot({ slotId, direction: 'down' });
  }, [slotId, moveSlot]);

  const handleMoveBottom = useCallback(() => {
    void moveSlot({ slotId, direction: 'bottom' });
  }, [slotId, moveSlot]);

  const handleDeleteItem = useCallback(() => {
    void deleteSlot(slotId);
  }, [slotId, deleteSlot]);

  const handleAddAbove = useCallback(() => {
    if (!slot || !node) return;
    void createSlot({ nodeId: node.id, index: indexInNode });
  }, [createSlot, node, slot, indexInNode]);

  const handleAddBelow = useCallback(() => {
    if (!slot || !node) return;
    void createSlot({ nodeId: node.id, index: indexInNode + 1 });
  }, [createSlot, node, slot, indexInNode]);

  const renderAddConnectedSubmenu = () => {
    return (
      <DropdownMenu.Sub>
        <DropdownMenu.SubTrigger>
          <PlusIcon style={{ marginRight: 8 }}/> Add Connected Node
        </DropdownMenu.SubTrigger>
        <DropdownMenu.SubContent>
          {INSERTABLE_NODE_ITEMS.map(item => (
            <DropdownMenu.Item key={item.type} onClick={() => handleInsert(item.type)}>
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
      {
        <>
          <DropdownMenu.Item onClick={handleAddAbove}>
            <PlusIcon style={{ marginRight: 8 }}/> Add Slot Above
          </DropdownMenu.Item>
          <DropdownMenu.Item onClick={handleAddBelow}>
            <PlusIcon style={{ marginRight: 8 }}/> Add Slot Below
          </DropdownMenu.Item>
          <DropdownMenu.Separator/>
        </>
      }

      {showAddConnected && renderAddConnectedSubmenu()}
      {showAddConnected && <DropdownMenu.Separator/>}

      {
        <>
          <DropdownMenu.Item onClick={handleMoveTop} disabled={!canMoveUp}>
            <ArrowUpIcon style={{ marginRight: 8 }}/> Move to Top
          </DropdownMenu.Item>
          <DropdownMenu.Item onClick={handleMoveUp} disabled={!canMoveUp}>
            <ArrowUpIcon style={{ marginRight: 8 }}/> Move Up
          </DropdownMenu.Item>
          <DropdownMenu.Item onClick={handleMoveDown} disabled={!canMoveDown}>
            <ArrowDownIcon style={{ marginRight: 8 }}/> Move Down
          </DropdownMenu.Item>
          <DropdownMenu.Item onClick={handleMoveBottom} disabled={!canMoveDown}>
            <ArrowDownIcon style={{ marginRight: 8 }}/> Move to Bottom
          </DropdownMenu.Item>
          <DropdownMenu.Separator/>
        </>
      }

      {renderDeleteSubmenu('outgoing')}
      {renderDeleteSubmenu('incoming')}

      {
        <>
          <DropdownMenu.Separator/>
          <DropdownMenu.Item onClick={handleDeleteItem} color="red" disabled={!canDelete}>
            <TrashIcon style={{ marginRight: 8 }}/> Delete Slot
          </DropdownMenu.Item>
        </>
      }
    </>
  );
};
