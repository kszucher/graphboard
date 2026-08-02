import { Box, Checkbox, Flex, Text, TextArea } from '@radix-ui/themes';
import { useCallback, useState } from 'react';
import { useUpdateNode } from '../../api/mutations';
import { NodeEditorCard, useNodeEditorData } from './NodeEditorShared';

interface AgenticSwitchNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export const AgenticSwitchNodeEditor = ({ graphId, nodeId, disabled = false }: AgenticSwitchNodeEditorProps) => {
  const { node, stateVariables } = useNodeEditorData(graphId, nodeId);
  const { mutateAsync: updateNode } = useUpdateNode(graphId);

  const promptText = node?.prompt || '';
  const agenticInputs: string[] = node?.agentic_inputs || [];

  const [draftPrompt, setDraftPrompt] = useState(promptText);

  const handlePromptBlur = useCallback(async () => {
    if (disabled) return;
    if (draftPrompt !== promptText) {
      await updateNode({ nodeId, updates: { prompt: draftPrompt } });
    }
  }, [disabled, draftPrompt, nodeId, promptText, updateNode]);

  const handleToggleInputVar = useCallback(
    async (varKey: string, checked: boolean) => {
      if (disabled) return;
      const nextInputs = checked
        ? [...agenticInputs, varKey]
        : agenticInputs.filter((k) => k !== varKey);
      await updateNode({ nodeId, updates: { agentic_inputs: nextInputs } });
    },
    [agenticInputs, disabled, nodeId, updateNode]
  );

  return (
    <NodeEditorCard title="Agentic Switch Configuration" disabled={disabled}>
      <Flex direction="column" gap="4">
        <Box style={{ backgroundColor: 'var(--gray-3)', padding: '8px 12px', borderRadius: 'var(--radius-2)' }}>
          <Text size="1" color="gray">
            The LLM evaluates this prompt and automatically selects one of the configured slot labels.
          </Text>
        </Box>

        {/* Prompt Text */}
        <Box>
          <Text size="2" weight="bold" mb="1" style={{ display: 'block' }}>
            Routing Decision Prompt:
          </Text>
          <TextArea
            value={draftPrompt}
            onChange={(e) => setDraftPrompt(e.target.value)}
            onBlur={handlePromptBlur}
            disabled={disabled}
            placeholder="e.g. Based on customer message '{user_message}', decide if they want option_a or option_b..."
            rows={4}
          />
        </Box>

        {/* Input Variables Selection */}
        <Box>
          <Text size="2" weight="bold" mb="2" style={{ display: 'block' }}>
            Input State Variables to Interpolate in Prompt:
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
                  checked={agenticInputs.includes(v.key)}
                  onCheckedChange={(checked) => handleToggleInputVar(v.key, !!checked)}
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
