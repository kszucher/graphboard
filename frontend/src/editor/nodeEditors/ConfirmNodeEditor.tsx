import { Box, Checkbox, Flex, Text } from '@radix-ui/themes';
import { useCallback } from 'react';
import { useUpdateNode } from '../../api/mutations';
import { NodeEditorCard, useNodeEditorData } from './NodeEditorShared';

interface ConfirmNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export const ConfirmNodeEditor = ({ graphId, nodeId, disabled = false }: ConfirmNodeEditorProps) => {
  const { node, stateVariables } = useNodeEditorData(graphId, nodeId);
  const { mutateAsync: updateNode } = useUpdateNode(graphId);

  const payloadVars: string[] = node?.payload_vars || [];

  const handleTogglePayloadVar = useCallback(
    async (varKey: string, checked: boolean) => {
      if (disabled) return;
      const nextVars = checked
        ? [...payloadVars, varKey]
        : payloadVars.filter((k) => k !== varKey);
      await updateNode({ nodeId, updates: { payload_vars: nextVars } });
    },
    [disabled, nodeId, payloadVars, updateNode]
  );

  return (
    <NodeEditorCard title="Confirm Node Configuration" disabled={disabled}>
      <Flex direction="column" gap="4">
        {/* Info */}
        <Box style={{ backgroundColor: 'var(--gray-3)', padding: '8px 12px', borderRadius: 'var(--radius-2)' }}>
          <Text size="1" color="gray">
            This node interrupts execution, presents confirmation context to the user, and routes to:
            <Text weight="bold"> confirmed</Text>, <Text weight="bold">rejected</Text>, or <Text weight="bold">unclear</Text>.
          </Text>
        </Box>

        {/* Payload Variables Selection */}
        <Box>
          <Text size="2" weight="bold" mb="2" style={{ display: 'block' }}>
            Payload State Variables Sent for Confirmation:
          </Text>
          <Flex direction="column" gap="2">
            {stateVariables.length === 0 && (
              <Text size="1" color="gray" style={{ fontStyle: 'italic' }}>
                No state variables defined in graph schema.
              </Text>
            )}
            {stateVariables.map((v) => (
              <Text as="label" size="2" key={v.key} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Checkbox
                  checked={payloadVars.includes(v.key)}
                  onCheckedChange={(checked) => handleTogglePayloadVar(v.key, !!checked)}
                  disabled={disabled}
                />
                {v.key} <Text color="gray" size="1">({v.type})</Text>
              </Text>
            ))}
          </Flex>
        </Box>
      </Flex>
    </NodeEditorCard>
  );
};
