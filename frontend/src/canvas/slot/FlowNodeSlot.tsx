import { Flex } from '@radix-ui/themes';
import { Handle, Position } from '@xyflow/react';
import { memo } from 'react';
import { NODE_PADDING } from '../../domain/graph/layout';
import { Editor } from '../../editor/Editor.tsx';
import type { ApiSlot, NodeType } from '../types';

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
  const leftHandle = false;
  const rightHandle = true;

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
          onSave={() => {
          }}
          disabled={disabled}
          readOnly={true}
          parentNodeSelected={parentNodeSelected}
        />
      </Flex>
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
