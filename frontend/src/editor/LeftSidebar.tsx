import { Box, Flex, Separator, Text } from '@radix-ui/themes';
import { useNodes } from '@xyflow/react';
import type { AppFlowNode } from '../canvas/types';
import { AgenticAssignerNodeEditor } from './nodeEditors/AgenticAssignerNodeEditor';
import { LogicalAssignerNodeEditor } from './nodeEditors/LogicalAssignerNodeEditor';
import { StateEditor } from './nodeEditors/StateEditor';
import { SwitchNodeEditor } from './nodeEditors/SwitchNodeEditor';

interface LeftSidebarProps {
  isGraphSelected: boolean;
  graphId: string;
}

export const LeftSidebar = ({ isGraphSelected, graphId }: LeftSidebarProps) => {
  const nodes = useNodes();
  const selectedNode = nodes.find((n) => n.selected) as AppFlowNode | undefined;

  const selectedNodeType = selectedNode?.data?.node?.node_type;
  const selectedNodeId = selectedNode?.id;

  const isSwitchActive = selectedNodeType === 'SWITCH' && !!selectedNodeId;
  const isLogicalActive = selectedNodeType === 'LOGICAL_ASSIGNER' && !!selectedNodeId;
  const isAgenticActive = selectedNodeType === 'AGENTIC_ASSIGNER' && !!selectedNodeId;

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
        {/* 1. Graph State Schema */}
        <Box style={{ flexShrink: 0 }}>
          <StateEditor graphId={graphId} disabled={!isGraphSelected} />
        </Box>

        <Separator size="4" style={{ backgroundColor: 'var(--gray-4)' }} />

        {/* 2. Switch Editor (Only active if Switch node is selected) */}
        <Box
          style={{
            flexShrink: 0,
            opacity: isSwitchActive ? 1 : 0.4,
            pointerEvents: isSwitchActive ? 'auto' : 'none',
          }}
        >
          {isSwitchActive ? (
            <SwitchNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={!isGraphSelected} />
          ) : (
            <Box
              style={{
                backgroundColor: 'var(--gray-3)',
                borderRadius: 'var(--radius-3)',
                padding: '16px',
                border: '1px border-dashed var(--gray-5)',
              }}
            >
              <Text size="2" color="gray" weight="bold">
                Switch Output Conditions
              </Text>
              <Text size="1" color="gray" style={{ display: 'block', marginTop: '4px' }}>
                Select a SWITCH node on the canvas to configure conditions.
              </Text>
            </Box>
          )}
        </Box>

        <Separator size="4" style={{ backgroundColor: 'var(--gray-4)' }} />

        {/* 3. Logical Assigner Editor (Only active if Logical Assigner node is selected) */}
        <Box
          style={{
            flexShrink: 0,
            opacity: isLogicalActive ? 1 : 0.4,
            pointerEvents: isLogicalActive ? 'auto' : 'none',
          }}
        >
          {isLogicalActive ? (
            <LogicalAssignerNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={!isGraphSelected} />
          ) : (
            <Box
              style={{
                backgroundColor: 'var(--gray-3)',
                borderRadius: 'var(--radius-3)',
                padding: '16px',
                border: '1px border-dashed var(--gray-5)',
              }}
            >
              <Text size="2" color="gray" weight="bold">
                Logical Assigner
              </Text>
              <Text size="1" color="gray" style={{ display: 'block', marginTop: '4px' }}>
                Select a LOGICAL ASSIGNER node on the canvas to configure assignments.
              </Text>
            </Box>
          )}
        </Box>

        <Separator size="4" style={{ backgroundColor: 'var(--gray-4)' }} />

        {/* 4. Agentic Assigner Editor (Only active if Agentic Assigner node is selected) */}
        <Box
          style={{
            flexShrink: 0,
            opacity: isAgenticActive ? 1 : 0.4,
            pointerEvents: isAgenticActive ? 'auto' : 'none',
          }}
        >
          {isAgenticActive ? (
            <AgenticAssignerNodeEditor graphId={graphId} nodeId={selectedNodeId} disabled={!isGraphSelected} />
          ) : (
            <Box
              style={{
                backgroundColor: 'var(--gray-3)',
                borderRadius: 'var(--radius-3)',
                padding: '16px',
                border: '1px border-dashed var(--gray-5)',
              }}
            >
              <Text size="2" color="gray" weight="bold">
                Agentic Assigner
              </Text>
              <Text size="1" color="gray" style={{ display: 'block', marginTop: '4px' }}>
                Select an AGENTIC ASSIGNER node on the canvas to configure agentic statements.
              </Text>
            </Box>
          )}
        </Box>
      </Flex>
    </Box>
  );
};
