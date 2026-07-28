import { CubeIcon, Pencil1Icon, PlusIcon, ResetIcon, TrashIcon } from '@radix-ui/react-icons';
import { Box, Button, Card, Flex, IconButton, Select, Text, TextField } from '@radix-ui/themes';
import { useCallback, useState, useMemo, type ReactNode } from 'react';
import type { ASTExpression, DefinerVariable, ApiNode, OperationsContainer, DefinerOperation, LogicalOperation } from '../../canvas/types';
import { useGraphQuery } from '../../hooks/graph/useGraphQuery';
import { coerceTypedValue, getTokenStyle, TARGET_TOKEN_STYLE, tokensToAst, type DraftToken } from './ExpressionEngine';

export function ExpressionChip({
  chip,
}: {
  chip: {
    kind: 'var' | 'op' | 'val';
    valType?: 'string' | 'number' | 'boolean' | 'float';
    value?: unknown;
    varKey?: string;
    op?: string;
    label?: string;
  };
}) {
  const style = getTokenStyle(chip);
  const text =
    chip.label ??
    (chip.kind === 'var' ? chip.varKey : chip.kind === 'op' ? chip.op : String(chip.value ?? ''));

  return (
    <Box style={style}>
      <Text size="1">{text}</Text>
    </Box>
  );
}

export function TargetVariableChip({ varKey }: { varKey: string }) {
  return (
    <Box style={TARGET_TOKEN_STYLE}>
      <Text size="1">{varKey}</Text>
    </Box>
  );
}

export function TypedValueInput({
  targetVarType,
  value,
  onChange,
  disabled,
  onEnter,
}: {
  targetVarType: 'boolean' | 'string' | 'number' | 'float';
  value: string;
  onChange: (val: string) => void;
  disabled: boolean;
  onEnter?: () => void;
}) {
  if (targetVarType === 'boolean') {
    return (
      <Box style={{ width: '75px' }}>
        <Select.Root
          size="1"
          value={value === 'true' ? 'true' : 'false'}
          onValueChange={(val) => onChange(val)}
          disabled={disabled}
        >
          <Select.Trigger variant="surface" color="green" style={{ width: '100%', fontFamily: 'monospace' }} />
          <Select.Content color="green">
            <Select.Item value="true">true</Select.Item>
            <Select.Item value="false">false</Select.Item>
          </Select.Content>
        </Select.Root>
      </Box>
    );
  }

  const isNum = targetVarType === 'number' || targetVarType === 'float';

  return (
    <TextField.Root
      size="1"
      type={isNum ? 'number' : 'text'}
      placeholder={isNum ? 'number...' : 'string...'}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && onEnter) onEnter();
      }}
      disabled={disabled}
      color={isNum ? 'amber' : 'green'}
      style={{ width: '110px', fontFamily: 'monospace' }}
    />
  );
}

export function StaticRow({
  children,
  onDelete,
  disabled = false,
}: {
  children: ReactNode;
  onDelete?: () => void;
  disabled?: boolean;
}) {
  return (
    <Flex
      align="center"
      justify="between"
      p="1"
      px="2"
      style={{
        backgroundColor: 'var(--gray-3)',
        borderRadius: 'var(--radius-1)',
      }}
    >
      <Flex align="center" gap="1" style={{ flexWrap: 'wrap', overflow: 'hidden' }}>
        {children}
      </Flex>

      {onDelete && (
        <IconButton
          size="1"
          variant="ghost"
          color="red"
          onClick={onDelete}
          disabled={disabled}
          style={{ flexShrink: 0, marginLeft: '6px', cursor: disabled ? 'default' : 'pointer' }}
        >
          <TrashIcon width="12" height="12" />
        </IconButton>
      )}
    </Flex>
  );
}

const EMPTY_NODES: ApiNode[] = [];
const EMPTY_DEFINER_OPS: DefinerOperation[] = [];
const EMPTY_LOGICAL_OPS: LogicalOperation[] = [];

// eslint-disable-next-line react-refresh/only-export-components
export function useNodeEditorData(graphId: string, nodeId: string) {
  const { data: graphFlow } = useGraphQuery(graphId);
  const rawFlow = (graphFlow || {}) as { nodes?: ApiNode[]; operations?: OperationsContainer };
  const nodes = rawFlow.nodes || EMPTY_NODES;
  const definerOps = rawFlow.operations?.definer || EMPTY_DEFINER_OPS;
  const logicalOps = rawFlow.operations?.logical || EMPTY_LOGICAL_OPS;
  
  const node = useMemo(() => {
    return nodes.find((n: ApiNode) => n.id === nodeId);
  }, [nodes, nodeId]);

  const stateVariables: DefinerVariable[] = useMemo(() => {
    return definerOps.flatMap((op: DefinerOperation) => op.variables || []);
  }, [definerOps]);

  return {
    rawFlow,
    nodes,
    node,
    definerOps,
    logicalOps,
    stateVariables,
  };
}

