import { CubeIcon, Pencil1Icon, PlusIcon, ResetIcon } from '@radix-ui/react-icons';
import { Box, Button, Flex, IconButton, Select, Text } from '@radix-ui/themes';
import { useCallback, useMemo, useState } from 'react';
import type { LogicalAssignment } from '../../canvas/types';
import {
  useCreateLogicalAssignment,
  useDeleteLogicalAssignment,
} from '../../hooks/graph/useGraphMutations';
import {
  ARITHMETIC_OPERATORS,
  coerceTypedValue,
  formatAstToChips,
  tokensToAst,
  type DraftStep,
  type DraftToken,
} from './ExpressionEngine';
import {
  ExpressionChip,
  NodeEditorCard,
  StaticRow,
  TargetVariableChip,
  TypedValueInput,
  useNodeEditorData,
} from './NodeEditorShared';

interface LogicalAssignerNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export const LogicalAssignerNodeEditor = ({
  graphId,
  nodeId,
  disabled = false,
}: LogicalAssignerNodeEditorProps) => {
  const { node, logicalOps, stateVariables } = useNodeEditorData(graphId, nodeId);
  
  const nodeRefId = node?.ref_id || `op_${nodeId}`;

  const currentOp = useMemo(() => {
    return logicalOps.find((op: any) => op.id === nodeRefId) || { assignments: [] };
  }, [logicalOps, nodeRefId]);

  const assignments: LogicalAssignment[] = currentOp.assignments || [];

  const { mutateAsync: createAsgn } = useCreateLogicalAssignment(graphId);
  const { mutateAsync: deleteAsgn } = useDeleteLogicalAssignment(graphId);

  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Workbench State
  const [draftStep, setDraftStep] = useState<DraftStep>('target');
  const [draftTarget, setDraftTarget] = useState<string>(stateVariables[0]?.key || '');
  const [draftTokens, setDraftTokens] = useState<DraftToken[]>([]);
  const [operandType, setOperandType] = useState<'var' | 'val' | ''>('');
  const [literalValue, setLiteralValue] = useState<string>('');

  const targetVarType = useMemo(() => {
    const v = stateVariables.find((sv) => sv.key === (draftTarget || stateVariables[0]?.key || ''));
    return v?.type || 'string';
  }, [draftTarget, stateVariables]);

  const compatibleStateVars = useMemo(() => {
    return stateVariables.filter((v) => {
      if (targetVarType === 'number' || targetVarType === 'float') {
        return v.type === 'number' || v.type === 'float';
      }
      return v.type === targetVarType;
    });
  }, [stateVariables, targetVarType]);

  const handleLockTarget = useCallback(() => {
    if (!draftTarget && stateVariables[0]?.key) {
      setDraftTarget(stateVariables[0].key);
    }
    setDraftTokens([]);
    setOperandType('');
    setDraftStep('operand_type_choice');
  }, [draftTarget, stateVariables]);

  const handleChooseOperandType = useCallback((kind: 'var' | 'val') => {
    setOperandType(kind);
    setLiteralValue('');
    setDraftStep('operand_input');
  }, []);

  const handleSelectStateVarToken = useCallback((varKey: string) => {
    if (!varKey) return;
    setDraftTokens((prev) => [...prev, { kind: 'var', varKey }]);
    setOperandType('');
    setDraftStep('operator_or_save');
  }, []);

  const handleAddValOperand = useCallback(() => {
    const parsed = coerceTypedValue(targetVarType, literalValue);
    const valType = targetVarType === 'number' || targetVarType === 'float' ? 'number' : targetVarType === 'boolean' ? 'boolean' : 'string';
    setDraftTokens((prev) => [...prev, { kind: 'val', value: parsed, valType }]);
    setOperandType('');
    setLiteralValue('');
    setDraftStep('operator_or_save');
  }, [literalValue, targetVarType]);

  const handleAddOperator = useCallback((op: string) => {
    setDraftTokens((prev) => [...prev, { kind: 'op', op }]);
    setOperandType('');
    setDraftStep('operand_type_choice');
  }, []);

  const handleResetDraft = useCallback(() => {
    setDraftStep('target');
    setDraftTokens([]);
    setOperandType('');
    setLiteralValue('');
    setErrorMsg(null);
  }, []);

  const handleSaveDraft = useCallback(async () => {
    if (disabled || draftStep !== 'operator_or_save' || draftTokens.length === 0) return;
    setErrorMsg(null);
    const ast = tokensToAst(draftTokens, draftTarget);

    try {
      await createAsgn({
        nodeId,
        targetVarKey: draftTarget,
        valueType: targetVarType,
        expression: ast || undefined,
      });
      handleResetDraft();
    } catch (e: any) {
      setErrorMsg(e?.message || 'Failed to save expression');
    }
  }, [disabled, draftStep, draftTokens, draftTarget, targetVarType, createAsgn, nodeId, handleResetDraft]);

  const handleDeleteAssignment = useCallback(
    (assignmentId: string) => {
      if (disabled) return;
      void deleteAsgn(assignmentId);
    },
    [disabled, deleteAsgn]
  );

  const listContent = (
    <Flex direction="column" gap="1">
      {assignments.length === 0 && (
        <Text size="1" color="gray" style={{ fontStyle: 'italic', padding: '4px 0' }}>
          No saved expressions.
        </Text>
      )}

      {assignments.map((asgn) => {
        const formattedChips = formatAstToChips(asgn.expression);
        return (
          <StaticRow key={asgn.id} onDelete={() => handleDeleteAssignment(asgn.id)} disabled={disabled}>
            <TargetVariableChip varKey={asgn.target_var_key} />
            <Text size="2" weight="bold" style={{ color: '#61afef' }}>
              =
            </Text>
            {formattedChips.map((chip, idx) => (
              <ExpressionChip key={idx} chip={chip} />
            ))}
          </StaticRow>
        );
      })}
    </Flex>
  );

  const workbenchContent = (
    <Flex align="center" gap="2" style={{ overflowX: 'auto' }}>
      {draftStep !== 'target' && (
        <>
          <TargetVariableChip varKey={draftTarget || stateVariables[0]?.key || 'x'} />
          <Text size="2" weight="bold" style={{ color: '#61afef', flexShrink: 0 }}>
            =
          </Text>
        </>
      )}

      {draftTokens.map((t, idx) => (
        <ExpressionChip key={idx} chip={t} />
      ))}

      {/* Step 0: Target Select */}
      {draftStep === 'target' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          <Box style={{ width: '130px' }}>
            <Select.Root
              size="1"
              value={draftTarget || (stateVariables[0]?.key ?? '')}
              onValueChange={(val) => setDraftTarget(val)}
              disabled={disabled || stateVariables.length === 0}
            >
              <Select.Trigger
                color="red"
                variant="surface"
                style={{ width: '100%', fontFamily: 'monospace', fontWeight: 'bold' }}
              />
              <Select.Content color="red">
                {stateVariables.map((v) => (
                  <Select.Item key={v.id} value={v.key}>
                    {v.key} ({v.type})
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </Box>
          <Button
            size="1"
            variant="solid"
            color="blue"
            onClick={handleLockTarget}
            disabled={disabled || stateVariables.length === 0}
          >
            =
          </Button>
        </Flex>
      )}

      {/* Step 1: Operand Choice Icons */}
      {draftStep === 'operand_type_choice' && (
        <Flex align="center" gap="1" style={{ flexShrink: 0 }}>
          <IconButton
            size="1"
            variant="soft"
            color="red"
            title="Add State Variable"
            onClick={() => handleChooseOperandType('var')}
            disabled={disabled || compatibleStateVars.length === 0}
            style={{ cursor: 'pointer' }}
          >
            <CubeIcon width="14" height="14" />
          </IconButton>
          <IconButton
            size="1"
            variant="soft"
            color="amber"
            title={`Add ${targetVarType} Value`}
            onClick={() => handleChooseOperandType('val')}
            disabled={disabled}
            style={{ cursor: 'pointer' }}
          >
            <Pencil1Icon width="14" height="14" />
          </IconButton>
        </Flex>
      )}

      {/* Step 2: Operand Input */}
      {draftStep === 'operand_input' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          {operandType === 'var' ? (
            <Box style={{ width: '130px' }}>
              <Select.Root
                size="1"
                value=""
                onValueChange={(vk) => {
                  if (vk) handleSelectStateVarToken(vk);
                }}
                disabled={disabled || compatibleStateVars.length === 0}
              >
                <Select.Trigger
                  placeholder="Select Var..."
                  color="red"
                  variant="surface"
                  style={{ width: '100%', fontFamily: 'monospace' }}
                />
                <Select.Content color="red">
                  {compatibleStateVars.map((v) => (
                    <Select.Item key={v.id} value={v.key}>
                      {v.key}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </Box>
          ) : (
            <>
              <TypedValueInput
                targetVarType={targetVarType}
                value={literalValue}
                onChange={(val) => setLiteralValue(val)}
                disabled={disabled}
                onEnter={handleAddValOperand}
              />
              <Button
                size="1"
                variant="solid"
                color={targetVarType === 'number' || targetVarType === 'float' ? 'amber' : 'green'}
                onClick={handleAddValOperand}
                disabled={disabled}
              >
                Add
              </Button>
            </>
          )}
        </Flex>
      )}

      {/* Step 3: Operator / Save - Restricted to Arithmetic Operators (+, -, *, /) */}
      {draftStep === 'operator_or_save' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          <Box style={{ width: '85px' }}>
            <Select.Root
              size="1"
              value=""
              onValueChange={(op: any) => {
                if (op) handleAddOperator(op);
              }}
              disabled={disabled}
            >
              <Select.Trigger placeholder="+ Act..." color="blue" variant="surface" style={{ width: '100%', fontWeight: 'bold' }} />
              <Select.Content color="blue">
                {ARITHMETIC_OPERATORS.map((op) => (
                  <Select.Item key={op} value={op}>
                    {op}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </Box>

          <Button
            size="1"
            variant="solid"
            color="green"
            onClick={handleSaveDraft}
            disabled={disabled}
            style={{ cursor: 'pointer' }}
          >
            <PlusIcon width="14" height="14" /> Save
          </Button>
        </Flex>
      )}

      {/* Reset Button */}
      {draftStep !== 'target' && (
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
      title="Logical Assigner"
      nodeId={nodeId}
      errorMsg={errorMsg}
      listContent={listContent}
      workbenchContent={workbenchContent}
    />
  );
};
