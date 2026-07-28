import { CubeIcon, Pencil1Icon, PlusIcon, ResetIcon, TrashIcon } from '@radix-ui/react-icons';
import { Box, Button, Card, Flex, IconButton, Select, Text, TextField } from '@radix-ui/themes';
import { useCallback, useMemo, useState } from 'react';
import type { ASTExpression, DefinerVariable, LogicalAssignment } from '../canvas/types';
import {
  useCreateLogicalAssignment,
  useDeleteLogicalAssignment,
} from '../hooks/graph/useGraphMutations';
import { useGraphQuery } from '../hooks/graph/useGraphQuery';

interface LogicalAssignerEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export type DraftStep = 'target' | 'operand_type_choice' | 'operand_input' | 'operator_or_save';

export type DraftToken =
  | { kind: 'var'; varKey: string }
  | { kind: 'val'; value: any; valType?: 'string' | 'number' | 'boolean' }
  | { kind: 'op'; op: '+' | '-' | '*' | '/' | '==' | '!=' | '>' | '<' };

// Outlined Token Styling Helper matching CodeMirror Syntax Theme
function getTokenStyle(chip: { kind: 'var' | 'op' | 'val'; valType?: 'string' | 'number' | 'boolean'; value?: any }) {
  const common = {
    backgroundColor: 'transparent',
    color: '#ffffff',
    fontWeight: '600',
    borderRadius: '12px',
    padding: '2px 10px',
    fontSize: '12px',
    lineHeight: '16px',
    fontFamily: 'monospace',
    flexShrink: 0,
  };

  if (chip.kind === 'var') {
    return { ...common, border: '1.5px solid #e06c75' };
  }
  if (chip.kind === 'op') {
    return { ...common, border: '1.5px solid #61afef' };
  }
  const v = chip.value;
  if (typeof v === 'number' || chip.valType === 'number') {
    return { ...common, border: '1.5px solid #e5a95d' };
  }
  return { ...common, border: '1.5px solid #98c379' };
}

const TARGET_TOKEN_STYLE = {
  backgroundColor: 'transparent',
  border: '1.5px solid #e06c75',
  color: '#ffffff',
  fontWeight: '600',
  fontFamily: 'monospace',
  padding: '2px 10px',
  borderRadius: '12px',
  fontSize: '12px',
  flexShrink: 0,
};

