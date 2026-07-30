import { Box, Flex, Text } from '@radix-ui/themes';
import { useNodes, useReactFlow } from '@xyflow/react';
import { useCallback } from 'react';
import { useGraphCode } from '../api/queries';
import { useCodeMirror } from '../hooks/editor/useCodeMirror';

interface FullCodeEditorProps {
  graphId: string;
}

export const FullCodeEditor = ({ graphId }: FullCodeEditorProps) => {
  const { data: codeData } = useGraphCode(graphId);
  const code = codeData?.code || '';
  const { setNodes } = useReactFlow();
  const nodes = useNodes();

  const selectedNodeId = nodes.find(n => n.selected)?.id || null;

  const setSelectedNodeId = useCallback((nodeId: string | null) => {
    setNodes(nodes =>
      nodes.map(n => {
        const isSel = n.id === nodeId;
        if (n.selected !== isSel) {
          return { ...n, selected: isSel };
        }
        return n;
      })
    );
  }, [setNodes]);

  const { containerRef } = useCodeMirror({
    code,
    selectedNodeId,
    setSelectedNodeId,
  });

  return (
    <Flex direction="column" gap="3" style={{ flexGrow: 1, minHeight: 0 }}>
      {/* Read-only indicator banner */}
      <Flex align="center" justify="between" px="2" py="1" style={{ borderBottom: '1px solid var(--gray-5)' }}>
        <Text size="1" color="gray" weight="bold">GENERATED PYTHON (READ-ONLY)</Text>
      </Flex>

      {/* Editor viewport container */}
      <Box
        style={{
          flexGrow: 1,
          border: '1px solid var(--gray-6)',
          borderRadius: '4px',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        }}
      >
        <div
          ref={containerRef}
          style={{
            flexGrow: 1,
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            minHeight: 0,
          }}
        />
      </Box>
    </Flex>
  );
};
