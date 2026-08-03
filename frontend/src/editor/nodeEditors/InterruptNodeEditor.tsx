import { Box, Checkbox, Flex, Select, Text } from '@radix-ui/themes';
import { useCallback } from 'react';
import { useUpdateNode } from '../../api/mutations';
import { NodeEditorCard, useNodeEditorData } from './NodeEditorShared';

interface InterruptNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export const InterruptNodeEditor = ({ graphId, nodeId, disabled = false }: InterruptNodeEditorProps) => {
  const { node, stateVariables } = useNodeEditorData(graphId, nodeId);
  const { mutateAsync: updateNode } = useUpdateNode(graphId);

  const payloadVars: string[] = node?.payload_vars || [];
  const resumeVar: string = node?.resume_var || '';

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

  const handleSelectResumeVar = useCallback(
    async (varKey: string) => {
      if (disabled) return;
      await updateNode({ nodeId, updates: { resume_var: varKey } });
    },
    [disabled, nodeId, updateNode]
  );

  return (
    <NodeEditorCard title="Interrupt Node Configuration" disabled={disabled}>
      <Flex direction="column" gap="4">
        {/* Resume Variable Selection */}
        <Box>
          <Text size="2" weight="bold" mb="1" style={{ display: 'block' }}>
            Resume Target Variable (Store User Payload):
          </Text>
          <Select.Root value={resumeVar} onValueChange={handleSelectResumeVar} disabled={disabled}>
            <Select.Trigger placeholder="Select variable..." style={{ width: '100%' }}/>
            <Select.Content>
              {stateVariables.map((v) => (
                <Select.Item key={v.key} value={v.key}>
                  {v.key} ({v.type})
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </Box>

        {/* Payload Variables Selection */}
        <Box>
          <Text size="2" weight="bold" mb="2" style={{ display: 'block' }}>
            Payload State Variables Sent on Interrupt:
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
