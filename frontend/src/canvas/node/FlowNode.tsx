import type { BadgeProps } from '@radix-ui/themes';
import { Badge, Flex } from '@radix-ui/themes';
import { Handle, type NodeProps, Position, useUpdateNodeInternals } from '@xyflow/react';
import { memo, useEffect } from 'react';
import { NODE_PADDING } from '../../domain/graph/layout';
import { FlowNodeSlot } from '../slot/FlowNodeSlot.tsx';
import { type AppFlowNode, type NodeType } from '../types.ts';

const NODE_COLORS: Record<NodeType, BadgeProps['color']> = {
  START: 'gray',
  END: 'gray',
  LOGICAL_SWITCH: 'amber',
  LOGICAL_ASSIGNER: 'teal',
  AGENTIC_ASSIGNER: 'pink',
  INTERRUPT: 'orange',
  AGENTIC_SWITCH: 'indigo',
};

const CustomNodeComponent = ({ data, id, selected }: NodeProps<AppFlowNode>) => {
  const updateNodeInternals = useUpdateNodeInternals();

  useEffect(() => {
    updateNodeInternals(id);
  }, [id, updateNodeInternals, data?.node?.slots, data?.node?.node_type, data?.node?.is_input, data?.node?.is_output]);

  if (!data) return null;

  const { node } = data;
  const mySlots = node.slots || [];
  const isStart = node.node_type === 'START';
  const isEnd = node.node_type === 'END';

  return (
    <Flex
      direction="column"
      style={{
        width: 'max-content',
        background: 'var(--gray-3)',
        borderRadius: 'var(--radius-3)',
        padding: NODE_PADDING,
        gap: NODE_PADDING,
        outline: selected ? '2px solid var(--accent-8)' : '1px solid var(--gray-5)',
        boxShadow: 'none',
      }}
    >
      <Flex align="center" width="100%" height="24px" style={{ position: 'relative', gap: '6px' }}>
        {data.node.is_input && (
          <Handle
            type="target"
            id={id}
            position={Position.Left}
            style={{ left: -NODE_PADDING }}
          />
        )}
        <Flex direction="row" gap="1" align="center" flexGrow="1">
          <Badge color={NODE_COLORS[data.node.node_type]} size="1" style={{ height: 'var(--space-5)' }}>
            {id}
          </Badge>
        </Flex>

        {data.node.is_output && (
          <Handle
            type="source"
            id={id}
            position={Position.Right}
            style={{ right: -NODE_PADDING }}
          />
        )}
      </Flex>

      {mySlots.map((slot) => {
        const disabled = isStart || isEnd;

        return (
          <FlowNodeSlot
            key={slot.id}
            slot={slot}
            nodeType={data.node.node_type}
            disabled={disabled}
            isStart={isStart}
            isEnd={isEnd}
            parentNodeSelected={selected}
          />
        );
      })}
    </Flex>
  );
};

export const CustomNode = memo(CustomNodeComponent, (prevProps, nextProps) => {
  return (
    prevProps.id === nextProps.id &&
    prevProps.selected === nextProps.selected &&
    prevProps.dragging === nextProps.dragging &&
    prevProps.data === nextProps.data
  );
});
