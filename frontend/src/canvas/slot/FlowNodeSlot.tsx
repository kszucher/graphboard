import { Flex } from '@radix-ui/themes';
import { Handle, Position } from '@xyflow/react';
import { memo, useCallback, useMemo } from 'react';
import { useUpdateSlot } from '../../api/mutations';
import { useGraphQuery } from '../../api/queries';
import { NODE_PADDING } from '../../domain/graph/layout';
import { fromApiPayload } from '../../domain/graph/mappers';
import { Editor } from '../../editor/Editor.tsx';
import { useCurrentGraphId } from '../../hooks/graph/useCurrentGraphId';
import type { ApiSlot } from '../types';
import { FlowNodeSlotActions } from './FlowNodeSlotActions.tsx';

interface FlowNodeSlotProps {
  slotId: string;
  disabled: boolean;
  isStart: boolean;
  isEnd: boolean;
  parentNodeSelected: boolean;
}

export const FlowNodeSlot = memo(({
  slotId,
  disabled,
  isStart,
  isEnd,
  parentNodeSelected,
}: FlowNodeSlotProps) => {
  const graphId = useCurrentGraphId();
  const { data } = useGraphQuery(graphId);
  const { nodes } = useMemo(() => {
    if (!data) return { nodes: [] };
    return fromApiPayload(data.nodes, []);
  }, [data]);

  const { mutateAsync: updateSlot } = useUpdateSlot(graphId);

  const node = useMemo(() => {
    return nodes.find((n) => n.data.node.slots?.some((s: ApiSlot) => s.id === slotId));
  }, [nodes, slotId]);

  const slot = useMemo(() => {
    return node?.data.node.slots?.find((s: ApiSlot) => s.id === slotId);
  }, [node, slotId]);

  const handleUpdateItem = useCallback(
    (newValue: string) => {
      void updateSlot({ slotId, rawString: newValue });
    },
    [slotId, updateSlot]
  );

  if (!slot) return null;

  const leftHandle = false;
  const rightHandle = true;

  const actions = !disabled ? (
    <div
      onPointerDown={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        flexShrink: 0,
        paddingRight: '2px',
        visibility: parentNodeSelected ? 'visible' : 'hidden',
      }}
    >
      <FlowNodeSlotActions
        slotId={slot.id}
      />
    </div>
  ) : null;

  const initialValue = (() => {
    if (isStart) return slot.raw_string || 'Start Node (Output)';
    if (isEnd) return slot.raw_string || 'End Node (Input)';
    return slot.raw_string;
  })();

  return (
    <Flex align="center" width="100%" height="24px" style={{ position: 'relative', gap: '6px' }}>
      {leftHandle && (
        <Handle
          type="target"
          id={slot.id}
          position={Position.Left}
          style={{ left: -NODE_PADDING }}
        />
      )}
      <Flex
        className="nodrag nopan"
        flexGrow="1"
        align="center"
        height="100%"
      >
        <Editor
          initialValue={initialValue}
          onSave={handleUpdateItem}
          disabled={disabled}
          parentNodeSelected={parentNodeSelected}
        />
      </Flex>
      {actions}
      {rightHandle && (
        <Handle
          type="source"
          id={slot.id}
          position={Position.Right}
          style={{ right: -NODE_PADDING }}
        />
      )}
    </Flex>
  );
});
