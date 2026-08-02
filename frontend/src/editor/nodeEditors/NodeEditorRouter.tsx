import { Box, Text } from '@radix-ui/themes';
import type { AppFlowNode, NodeType } from '../../canvas/types';
import { AgenticAssignerNodeEditor } from './AgenticAssignerNodeEditor';
import { AgenticSwitchNodeEditor } from './AgenticSwitchNodeEditor';
import { ConfirmNodeEditor } from './ConfirmNodeEditor';
import { InterruptNodeEditor } from './InterruptNodeEditor';
import { LogicalAssignerNodeEditor } from './LogicalAssignerNodeEditor';
import { RetryNodeEditor } from './RetryNodeEditor';
import { SwitchNodeEditor } from './SwitchNodeEditor';

interface NodeEditorRouterProps {
  graphId: string;
  selectedNode: AppFlowNode | null;
  disabled?: boolean;
}

export const NodeEditorRouter = ({
  graphId,
  selectedNode,
  disabled = false,
}: NodeEditorRouterProps) => {
  const selectedNodeType: NodeType | undefined = selectedNode?.data?.node?.node_type;
  const selectedNodeId: string | undefined = selectedNode?.id;

  if (!selectedNodeId || !selectedNodeType) {
    return (
      <Box
        style={{
          backgroundColor: 'var(--gray-3)',
          borderRadius: 'var(--radius-3)',
          padding: '16px',
          border: '1px border-dashed var(--gray-5)',
        }}
      >
        <Text size="2" color="gray" weight="bold">
          Node Properties
        </Text>
        <Text size="1" color="gray" style={{ display: 'block', marginTop: '4px' }}>
          Select any node on the canvas to configure node properties.
        </Text>
      </Box>
    );
  }

  switch (selectedNodeType) {
    case 'LOGICAL_ASSIGNER':
    case 'EXTRACT':
    case 'VALIDATE':
      return <LogicalAssignerNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;

    case 'AGENTIC_ASSIGNER':
      return <AgenticAssignerNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;

    case 'SWITCH':
      return <SwitchNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;

    case 'AGENTIC_SWITCH':
      return <AgenticSwitchNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;

    case 'INTERRUPT':
      return <InterruptNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;

    case 'RETRY':
      return <RetryNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;

    case 'CONFIRM':
      return <ConfirmNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;

    case 'REVIEW':
      return (
        <Box style={{ backgroundColor: 'var(--gray-3)', padding: '16px', borderRadius: 'var(--radius-3)' }}>
          <Text size="2" weight="bold" color="gray">
            Review Node ({selectedNodeId})
          </Text>
          <Text size="1" color="gray" style={{ display: 'block', marginTop: '4px' }}>
            Review node acts as a human-in-the-loop passthrough inspection checkpoint in the graph flow.
          </Text>
        </Box>
      );

    case 'START':
    case 'END':
      return (
        <Box style={{ backgroundColor: 'var(--gray-3)', padding: '16px', borderRadius: 'var(--radius-3)' }}>
          <Text size="2" weight="bold" color="gray">
            Sentinel Node ({selectedNodeId})
          </Text>
          <Text size="1" color="gray" style={{ display: 'block', marginTop: '4px' }}>
            {selectedNodeType === 'START' ? 'Graph entry point.' : 'Graph termination point.'}
          </Text>
        </Box>
      );

    default:
      return null;
  }
};
