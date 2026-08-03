import { Badge, Box, Checkbox, Flex, Text, TextField } from '@radix-ui/themes';
import { useCallback, useState } from 'react';
import { useUpdateNode, useUpdateSlot } from '../../api/mutations';
import { NodeEditorCard, StaticRow, useNodeEditorData } from './NodeEditorShared';

interface AgenticSwitchNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export const AgenticSwitchNodeEditor = ({ graphId, nodeId, disabled = false }: AgenticSwitchNodeEditorProps) => {
  const { node, stateVariables } = useNodeEditorData(graphId, nodeId);
  const { mutateAsync: updateNode } = useUpdateNode(graphId);
  const { mutateAsync: updateSlot } = useUpdateSlot(graphId);

  const agenticInputs: string[] = node?.agentic_inputs || [];
  const slots: Array<{ id: string; raw_string: string }> = node?.slots || [];

  // Local draft states for slot option labels
  const [slotDrafts, setSlotDrafts] = useState<Record<string, string>>({});

  const handleSlotBlur = useCallback(
    async (slotId: string, currentVal: string) => {
      if (disabled) return;
      const draftVal = slotDrafts[slotId];
      if (draftVal !== undefined && draftVal !== currentVal) {
        await updateSlot({ slotId, rawString: draftVal });
      }
    },
    [disabled, slotDrafts, updateSlot]
  );

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

  const optionsListStr = slots.map((s) => `'${s.raw_string}'`).join(', ');
  const variablesListStr = agenticInputs.length > 0 ? agenticInputs.map((v) => `'{${v}}'`).join(', ') : '(no state variables selected)';

  const listContent = (
    <Flex direction="column" gap="2">
      {slots.length === 0 && (
        <Text size="1" color="gray" style={{ fontStyle: 'italic', padding: '4px 0' }}>
          No output options/slots configured on this node.
        </Text>
      )}

      {slots.map((slot, idx) => {
        const val = slotDrafts[slot.id] !== undefined ? slotDrafts[slot.id] : slot.raw_string;
        const slug = val.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase() || `OPTION_${idx + 1}`;

        return (
          <StaticRow key={slot.id} disabled={disabled}>
            <Badge color="purple" variant="soft" style={{ fontFamily: 'monospace', flexShrink: 0 }}>
              OPTION #{idx + 1}
            </Badge>
            <Box style={{ flexGrow: 1 }}>
              <TextField.Root
                size="1"
                value={val}
                onChange={(e) => setSlotDrafts((prev) => ({ ...prev, [slot.id]: e.target.value }))}
                onBlur={() => handleSlotBlur(slot.id, slot.raw_string)}
                disabled={disabled}
                placeholder="Option label..."
                style={{ fontFamily: 'monospace' }}
              />
            </Box>
            <Text size="1" color="gray" style={{ fontFamily: 'monospace', flexShrink: 0 }}>
              (Enum: {slug})
            </Text>
          </StaticRow>
        );
      })}
    </Flex>
  );

  return (
    <NodeEditorCard
      title="Agentic Switch Configuration"
      nodeId={nodeId}
      disabled={disabled}
      listContent={listContent}
    >
      <Flex direction="column" gap="4">
        <Box style={{ backgroundColor: 'var(--gray-3)', padding: '10px 14px', borderRadius: 'var(--radius-2)' }}>
          <Text size="2" weight="bold" color="purple" style={{ display: 'block', marginBottom: '4px' }}>
            Auto-Assembled Classification Prompt:
          </Text>
          <Text size="1" color="gray" style={{ fontFamily: 'monospace', wordBreak: 'break-word' }}>
            "Classify input state {variablesListStr} into one of options: [{optionsListStr}]."
          </Text>
        </Box>

        {/* Input Variables Selection */}
        <Box>
          <Text size="2" weight="bold" mb="2" style={{ display: 'block' }}>
            Input State Variables to Classify:
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
