import { CubeIcon, Pencil1Icon, PlusIcon, ResetIcon } from '@radix-ui/react-icons';
import { Badge, Box, Button, Flex, IconButton, Select, Text } from '@radix-ui/themes';
import { useCallback, useMemo, useState } from 'react';
import { useUpdateSlot } from '../../hooks/graph/useGraphMutations';
import {
  COMPARISON_OPERATORS,
  coerceTypedValue,
  formatAstToChips,
} from './ExpressionEngine';
import {
  ExpressionChip,
  NodeEditorCard,
  StaticRow,
  TargetVariableChip,
  TypedValueInput,
  useNodeEditorData,
} from './NodeEditorShared';

interface SwitchNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export type SwitchDraftStep =
  | 'slot'
  | 'lhs_type'
  | 'lhs_input'
  | 'operator'
  | 'rhs_type'
  | 'rhs_input_and_save';

export const SwitchNodeEditor = ({
  graphId,
  nodeId,
  disabled = false,
}: SwitchNodeEditorProps) => {
  const { node, stateVariables } = useNodeEditorData(graphId, nodeId);

  const slots: Array<{ id: string; raw_string: string; expression?: any }> = useMemo(() => {
    return node?.slots || [];
  }, [node]);

  const { mutateAsync: updateSlotMutation } = useUpdateSlot(graphId);

  const [selectedSlotId, setSelectedSlotId] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Draft Workbench State
  const [draftStep, setDraftStep] = useState<SwitchDraftStep>('slot');
  const [lhsType, setLhsType] = useState<'var' | 'val'>('var');
  const [lhsVarKey, setLhsVarKey] = useState<string>('');
  const [lhsLiteral, setLhsLiteral] = useState<string>('');
  const [selectedOp, setSelectedOp] = useState<string>('==');
  const [rhsType, setRhsType] = useState<'var' | 'val'>('val');
  const [rhsVarKey, setRhsVarKey] = useState<string>('');
  const [rhsLiteral, setRhsLiteral] = useState<string>('');

  // Resilient active slot resolution
  const activeSlot = useMemo(() => {
    if (!slots.length) return null;
    return slots.find((s) => s.id === selectedSlotId) || slots[0];
  }, [slots, selectedSlotId]);

  const targetSlotId = activeSlot?.id || '';

  // Inferred LHS variable type for cross-operand coercion
  const lhsVarType = useMemo(() => {
    if (lhsType === 'var') {
      const v = stateVariables.find((sv) => sv.key === lhsVarKey);
      return v?.type || 'string';
    }
    return 'string';
  }, [lhsType, lhsVarKey, stateVariables]);

  const compatibleRhsStateVars = useMemo(() => {
    return stateVariables.filter((v) => {
      if (lhsVarType === 'number' || lhsVarType === 'float') {
        return v.type === 'number' || v.type === 'float';
      }
      return v.type === lhsVarType;
    });
  }, [stateVariables, lhsVarType]);

  const handleResetDraft = useCallback(() => {
    setDraftStep('slot');
    setLhsType('var');
    setLhsVarKey('');
    setLhsLiteral('');
    setSelectedOp('==');
    setRhsType('val');
    setRhsVarKey('');
    setRhsLiteral('');
    setErrorMsg(null);
  }, []);

  const handleLockSlot = useCallback(() => {
    if (!targetSlotId) return;
    setDraftStep('lhs_type');
  }, [targetSlotId]);

  const handleChooseLhsType = useCallback((kind: 'var' | 'val') => {
    setLhsType(kind);
    setLhsVarKey(stateVariables[0]?.key || '');
    setLhsLiteral('');
    setDraftStep('lhs_input');
  }, [stateVariables]);

  const handleConfirmLhs = useCallback(() => {
    setDraftStep('operator');
  }, []);

  const handleChooseOp = useCallback((op: string) => {
    setSelectedOp(op);
    setDraftStep('rhs_type');
  }, []);

  const handleChooseRhsType = useCallback((kind: 'var' | 'val') => {
    setRhsType(kind);
    setRhsVarKey(compatibleRhsStateVars[0]?.key || '');
    setRhsLiteral('');
    setDraftStep('rhs_input_and_save');
  }, [compatibleRhsStateVars]);

  const handleSaveCondition = useCallback(async () => {
    if (disabled || !targetSlotId) return;
    setErrorMsg(null);

    const lhsAst =
      lhsType === 'var'
        ? { kind: 'stateRef', varKey: lhsVarKey || stateVariables[0]?.key || 'x' }
        : { kind: 'literal', value: coerceTypedValue('string', lhsLiteral) };

    const rhsAst =
      rhsType === 'var'
        ? { kind: 'stateRef', varKey: rhsVarKey || compatibleRhsStateVars[0]?.key || 'x' }
        : { kind: 'literal', value: coerceTypedValue(lhsVarType, rhsLiteral) };

    const expression = {
      kind: 'binaryOp',
      op: selectedOp,
      left: lhsAst,
      right: rhsAst,
    };

    try {
      await updateSlotMutation({
        slotId: targetSlotId,
        rawString: activeSlot?.raw_string,
        expression,
      });
      handleResetDraft();
    } catch (e: any) {
      setErrorMsg(e?.message || 'Failed to save slot condition.');
    }
  }, [
    disabled,
    targetSlotId,
    activeSlot,
    lhsType,
    lhsVarKey,
    lhsLiteral,
    rhsType,
    rhsVarKey,
    rhsLiteral,
    lhsVarType,
    selectedOp,
    stateVariables,
    compatibleRhsStateVars,
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
          expression: {},
        });
      } catch (e: any) {
        setErrorMsg(e?.message || 'Failed to clear slot condition.');
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
        const formattedChips = formatAstToChips(slot.expression);
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

            <TargetVariableChip varKey={slot.raw_string} />

            <Text size="2" weight="bold" style={{ color: '#61afef' }}>
              :
            </Text>

            {hasCondition ? (
              formattedChips.map((chip, cIdx) => <ExpressionChip key={cIdx} chip={chip} />)
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
          <TargetVariableChip varKey={activeSlot.raw_string} />
          <Text size="2" weight="bold" style={{ color: '#61afef', flexShrink: 0 }}>
            :
          </Text>
        </>
      )}

      {/* Step 1: LHS Operand Type Choice */}
      {draftStep === 'lhs_type' && (
        <Flex align="center" gap="1" style={{ flexShrink: 0 }}>
          <IconButton
            size="1"
            variant="soft"
            color="red"
            title="LHS State Variable"
            onClick={() => handleChooseLhsType('var')}
            disabled={disabled || stateVariables.length === 0}
            style={{ cursor: 'pointer' }}
          >
            <CubeIcon width="14" height="14" />
          </IconButton>
          <IconButton
            size="1"
            variant="soft"
            color="amber"
            title="LHS Value"
            onClick={() => handleChooseLhsType('val')}
            disabled={disabled}
            style={{ cursor: 'pointer' }}
          >
            <Pencil1Icon width="14" height="14" />
          </IconButton>
        </Flex>
      )}

      {/* Step 2: LHS Input */}
      {draftStep === 'lhs_input' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          {lhsType === 'var' ? (
            <Box style={{ width: '120px' }}>
              <Select.Root
                size="1"
                value={lhsVarKey || (stateVariables[0]?.key ?? '')}
                onValueChange={(vk) => setLhsVarKey(vk)}
                disabled={disabled}
              >
                <Select.Trigger color="red" variant="surface" style={{ width: '100%', fontFamily: 'monospace' }} />
                <Select.Content color="red">
                  {stateVariables.map((v) => (
                    <Select.Item key={v.id} value={v.key}>
                      {v.key}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </Box>
          ) : (
            <TypedValueInput
              targetVarType="string"
              value={lhsLiteral}
              onChange={(val) => setLhsLiteral(val)}
              disabled={disabled}
              onEnter={handleConfirmLhs}
            />
          )}
          <Button size="1" variant="solid" color="blue" onClick={handleConfirmLhs} disabled={disabled}>
            Next
          </Button>
        </Flex>
      )}

      {/* Render LHS Chip preview after step 2 */}
      {['operator', 'rhs_type', 'rhs_input_and_save'].includes(draftStep) && (
        <ExpressionChip
          chip={
            lhsType === 'var'
              ? { kind: 'var', varKey: lhsVarKey || stateVariables[0]?.key || 'x' }
              : { kind: 'val', value: lhsLiteral }
          }
        />
      )}

      {/* Step 3: Comparison Operator Selection */}
      {draftStep === 'operator' && (
        <Box style={{ width: '85px', flexShrink: 0 }}>
          <Select.Root
            size="1"
            value=""
            onValueChange={(op: any) => {
              if (op) handleChooseOp(op);
            }}
            disabled={disabled}
          >
            <Select.Trigger placeholder="cmp..." color="blue" variant="surface" style={{ width: '100%', fontWeight: 'bold' }} />
            <Select.Content color="blue">
              {COMPARISON_OPERATORS.map((op) => (
                <Select.Item key={op} value={op}>
                  {op}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </Box>
      )}

      {/* Render Operator Chip preview after step 3 */}
      {['rhs_type', 'rhs_input_and_save'].includes(draftStep) && (
        <ExpressionChip chip={{ kind: 'op', op: selectedOp }} />
      )}

      {/* Step 4: RHS Operand Type Choice */}
      {draftStep === 'rhs_type' && (
        <Flex align="center" gap="1" style={{ flexShrink: 0 }}>
          <IconButton
            size="1"
            variant="soft"
            color="red"
            title="RHS State Variable"
            onClick={() => handleChooseRhsType('var')}
            disabled={disabled || compatibleRhsStateVars.length === 0}
            style={{ cursor: 'pointer' }}
          >
            <CubeIcon width="14" height="14" />
          </IconButton>
          <IconButton
            size="1"
            variant="soft"
            color="amber"
            title={`RHS ${lhsVarType} Value`}
            onClick={() => handleChooseRhsType('val')}
            disabled={disabled}
            style={{ cursor: 'pointer' }}
          >
            <Pencil1Icon width="14" height="14" />
          </IconButton>
        </Flex>
      )}

      {/* Step 5: RHS Input & Save */}
      {draftStep === 'rhs_input_and_save' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          {rhsType === 'var' ? (
            <Box style={{ width: '120px' }}>
              <Select.Root
                size="1"
                value={rhsVarKey || (compatibleRhsStateVars[0]?.key ?? '')}
                onValueChange={(vk) => setRhsVarKey(vk)}
                disabled={disabled}
              >
                <Select.Trigger color="red" variant="surface" style={{ width: '100%', fontFamily: 'monospace' }} />
                <Select.Content color="red">
                  {compatibleRhsStateVars.map((v) => (
                    <Select.Item key={v.id} value={v.key}>
                      {v.key}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </Box>
          ) : (
            <TypedValueInput
              targetVarType={lhsVarType}
              value={rhsLiteral}
              onChange={(val) => setRhsLiteral(val)}
              disabled={disabled}
              onEnter={handleSaveCondition}
            />
          )}
          <Button
            size="1"
            variant="solid"
            color="green"
            onClick={handleSaveCondition}
            disabled={disabled}
            style={{ cursor: 'pointer' }}
          >
            <PlusIcon width="14" height="14" /> Save
          </Button>
        </Flex>
      )}

      {/* Revert / Cancel Button */}
      {draftStep !== 'slot' && (
        <IconButton
          size="1"
          variant="ghost"
          color="gray"
          title="Reset / Cancel Draft"
          onClick={handleResetDraft}
          disabled={disabled}
          style={{ cursor: 'pointer', flexShrink: 0, marginLeft: 'auto' }}
        >
          <ResetIcon width="12" height="12" />
        </IconButton>
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
