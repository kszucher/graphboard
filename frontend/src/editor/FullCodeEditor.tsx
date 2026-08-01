import { Box } from '@radix-ui/themes';
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
    <Box
      style={{
        flexGrow: 1,
        height: '100%',
        width: '100%',
        minHeight: 0,
        overflow: 'hidden',
      }}
    >
      <div
        ref={containerRef}
        style={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          width: '100%',
          minHeight: 0,
        }}
      />
    </Box>
  );
};
