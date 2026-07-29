import { Box, Card, Flex, Text } from '@radix-ui/themes';
import { useNodes, useReactFlow } from '@xyflow/react';
import { useCallback } from 'react';
import type { Diagnostic } from '../canvas/types';
import { useCodeMirror } from '../hooks/editor/useCodeMirror';
import { useGraphQuery } from '../hooks/graph/useGraphQuery';

interface FullCodeEditorProps {
  graphId: string;
}

export const FullCodeEditor = ({ graphId }: FullCodeEditorProps) => {
  const { data: graphFlow } = useGraphQuery(graphId);
  const rawFlow = (graphFlow || {}) as {
    diagnostics?: Diagnostic[];
    code?: string;
  };

  const diagnostics: Diagnostic[] = rawFlow.diagnostics || [];

  const code = rawFlow.code || '';
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
    diagnostics,
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

      {/* Diagnostics summary if errors exist */}
      {diagnostics.length > 0 && (
        <Card
          style={{
            padding: '8px',
            backgroundColor: 'var(--red-a2)',
            border: '1px solid var(--red-6)',
            maxHeight: '120px',
            overflowY: 'auto',
          }}
        >
          <Flex direction="column" gap="1">
            <Text size="1" color="red" weight="bold">⚠️ Diagnostics ({diagnostics.length}):</Text>
            {diagnostics.map((d: Diagnostic, i: number) => (
              <Text key={i} size="1" color="red" style={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                [{d.code}] Line {d.line}:{d.column} - {d.message}
              </Text>
            ))}
          </Flex>
        </Card>
      )}
    </Flex>
  );
};
