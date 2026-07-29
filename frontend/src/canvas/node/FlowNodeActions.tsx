import { DotsHorizontalIcon } from '@radix-ui/react-icons';
import { Button, Dialog, DropdownMenu, Flex, IconButton, Text, TextField } from '@radix-ui/themes';
import { memo, useEffect, useMemo, useState } from 'react';
import { fromApiPayload } from '../../domain/graph/mappers';
import { useCurrentGraphId } from '../../hooks/graph/useCurrentGraphId';
import { useUpdateNode } from '../../hooks/graph/useGraphMutations';
import { useGraphQuery } from '../../hooks/graph/useGraphQuery';
import { FlowNodeActionsContent } from './FlowNodeActionsContent.tsx';

interface FlowNodeActionsProps {
  nodeId: string;
  triggerStyle?: React.CSSProperties;
}

export const FlowNodeActions = memo(({ nodeId, triggerStyle }: FlowNodeActionsProps) => {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [newName, setNewName] = useState(nodeId);
  const [error, setError] = useState<string | null>(null);

  const graphId = useCurrentGraphId();
  const { data } = useGraphQuery(graphId);
  const { nodes } = useMemo(() => {
    if (!data) return { nodes: [] };
    return fromApiPayload(data.nodes, []);
  }, [data]);
  const { mutateAsync: updateNode } = useUpdateNode(graphId);

  useEffect(() => {
    if (renameOpen) {
      setNewName(nodeId);
      setError(null);
    }
  }, [renameOpen, nodeId]);

  const handleRenameSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) {
      setError('Node name cannot be empty.');
      return;
    }
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(trimmed)) {
      setError('Must start with a letter/underscore and contain only letters, numbers, and underscores.');
      return;
    }
    if (trimmed !== nodeId && nodes.some(n => n.id === trimmed)) {
      setError('A node with this name already exists.');
      return;
    }

    try {
      await updateNode({ nodeId, updates: { new_id: trimmed } });
      setRenameOpen(false);
    } catch (err) {
      const message = (err && typeof err === 'object' && 'message' in err && typeof err.message === 'string')
        ? err.message
        : 'Failed to rename node.';
      setError(message);
    }
  };

  return (
    <>
      <DropdownMenu.Root modal={false} onOpenChange={setDropdownOpen}>
        <DropdownMenu.Trigger>
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            style={{ pointerEvents: 'auto', ...triggerStyle }}
          >
            <DotsHorizontalIcon/>
          </IconButton>
        </DropdownMenu.Trigger>
        <DropdownMenu.Content onCloseAutoFocus={e => e.preventDefault()}>
          {dropdownOpen && (
            <FlowNodeActionsContent
              nodeId={nodeId}
              onRenameClick={() => setRenameOpen(true)}
            />
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Root>

      <Dialog.Root open={renameOpen} onOpenChange={setRenameOpen}>
        <Dialog.Content style={{ maxWidth: 400 }} onClick={e => e.stopPropagation()}>
          <Dialog.Title>Rename Node</Dialog.Title>
          <Dialog.Description size="2" mb="4">
            Enter a new Python-valid identifier name for this node.
          </Dialog.Description>

          <form onSubmit={handleRenameSubmit}>
            <Flex direction="column" gap="3">
              <label>
                <Text as="div" size="2" mb="1" weight="bold">
                  Node Name
                </Text>
                <TextField.Root
                  value={newName}
                  onChange={(e) => {
                    setNewName(e.target.value);
                    setError(null);
                  }}
                  autoFocus
                />
              </label>

              {error && (
                <Text color="red" size="1">
                  {error}
                </Text>
              )}

              <Flex gap="3" justify="end">
                <Dialog.Close>
                  <Button variant="soft" color="gray" type="button">
                    Cancel
                  </Button>
                </Dialog.Close>
                <Button type="submit">
                  Save
                </Button>
              </Flex>
            </Flex>
          </form>
        </Dialog.Content>
      </Dialog.Root>
    </>
  );
});
