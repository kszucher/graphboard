import { Box, Flex, Text, TextField } from '@radix-ui/themes';
import { useCallback, useMemo, useState } from 'react';
import { useUpdateNode } from '../../api/mutations';
import type { ASTExpression } from '../../canvas/types';
import { COMPARISON_OPERATORS, formatAstToChips } from './ExpressionEngine';
import { ExpressionBuilder, ExpressionChip, NodeEditorCard, useNodeEditorData } from './NodeEditorShared';

interface RetryNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export const RetryNodeEditor = ({ graphId, nodeId, disabled = false }: RetryNodeEditorProps) => {
  const { node, stateVariables } = useNodeEditorData(graphId, nodeId);
  const { mutateAsync: updateNode } = useUpdateNode(graphId);

  const maxAttempts = node?.max_attempts ?? 3;
  const validExpression: ASTExpression | null = (node?.valid_expression as ASTExpression) || null;

  const [attemptsValue, setAttemptsValue] = useState<string>(String(maxAttempts));

  const handleAttemptsBlur = useCallback(async () => {
    if (disabled) return;
    const parsed = parseInt(attemptsValue, 10);
    if (!isNaN(parsed) && parsed > 0 && parsed !== maxAttempts) {
      await updateNode({ nodeId, updates: { max_attempts: parsed } });
    } else {
      setAttemptsValue(String(maxAttempts));
    }
  }, [attemptsValue, disabled, maxAttempts, nodeId, updateNode]);

  const handleSaveValidExpression = useCallback(
    async (ast: ASTExpression) => {
      if (disabled) return;
      await updateNode({ nodeId, updates: { valid_expression: ast } });
    },
    [disabled, nodeId, updateNode]
  );

  const chips = useMemo(() => {
    return formatAstToChips(validExpression, stateVariables);
  }, [validExpression, stateVariables]);

  return (
    <NodeEditorCard title="Retry Node Configuration" disabled={disabled}>
      <Flex direction="column" gap="4">
        {/* Info */}
        <Box style={{ backgroundColor: 'var(--gray-3)', padding: '8px 12px', borderRadius: 'var(--radius-2)' }}>
          <Text size="1" color="gray">
            If the condition below is valid, routes to <Text weight="bold">valid</Text>. If invalid and count &lt; max attempts, routes to <Text weight="bold">retry</Text>. Otherwise routes to <Text weight="bold">exhausted</Text>.
          </Text>
        </Box>

        {/* Max Attempts Input */}
        <Box>
          <Text size="2" weight="bold" mb="1" style={{ display: 'block' }}>
            Maximum Retry Attempts:
          </Text>
          <TextField.Root
            type="number"
            value={attemptsValue}
            onChange={(e) => setAttemptsValue(e.target.value)}
            onBlur={handleAttemptsBlur}
            disabled={disabled}
            style={{ width: '120px' }}
          />
        </Box>

        {/* Valid Expression Builder */}
        <Box>
          <Text size="2" weight="bold" mb="2" style={{ display: 'block' }}>
            Valid Condition Expression:
          </Text>
          {chips.length > 0 && (
            <Flex gap="1" wrap="wrap" mb="2">
              {chips.map((c, i) => (
                <ExpressionChip key={i} chip={c} />
              ))}
            </Flex>
          )}
          <ExpressionBuilder
            stateVariables={stateVariables}
            allowedOperators={COMPARISON_OPERATORS}
            baseVarType="boolean"
            onSave={handleSaveValidExpression}
            onCancel={() => {}}
            disabled={disabled}
          />
        </Box>
      </Flex>
    </NodeEditorCard>
  );
};
