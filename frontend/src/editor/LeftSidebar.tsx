import { Box, Flex, Separator } from '@radix-ui/themes';
import { useNodes } from '@xyflow/react';
import type { AppFlowNode } from '../canvas/types';
import { NodeEditorRouter } from './nodeEditors/NodeEditorRouter';
import { StateEditor } from './nodeEditors/StateEditor';

interface LeftSidebarProps {
  isGraphSelected: boolean;
  graphId: string;
}

export const LeftSidebar = ({ isGraphSelected, graphId }: LeftSidebarProps) => {
  const nodes = useNodes();
  const selectedNode = (nodes.find((n) => n.selected) as AppFlowNode | undefined) || null;

  return (
    <Box
      style={{
        width: '450px',
        minWidth: '450px',
        height: '100%',
        borderRight: '1px solid var(--gray-4)',
        backgroundColor: 'var(--gray-2)',
        overflowX: 'hidden',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        padding: '16px',
      }}
    >
      <Flex direction="column" gap="4" style={{ minHeight: 0 }}>
        {/* 1. Graph State Schema Editor */}
        <Box style={{ flexShrink: 0 }}>
          <StateEditor graphId={graphId} disabled={!isGraphSelected}/>
        </Box>

        <Separator size="4" style={{ backgroundColor: 'var(--gray-4)' }}/>

        {/* 2. Dynamic Node Editor Router */}
        <Box style={{ flexShrink: 0 }}>
          <NodeEditorRouter
            graphId={graphId}
            selectedNode={selectedNode}
            disabled={!isGraphSelected}
          />
        </Box>
      </Flex>
    </Box>
  );
};
