import { Box, Button, Flex, Separator, Text } from '@radix-ui/themes';
import { useNodes } from '@xyflow/react';
import { useRunGraph } from '../hooks/graph/useGraphMutations';
import { FullCodeEditor } from './FullCodeEditor';
import { NodeEditorRouter } from './nodeEditors/NodeEditorRouter';
import type { AppFlowNode } from '../canvas/types';

interface SidebarProps {
  isSidebarOpen: boolean;
  isGraphSelected: boolean;
  graphId: string;
}

export const Sidebar = ({ isSidebarOpen, isGraphSelected, graphId }: SidebarProps) => {
  const { mutate: runGraph } = useRunGraph(graphId);
  const nodes = useNodes();
  const selectedNode = nodes.find((n) => n.selected);

  return (
    <Box
      style={{
        width: isSidebarOpen ? '580px' : '0px',
        minWidth: isSidebarOpen ? '580px' : '0px',
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
            style={{ width: '580px', height: '100%', minHeight: 0, boxSizing: 'border-box' }}>
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
          <NodeEditorRouter graphId={graphId} selectedNode={(selectedNode as AppFlowNode) || null} disabled={!isGraphSelected} />
        </Box>
      </Flex>
    </Box>
  );
};
