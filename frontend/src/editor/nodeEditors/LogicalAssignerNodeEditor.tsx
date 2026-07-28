import { Box, Button, Flex, Select, Text } from '@radix-ui/themes';
import { useCallback, useMemo, useState } from 'react';
import type { ASTExpression, LogicalAssignment } from '../../canvas/types';
import {
  useCreateLogicalAssignment,
  useDeleteLogicalAssignment,
} from '../../hooks/graph/useGraphMutations';
import {
  ARITHMETIC_OPERATORS,
  formatAstToChips,
} from './ExpressionEngine';
import {
  ExpressionBuilder,
  ExpressionChip,
  NodeEditorCard,
  StaticRow,
  TargetVariableChip,
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
  
  const nodeRefId = (node as unknown as { ref_id?: string })?.ref_id || `op_${nodeId}`;

  const currentOp = useMemo(() => {
    return logicalOps.find((op) => op.id === nodeRefId) || { assignments: [] };
  }, [logicalOps, nodeRefId]);

  const assignments: LogicalAssignment[] = currentOp.assignments || [];

  const { mutateAsync: createAsgn } = useCreateLogicalAssignment(graphId);
  const { mutateAsync: deleteAsgn } = useDeleteLogicalAssignment(graphId);

  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Workbench State
  const [draftStep, setDraftStep] = useState<'target' | 'expression'>('target');
  const [draftTarget, setDraftTarget] = useState<string>(stateVariables[0]?.key || '');

  const targetVarType = useMemo(() => {
    const v = stateVariables.find((sv) => sv.key === (draftTarget || stateVariables[0]?.key || ''));
    return v?.type || 'string';
  }, [draftTarget, stateVariables]);

  const handleLockTarget = useCallback(() => {
    if (!draftTarget && stateVariables[0]?.key) {
      setDraftTarget(stateVariables[0].key);
    }
    setDraftStep('expression');
  }, [draftTarget, stateVariables]);

  const handleResetDraft = useCallback(() => {
    setDraftStep('target');
    setErrorMsg(null);
  }, []);

  const handleSaveDraft = useCallback(async (ast: ASTExpression | null) => {
    if (disabled || draftStep !== 'expression') return;
    setErrorMsg(null);

    try {
      await createAsgn({
        nodeId,
        targetVarKey: draftTarget,
        valueType: targetVarType,
        expression: ast || undefined,
      });
      handleResetDraft();
    } catch (e: unknown) {
      setErrorMsg((e as Error)?.message || 'Failed to save expression');
    }
  }, [disabled, draftStep, draftTarget, targetVarType, createAsgn, nodeId, handleResetDraft]);

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
        const formattedChips = formatAstToChips(asgn.expression, stateVariables);
        const isTargetMissing = !stateVariables.some(v => v.key === asgn.target_var_key);
        return (
          <StaticRow key={asgn.id} onDelete={() => handleDeleteAssignment(asgn.id)} disabled={disabled}>
            <TargetVariableChip varKey={asgn.target_var_key} isMissing={isTargetMissing} />
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

      {/* Step 1: Expression Builder */}
      {draftStep === 'expression' && (
        <ExpressionBuilder
          stateVariables={stateVariables}
          disabled={disabled}
          allowedOperators={ARITHMETIC_OPERATORS}
          baseVarType={targetVarType}
          onSave={handleSaveDraft}
          onCancel={handleResetDraft}
        />
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
