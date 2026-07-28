import { Box, Text } from '@radix-ui/themes';
import type { NodeType, AppFlowNode } from '../../canvas/types';
import { DefinerNodeEditor } from './DefinerNodeEditor';
import { LogicalAssignerNodeEditor } from './LogicalAssignerNodeEditor';
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

  if (selectedNodeType === 'DEFINER' && selectedNodeId) {
    return <DefinerNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;
  }

  if (selectedNodeType === 'LOGICAL_ASSIGNER' && selectedNodeId) {
    return <LogicalAssignerNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;
  }

  if (selectedNodeType === 'SWITCH' && selectedNodeId) {
    return <SwitchNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={disabled} />;
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
        Select a <Text weight="bold">DEFINER</Text>, <Text weight="bold">LOGICAL ASSIGNER</Text>, or <Text weight="bold">SWITCH</Text> node on the canvas to edit operation settings.
      </Text>
    </Box>
  );
};
