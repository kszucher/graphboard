import { Box, Flex, Separator } from '@radix-ui/themes';
import { useNodes } from '@xyflow/react';
import type { AppFlowNode } from '../canvas/types';
import { FullCodeEditor } from './FullCodeEditor';
import { NodeEditorRouter } from './nodeEditors/NodeEditorRouter';
import { StateEditor } from './nodeEditors/StateEditor';

interface SidebarProps {
  isSidebarOpen: boolean;
  isGraphSelected: boolean;
  graphId: string;
}

export const Sidebar = ({ isSidebarOpen, isGraphSelected, graphId }: SidebarProps) => {
  const nodes = useNodes();
  const selectedNode = nodes.find((n) => n.selected);

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
      <Flex
        direction="column"
        style={{
          width: '500px',
          height: '100%',
          minHeight: 0,
          boxSizing: 'border-box',
        }}
      >
        {/* Top Panel: Workflow Code Viewer (50% height) */}
        <Box style={{
          height: '50%',
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          padding: '16px 16px 8px 16px'
        }}>
          <FullCodeEditor graphId={graphId}/>
        </Box>

        {/* Separator Divider */}
        <Separator size="4" style={{ backgroundColor: 'var(--gray-4)' }}/>

        {/* Bottom Section (50% height) split into two equal vertical parts */}
        <Flex
          direction="column"
          gap="3"
          style={{
            height: '50%',
            minHeight: 0,
            padding: '8px 16px 16px 16px',
            boxSizing: 'border-box',
          }}
        >
          {/* Top half of bottom section (State Editor) */}
          <Box style={{ flex: '1 1 50%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <StateEditor graphId={graphId} disabled={!isGraphSelected}/>
          </Box>

          {/* Bottom half of bottom section (Node Editor) */}
          <Box style={{ flex: '1 1 50%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <NodeEditorRouter
              graphId={graphId}
              selectedNode={(selectedNode as AppFlowNode) || null}
              disabled={!isGraphSelected}
            />
          </Box>
        </Flex>
      </Flex>
    </Box>
  );
};