/**
 * Shared container layout for node editors.
 */
export function NodeEditorCard({
  nodeId,
  title,
  errorMsg,
  listContent,
  workbenchContent,
}: {
  nodeId: string;
  title: string;
  errorMsg?: string | null;
  listContent: ReactNode;
  workbenchContent: ReactNode;
}) {
  return (
    <Card
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--gray-2)',
        border: '1px solid var(--gray-5)',
        borderRadius: 'var(--radius-3)',
        padding: '12px',
        boxSizing: 'border-box',
      }}
    >
      <Flex direction="column" gap="3" style={{ height: '100%' }}>
        {/* Header */}
        <Flex align="center" justify="between" style={{ flexShrink: 0 }}>
          <Text size="2" weight="bold">
            {title} ({nodeId})
          </Text>
        </Flex>

        {/* Error Feedback */}
        {errorMsg && (
          <Text size="1" color="red">
            ⚠️ {errorMsg}
          </Text>
        )}

        {/* Static List Content */}
        <Box style={{ flexGrow: 1, minHeight: 0, overflowY: 'auto' }}>
          {listContent}
        </Box>

        {/* Draft Workbench Content */}
        <Box
          style={{
            flexShrink: 0,
            backgroundColor: 'var(--gray-3)',
            borderRadius: 'var(--radius-2)',
            padding: '8px 10px',
          }}
        >
          {workbenchContent}
        </Box>
      </Flex>
    </Card>
  );
}

/**
 * Shared Expression Builder UI for drafting tokenized AST expressions.
 */
export function ExpressionBuilder({
  stateVariables,
  disabled,
  allowedOperators,
  baseVarType,
  onSave,
  onCancel,
}: {
  stateVariables: DefinerVariable[];
  disabled: boolean;
  allowedOperators: string[];
  baseVarType?: 'string' | 'number' | 'float' | 'boolean';
  onSave: (ast: ASTExpression) => void;
  onCancel: () => void;
}) {
  const [draftStep, setDraftStep] = useState<'operand_type_choice' | 'operand_input' | 'operator_or_save'>('operand_type_choice');
  const [draftTokens, setDraftTokens] = useState<DraftToken[]>([]);
  const [operandType, setOperandType] = useState<'var' | 'val' | ''>('');
  const [literalValue, setLiteralValue] = useState<string>('');

  const targetVarType = useMemo(() => {
    if (baseVarType) return baseVarType;
    const firstVar = draftTokens.find(t => t.kind === 'var');
    if (firstVar) {
      const v = stateVariables.find((sv) => sv.key === firstVar.varKey);
      return v?.type || 'string';
    }
    return 'string';
  }, [baseVarType, draftTokens, stateVariables]);

  const compatibleStateVars = useMemo(() => {
    return stateVariables.filter((v) => {
      if (targetVarType === 'number' || targetVarType === 'float') {
        return v.type === 'number' || v.type === 'float';
      }
      return v.type === targetVarType;
    });
  }, [stateVariables, targetVarType]);

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

  const handleSave = useCallback(() => {
    if (draftTokens.length === 0) return;
    const ast = tokensToAst(draftTokens, 'x'); // defaultTargetKey 'x' is safe here
    if (ast) onSave(ast);
  }, [draftTokens, onSave]);

  return (
    <>
      {draftTokens.map((t, idx) => (
        <ExpressionChip key={idx} chip={t} />
      ))}

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

      {draftStep === 'operator_or_save' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          <Box style={{ width: '85px' }}>
            <Select.Root
              size="1"
              value=""
              onValueChange={(op: string) => {
                if (op) handleAddOperator(op);
              }}
              disabled={disabled}
            >
              <Select.Trigger placeholder="Op..." color="blue" variant="surface" style={{ width: '100%', fontWeight: 'bold' }} />
              <Select.Content color="blue">
                {allowedOperators.map((op) => (
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
            onClick={handleSave}
            disabled={disabled}
            style={{ cursor: 'pointer' }}
          >
            <PlusIcon width="14" height="14" /> Save
          </Button>
        </Flex>
      )}

      <IconButton
        size="1"
        variant="ghost"
        color="gray"
        title="Reset / Cancel Draft"
        onClick={onCancel}
        disabled={disabled}
        style={{ cursor: 'pointer', flexShrink: 0, marginLeft: 'auto' }}
      >
        <ResetIcon width="12" height="12" />
      </IconButton>
    </>
  );
}

