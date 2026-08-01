import { DotsHorizontalIcon } from '@radix-ui/react-icons';
import { DropdownMenu, IconButton } from '@radix-ui/themes';
import { EdgeLabelRenderer } from '@xyflow/react';
import { useCallback } from 'react';
import { useDeleteEdge, useInsertNodeOnEdge } from '../../api/mutations';
import { useCurrentGraphId } from '../../hooks/graph/useCurrentGraphId';

import type { InsertableNodeType } from '../types';

interface FlowEdgeActionsProps {
  edgeId: string;
  labelX: number;
  labelY: number;
  source: string;
  sourceHandleId?: string | null;
}

export const FlowEdgeActions = ({
  edgeId,
  labelX,
  labelY,
  source,
  sourceHandleId,
}: FlowEdgeActionsProps) => {
  const graphId = useCurrentGraphId();
  const { mutateAsync: insertNodeOnEdge } = useInsertNodeOnEdge(graphId);
  const { mutateAsync: deleteEdge } = useDeleteEdge(graphId);

  const handleInsert = useCallback(
    (nodeType: InsertableNodeType) => {
      const handle = sourceHandleId || source;
      if (handle) {
        void insertNodeOnEdge({ sourceHandle: handle, nodeType });
      }
    },
    [insertNodeOnEdge, sourceHandleId, source]
  );

  const handleDelete = useCallback(() => {
    void deleteEdge(edgeId);
  }, [deleteEdge, edgeId]);

  return (
    <EdgeLabelRenderer>
      <div
        style={{
          position: 'absolute',
          transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          pointerEvents: 'all',
        }}
        className="nodrag nopan"
      >
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            <IconButton
              size="1"
              radius="full"
              variant="solid"
              style={{ backgroundColor: 'var(--accent-9)', color: 'var(--accent-contrast)' }}
              title="Edge actions"
              onClick={(e) => e.stopPropagation()}
            >
              <DotsHorizontalIcon width="14" height="14"/>
            </IconButton>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content>
            <DropdownMenu.Sub>
              <DropdownMenu.SubTrigger>
                Insert Node
              </DropdownMenu.SubTrigger>
              <DropdownMenu.SubContent>
                <DropdownMenu.Item onClick={() => handleInsert('LOGICAL_ASSIGNER')}>
                  Logical Assigner
                </DropdownMenu.Item>
                <DropdownMenu.Item onClick={() => handleInsert('AGENTIC_ASSIGNER')}>
                  Agentic Assigner
                </DropdownMenu.Item>
                <DropdownMenu.Item onClick={() => handleInsert('SWITCH')}>
                  Switch
                </DropdownMenu.Item>
              </DropdownMenu.SubContent>
            </DropdownMenu.Sub>

            <DropdownMenu.Separator/>

            <DropdownMenu.Item color="red" onClick={handleDelete}>
              Delete Edge
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </div>
    </EdgeLabelRenderer>
  );
};
