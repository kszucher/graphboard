import { Box, Text } from '@radix-ui/themes';
import type { AppFlowNode, NodeType } from '../../canvas/types';
import { LogicalAssignerNodeEditor } from './LogicalAssignerNodeEditor';
import { SwitchNodeEditor } from './SwitchNodeEditor';
import { AgenticAssignerNodeEditor } from './AgenticAssignerNodeEditor';

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

  if (selectedNodeType === 'LOGICAL_ASSIGNER' && selectedNodeId) {
    return <LogicalAssignerNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled}/>;
  }

  if (selectedNodeType === 'AGENTIC_ASSIGNER' && selectedNodeId) {
    return <AgenticAssignerNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled}/>;
  }

  if (selectedNodeType === 'SWITCH' && selectedNodeId) {
    return <SwitchNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled}/>;
  }

  return (
    <Box
      style={{
        height: '100%',
        backgroundColor: 'var(--gray-1)',
        border: '1px solid var(--gray-5)',
        borderRadius: 'var(--radius-3)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <Text size="2" color="gray" style={{ textAlign: 'center' }}>
        Select a <Text weight="bold">LOGICAL ASSIGNER</Text>, <Text weight="bold">AGENTIC ASSIGNER</Text>, or <Text
        weight="bold">SWITCH</Text> node on the canvas to edit operation settings.
      </Text>
    </Box>
  );
};