export const LogicalAssignerEditor = ({
  graphId,
  nodeId,
  disabled = false,
}: LogicalAssignerEditorProps) => {
  const { data: graphFlow } = useGraphQuery(graphId);
  const rawFlow = (graphFlow || {}) as Record<string, any>;
  const definerOps = rawFlow.operations?.definer || [];
  const logicalOps = rawFlow.operations?.logical || [];

  const nodeRefId = useMemo(() => {
    const nodes = rawFlow.nodes || [];
    const n = nodes.find((nd: any) => nd.id === nodeId);
    return n?.ref_id || `op_${nodeId}`;
  }, [rawFlow.nodes, nodeId]);

  const stateVariables: DefinerVariable[] = useMemo(() => {
    return definerOps.flatMap((op: any) => op.variables || []);
  }, [definerOps]);

  const currentOp = useMemo(() => {
    return logicalOps.find((op: any) => op.id === nodeRefId) || { assignments: [] };
  }, [logicalOps, nodeRefId]);

  const assignments: LogicalAssignment[] = currentOp.assignments || [];

  const { mutateAsync: createAsgn } = useCreateLogicalAssignment(graphId);
  const { mutateAsync: deleteAsgn } = useDeleteLogicalAssignment(graphId);

  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Strict Left-to-Right Workbench State
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

  const compatibleOperators = useMemo(() => {
    if (targetVarType === 'number' || targetVarType === 'float') {
      return ['+', '-', '*', '/', '==', '!=', '>', '<'];
    }
    return ['+', '==', '!='];
  }, [targetVarType]);

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
    let parsed: any = literalValue;
    let valType: 'string' | 'number' | 'boolean' = 'string';
    if (targetVarType === 'number' || targetVarType === 'float') {
      parsed = parseInt(literalValue || '0', 10) || 0;
      valType = 'number';
    } else if (targetVarType === 'boolean') {
      parsed = literalValue === 'true';
      valType = 'boolean';
    }
    setDraftTokens((prev) => [...prev, { kind: 'val', value: parsed, valType }]);
    setOperandType('');
    setLiteralValue('');
    setDraftStep('operator_or_save');
  }, [literalValue, targetVarType]);

  const handleAddOperator = useCallback((op: '+' | '-' | '*' | '/' | '==' | '!=' | '>' | '<') => {
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
            Logical Assigner ({nodeId})
          </Text>
        </Flex>

        {/* Error Feedback */}
        {errorMsg && (
          <Text size="1" color="red">
            ⚠️ {errorMsg}
          </Text>
        )}

        {/* Saved Assignments List */}
        <Box style={{ flexGrow: 1, minHeight: 0, overflowY: 'auto' }}>
          <Flex direction="column" gap="1">
            {assignments.length === 0 && (
              <Text size="1" color="gray" style={{ fontStyle: 'italic', padding: '4px 0' }}>
                No saved expressions.
              </Text>
            )}

            {assignments.map((asgn) => (
              <StaticAssignmentRow
                key={asgn.id}
                assignment={asgn}
                onDelete={() => handleDeleteAssignment(asgn.id)}
                disabled={disabled}
              />
            ))}
          </Flex>
        </Box>

        {/* Single Line Continuous Draft Workbench */}
        <Box
          style={{
            flexShrink: 0,
            backgroundColor: 'var(--gray-3)',
            borderRadius: 'var(--radius-2)',
            padding: '8px 10px',
          }}
        >
          <Flex align="center" gap="2" style={{ overflowX: 'auto' }}>
            {/* Draft Expression Chips */}
            {draftStep !== 'target' && (
              <>
                <Box style={TARGET_TOKEN_STYLE}>
                  <Text size="1">{draftTarget || stateVariables[0]?.key || 'x'}</Text>
                </Box>
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

            {/* Step 3: Operator / Save */}
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
                      {compatibleOperators.map((op) => (
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
        </Box>
      </Flex>
    </Card>
  );
};

function ExpressionChip({
  chip,
}: {
  chip: {
    kind: 'var' | 'op' | 'val';
    valType?: 'string' | 'number' | 'boolean';
    value?: any;
    varKey?: string;
    op?: string;
    label?: string;
  };
}) {
  const style = getTokenStyle(chip);
  const text = chip.label ?? (chip.kind === 'var' ? chip.varKey : chip.kind === 'op' ? chip.op : String(chip.value ?? ''));
  return (
    <Box style={style}>
      <Text size="1">{text}</Text>
    </Box>
  );
}

function TypedValueInput({
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
      placeholder={isNum ? 'enter number...' : 'enter string...'}
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

function StaticAssignmentRow({
  assignment,
  onDelete,
  disabled,
}: {
  assignment: LogicalAssignment;
  onDelete: () => void;
  disabled: boolean;
}) {
  const formattedChips = formatAstToStaticChips(assignment.expression);

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
        <Box style={TARGET_TOKEN_STYLE}>
          <Text size="1">{assignment.target_var_key}</Text>
        </Box>
        <Text size="2" weight="bold" style={{ color: '#61afef' }}>
          =
        </Text>

        {formattedChips.map((chip, idx) => (
          <ExpressionChip key={idx} chip={chip} />
        ))}
      </Flex>

      <IconButton
        size="1"
        variant="ghost"
        color="red"
        onClick={onDelete}
        disabled={disabled}
        style={{ flexShrink: 0, marginLeft: '6px' }}
      >
        <TrashIcon width="12" height="12" />
      </IconButton>
    </Flex>
  );
}

function formatAstToStaticChips(
  expr: ASTExpression | null | undefined
): { kind: 'var' | 'op' | 'val'; label: string; value?: any }[] {
  if (!expr) return [];
  if (expr.kind === 'literal') {
    return [{ kind: 'val', label: String(expr.value ?? 0), value: expr.value }];
  }
  if (expr.kind === 'stateRef') {
    return [{ kind: 'var', label: expr.varKey }];
  }
  if (expr.kind === 'binaryOp') {
    const left = formatAstToStaticChips(expr.left);
    const opChip = { kind: 'op' as const, label: expr.op };
    const right = formatAstToStaticChips(expr.right);
    return [...left, opChip, ...right];
  }
  return [];
}

function tokensToAst(tokens: DraftToken[], targetKey: string): ASTExpression | null {
  if (tokens.length === 0) return null;

  const tokenToAstNode = (t: DraftToken): ASTExpression => {
    if (t.kind === 'var') {
      return { kind: 'stateRef', varKey: t.varKey || targetKey } as ASTExpression;
    }
    if (t.kind === 'val') {
      return { kind: 'literal', value: t.value } as ASTExpression;
    }
    return { kind: 'literal', value: 0 } as ASTExpression;
  };

  let leftAst = tokenToAstNode(tokens[0]);

  for (let i = 1; i < tokens.length; i++) {
    const token = tokens[i];
    if (token.kind === 'op') {
      const op = token.op;
      const nextOperandToken = tokens[i + 1];
      const rightAst = nextOperandToken ? tokenToAstNode(nextOperandToken) : ({ kind: 'literal', value: 0 } as ASTExpression);
      leftAst = {
        kind: 'binaryOp',
        op: op as any,
        left: leftAst,
        right: rightAst,
      } as ASTExpression;
      if (nextOperandToken) i++;
    }
  }

  return leftAst;
}
