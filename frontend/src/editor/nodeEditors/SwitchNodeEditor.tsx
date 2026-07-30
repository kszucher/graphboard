import { Badge, Box, Button, Flex, Select, Text } from '@radix-ui/themes';
import { useCallback, useMemo, useState } from 'react';
import { useUpdateSlot } from '../../api/mutations';
import type { ASTExpression } from '../../canvas/types';
import { COMPARISON_OPERATORS, formatAstToChips, } from './ExpressionEngine';
import {
  ExpressionBuilder,
  ExpressionChip,
  NodeEditorCard,
  StaticRow,
  TargetVariableChip,
  useNodeEditorData,
} from './NodeEditorShared';

interface SwitchNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export const SwitchNodeEditor = ({
  graphId,
  nodeId,
  disabled = false,
}: SwitchNodeEditorProps) => {
  const { node, stateVariables } = useNodeEditorData(graphId, nodeId);

  const slots: Array<{ id: string; raw_string: string; expression?: ASTExpression | null }> = useMemo(() => {
    return node?.slots || [];
  }, [node]);

  const { mutateAsync: updateSlotMutation } = useUpdateSlot(graphId);

  const [selectedSlotId, setSelectedSlotId] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Draft Workbench State
  const [draftStep, setDraftStep] = useState<'slot' | 'expression'>('slot');

  // Resilient active slot resolution
  const activeSlot = useMemo(() => {
    if (!slots.length) return null;
    return slots.find((s) => s.id === selectedSlotId) || slots[0];
  }, [slots, selectedSlotId]);

  const targetSlotId = activeSlot?.id || '';

  const handleResetDraft = useCallback(() => {
    setDraftStep('slot');
    setErrorMsg(null);
  }, []);

  const handleLockSlot = useCallback(() => {
    if (!targetSlotId) return;
    setDraftStep('expression');
  }, [targetSlotId]);

  const handleSaveCondition = useCallback(async (ast: ASTExpression | null) => {
    if (disabled || !targetSlotId) return;
    setErrorMsg(null);

    try {
      await updateSlotMutation({
        slotId: targetSlotId,
        rawString: activeSlot?.raw_string,
        expression: ast,
      });
      handleResetDraft();
    } catch (e: unknown) {
      setErrorMsg((e as Error)?.message || 'Failed to save slot condition.');
    }
  }, [
    disabled,
    targetSlotId,
    activeSlot,
    updateSlotMutation,
    handleResetDraft,
  ]);

  const handleClearSlotExpression = useCallback(
    async (slotId: string) => {
      if (disabled) return;
      const slot = slots.find((s) => s.id === slotId);
      try {
        await updateSlotMutation({
          slotId,
          rawString: slot?.raw_string,
          expression: null,
        });
      } catch (e: unknown) {
        setErrorMsg((e as Error)?.message || 'Failed to clear slot condition.');
      }
    },
    [disabled, slots, updateSlotMutation]
  );

  const listContent = (
    <Flex direction="column" gap="1">
      {slots.length === 0 && (
        <Text size="1" color="gray" style={{ fontStyle: 'italic', padding: '4px 0' }}>
          No output slots on this SWITCH node.
        </Text>
      )}

      {slots.map((slot, idx) => {
        const formattedChips = formatAstToChips(slot.expression, stateVariables);
        const badgeLabel = idx === 0 ? '#1 IF' : `#${idx + 1} ELIF`;
        const hasCondition = formattedChips.length > 0;

        return (
          <StaticRow
            key={slot.id}
            onDelete={hasCondition ? () => handleClearSlotExpression(slot.id) : undefined}
            disabled={disabled}
          >
            <Badge color={idx === 0 ? 'amber' : 'blue'} variant="soft" style={{ fontFamily: 'monospace' }}>
              {badgeLabel}
            </Badge>

            <TargetVariableChip varKey={slot.raw_string}/>

            <Text size="2" weight="bold" style={{ color: '#61afef' }}>
              :
            </Text>

            {hasCondition ? (
              formattedChips.map((chip, cIdx) => <ExpressionChip key={cIdx} chip={chip}/>)
            ) : (
              <Text size="1" color="gray" style={{ fontStyle: 'italic' }}>
                (unconfigured)
              </Text>
            )}
          </StaticRow>
        );
      })}
    </Flex>
  );

  const workbenchContent = (
    <Flex align="center" gap="2" style={{ overflowX: 'auto' }}>
      {/* Step 0: Target Slot Selection */}
      {draftStep === 'slot' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          <Box style={{ width: '140px' }}>
            <Select.Root
              size="1"
              value={targetSlotId}
              onValueChange={(val) => setSelectedSlotId(val)}
              disabled={disabled || slots.length === 0}
            >
              <Select.Trigger
                color="blue"
                variant="surface"
                style={{ width: '100%', fontFamily: 'monospace', fontWeight: 'bold' }}
              />
              <Select.Content color="blue">
                {slots.map((s, idx) => (
                  <Select.Item key={s.id} value={s.id}>
                    #{idx + 1} {s.raw_string}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </Box>
          <Button
            size="1"
            variant="solid"
            color="blue"
            onClick={handleLockSlot}
            disabled={disabled || !targetSlotId}
          >
            :
          </Button>
        </Flex>
      )}

      {draftStep !== 'slot' && activeSlot && (
        <>
          <TargetVariableChip varKey={activeSlot.raw_string}/>
          <Text size="2" weight="bold" style={{ color: '#61afef', flexShrink: 0 }}>
            :
          </Text>
        </>
      )}

      {/* Step 1: Expression Builder */}
      {draftStep === 'expression' && (
        <ExpressionBuilder
          stateVariables={stateVariables}
          disabled={disabled}
          allowedOperators={COMPARISON_OPERATORS}
          onSave={handleSaveCondition}
          onCancel={handleResetDraft}
        />
      )}
    </Flex>
  );

  return (
    <NodeEditorCard
      title="Switch Output Conditions"
      nodeId={nodeId}
      errorMsg={errorMsg}
      listContent={listContent}
      workbenchContent={workbenchContent}
    />
  );
};
