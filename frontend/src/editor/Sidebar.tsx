import { Box, Button, Flex, Separator, Text } from '@radix-ui/themes';
import { useNodes } from '@xyflow/react';
import { useRunGraph } from '../hooks/graph/useGraphMutations';
import { DefinerVariableEditor } from './DefinerVariableEditor';
import { FullCodeEditor } from './FullCodeEditor';
import { LogicalAssignerEditor } from './LogicalAssignerEditor';

interface SidebarProps {
  isSidebarOpen: boolean;
  isGraphSelected: boolean;
  graphId: string;
}

export const Sidebar = ({ isSidebarOpen, isGraphSelected, graphId }: SidebarProps) => {
  const { mutate: runGraph } = useRunGraph(graphId);
  const nodes = useNodes();
  const selectedNode = nodes.find((n) => n.selected);
  const selectedNodeType = (selectedNode?.data as any)?.node?.node_type;
  const selectedNodeId = selectedNode?.id;

  return (
    <Box
      style={{
        width: isSidebarOpen ? '500px' : '0px',
        minWidth: isSidebarOpen ? '500px' : '0px',
        height: '100%',
        borderRight: isSidebarOpen ? '1px solid var(--gray-4)' : 'none',
        backgroundColor: 'var(--gray-2)',
        transition: 'width 0.2s ease-in-out, min-width 0.2s ease-in-out',
        overflowX: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Flex direction="column" gap="3" p="4"
            style={{ width: '500px', height: '100%', minHeight: 0, boxSizing: 'border-box' }}>
        {/* Header */}
        <Flex justify="between" align="center" style={{ flexShrink: 0 }}>
          <Text size="3" weight="bold">Workflow Code</Text>
          <Button
            size="2"
            variant="solid"
            color="green"
            onClick={() => void runGraph()}
            disabled={!isGraphSelected}
            style={{ cursor: isGraphSelected ? 'pointer' : 'default' }}
          >
            ▶ Run Graph
          </Button>
        </Flex>

        {/* Top Panel: Workflow Code Viewer */}
        <Box style={{ flex: '1 1 0%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <FullCodeEditor graphId={graphId}/>
        </Box>

        {/* Separator Divider */}
        <Separator size="4" style={{ backgroundColor: 'var(--gray-4)' }}/>

        {/* Bottom Panel: Dynamic Node Editor (~300px height) */}
        <Box style={{ height: '300px', minHeight: '300px', flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
          {selectedNodeType === 'DEFINER' && selectedNodeId ? (
            <DefinerVariableEditor graphId={graphId} nodeId={selectedNodeId} disabled={!isGraphSelected} />
          ) : selectedNodeType === 'LOGICAL_ASSIGNER' && selectedNodeId ? (
            <LogicalAssignerEditor graphId={graphId} nodeId={selectedNodeId} disabled={!isGraphSelected} />
          ) : (
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
                Select a <Text weight="bold">DEFINER</Text> or <Text weight="bold">LOGICAL_ASSIGNER</Text> node on the canvas to edit operation settings.
              </Text>
            </Box>
          )}
        </Box>
      </Flex>
    </Box>
  );
};

