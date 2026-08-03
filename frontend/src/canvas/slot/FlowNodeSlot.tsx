import { Flex } from '@radix-ui/themes';
import { Handle, Position } from '@xyflow/react';
import { memo, useCallback } from 'react';
import { useUpdateSlot } from '../../api/mutations';
import { NODE_PADDING } from '../../domain/graph/layout';
import { Editor } from '../../editor/Editor.tsx';
import { useCurrentGraphId } from '../../hooks/graph/useCurrentGraphId';
import type { ApiSlot, NodeType } from '../types';
import { FlowNodeSlotActions } from './FlowNodeSlotActions.tsx';

interface FlowNodeSlotProps {
  slot: ApiSlot;
  nodeType: NodeType;
  disabled: boolean;
  isStart: boolean;
  isEnd: boolean;
  parentNodeSelected: boolean;
}

export const FlowNodeSlot = memo(({
  slot,
  disabled,
  isStart,
  isEnd,
  parentNodeSelected,
}: FlowNodeSlotProps) => {
  const graphId = useCurrentGraphId();
  const { mutateAsync: updateSlot } = useUpdateSlot(graphId);

  const handleUpdateItem = useCallback(
    (newValue: string) => {
      void updateSlot({ slotId: slot.id, rawString: newValue });
    },
    [slot.id, updateSlot]
  );

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
