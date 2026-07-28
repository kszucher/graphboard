import { Cross2Icon, PlusIcon, TrashIcon } from '@radix-ui/react-icons';
import { Badge, Box, Button, Card, Flex, IconButton, Select, Text, TextField } from '@radix-ui/themes';
import { useCallback, useMemo, useState } from 'react';
import type { ASTExpression, DefinerVariable, LogicalAssignment } from '../canvas/types';
import {
  useCreateLogicalAssignment,
  useDeleteLogicalAssignment,
  useUpdateLogicalAssignment,
} from '../hooks/graph/useGraphMutations';
import { useGraphQuery } from '../hooks/graph/useGraphQuery';

interface LogicalAssignerEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export type LegoTokenType = 'var' | 'op' | 'val';

export interface LegoToken {
  id: string;
  type: LegoTokenType;
  varKey?: string;
  op?: '+' | '-' | '*' | '/' | '==' | '!=' | '>' | '<';
  valType?: 'number' | 'string' | 'boolean' | 'float';
  value?: any;
}

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
  const { mutateAsync: updateAsgn } = useUpdateLogicalAssignment(graphId);
  const { mutateAsync: deleteAsgn } = useDeleteLogicalAssignment(graphId);

  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const getVarType = useCallback(
    (key: string): 'boolean' | 'string' | 'number' | 'float' => {
      const v = stateVariables.find((sv) => sv.key === key);
      return v?.type || 'string';
    },
    [stateVariables]
  );

  const handleAddLine = useCallback(async () => {
    if (disabled) return;
    const defaultTarget = stateVariables[0]?.key;
    if (!defaultTarget) {
      setErrorMsg('No state variable available. Declare variables in DEFINER first.');
      return;
    }
    setErrorMsg(null);
    const varType = getVarType(defaultTarget);
    const initialAst: ASTExpression = { kind: 'stateRef', varKey: defaultTarget };

    try {
      await createAsgn({
        nodeId,
        targetVarKey: defaultTarget,
        valueType: varType,
        expression: initialAst,
      });
    } catch (e: any) {
      setErrorMsg(e?.message || 'Failed to add physical line');
    }
  }, [disabled, stateVariables, getVarType, createAsgn, nodeId]);

  const handleDelete = useCallback(
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
      <Flex direction="column" gap="2" style={{ height: '100%' }}>
        {/* Header */}
        <Flex align="center" justify="between" style={{ flexShrink: 0 }}>
          <Text size="2" weight="bold">
            Logical Assigner ({nodeId})
          </Text>
          <Badge color="purple" variant="soft" size="1">
            Grammar-Aware Expression Lines
          </Badge>
        </Flex>

        {/* Error Feedback */}
        {errorMsg && (
          <Text size="1" color="red">
            ⚠️ {errorMsg}
          </Text>
        )}

        {/* Physical Line List */}
        <Box style={{ flexGrow: 1, minHeight: 0, overflowY: 'auto' }}>
          <Flex direction="column" gap="2">
            {assignments.length === 0 && (
              <Text size="1" color="gray" style={{ fontStyle: 'italic', padding: '8px 0' }}>
                No assignment lines created yet. Click "+ Add Expression Line" below to add a line.
              </Text>
            )}

            {assignments.map((asgn) => (
              <PhysicalAssignmentLine
                key={asgn.id}
                assignment={asgn}
                stateVariables={stateVariables}
                disabled={disabled}
                onUpdate={async (updatedTarget, ast) => {
                  const vType = getVarType(updatedTarget);
                  await updateAsgn({
                    assignmentId: asgn.id,
                    targetVarKey: updatedTarget,
                    valueType: vType,
                    expression: ast,
                  });
                }}
                onDelete={() => handleDelete(asgn.id)}
              />
            ))}
          </Flex>
        </Box>

        {/* Add New Physical Line Button */}
        <Flex align="center" justify="end" style={{ flexShrink: 0, paddingTop: '4px' }}>
          <Button
            size="1"
            variant="solid"
            color="purple"
            onClick={handleAddLine}
            disabled={disabled || stateVariables.length === 0}
            style={{ cursor: disabled || stateVariables.length === 0 ? 'default' : 'pointer' }}
          >
            <PlusIcon width="14" height="14" /> Add Expression Line
          </Button>
        </Flex>
      </Flex>
    </Card>
  );
};

interface PhysicalAssignmentLineProps {
  assignment: LogicalAssignment;
  stateVariables: DefinerVariable[];
  disabled: boolean;
  onUpdate: (targetKey: string, ast: ASTExpression | null) => Promise<void>;
  onDelete: () => void;
}

function PhysicalAssignmentLine({
  assignment,
  stateVariables,
  disabled,
  onUpdate,
  onDelete,
}: PhysicalAssignmentLineProps) {
  const [targetKey, setTargetKey] = useState<string>(assignment.target_var_key);

  // Placed Static Tokens
  const [tokens, setTokens] = useState<LegoToken[]>(() => {
    const parsed = astToTokens(assignment.expression);
    if (parsed.length > 0) return parsed;
    return [{ id: `tk_${Date.now()}`, type: 'var', varKey: assignment.target_var_key }];
  });

  const [valInput, setValInput] = useState<string>('');

  // Grammatical State Check:
  // Last token type determines whether we expect an Action or an Operand (Var/Val)
  const lastToken = tokens[tokens.length - 1];
  const isExpectingAction = lastToken && (lastToken.type === 'var' || lastToken.type === 'val');
  const isExpectingOperand = !lastToken || lastToken.type === 'op';

  const syncUpdate = useCallback(
    (newTarget: string, newTokens: LegoToken[]) => {
      const ast = tokensToAst(newTokens, stateVariables[0]?.key || '');
      void onUpdate(newTarget, ast);
    },
    [onUpdate, stateVariables]
  );

  // Instant Add Variable Token
  const handleSelectVar = useCallback(
    (varToPlace: string) => {
      if (!varToPlace) return;
      const newTokens = [...tokens, { id: `tk_${Date.now()}_${Math.random()}`, type: 'var' as const, varKey: varToPlace }];
      setTokens(newTokens);
      syncUpdate(targetKey, newTokens);
    },
    [tokens, syncUpdate, targetKey]
  );

  // Instant Add Action Token
  const handleSelectOp = useCallback(
    (opToPlace: '+' | '-' | '*' | '/' | '==' | '!=' | '>' | '<') => {
      const newTokens = [...tokens, { id: `tk_${Date.now()}_${Math.random()}`, type: 'op' as const, op: opToPlace }];
      setTokens(newTokens);
      syncUpdate(targetKey, newTokens);
    },
    [tokens, syncUpdate, targetKey]
  );

  // Instant Add Value Token on Enter
  const handleAddValToken = useCallback(() => {
    if (!valInput.trim()) return;
    let parsed: any = valInput.trim();
    if (!isNaN(Number(valInput))) parsed = Number(valInput);
    if (valInput === 'true' || valInput === 'false') parsed = valInput === 'true';

    const newTokens = [
      ...tokens,
      { id: `tk_${Date.now()}_${Math.random()}`, type: 'val' as const, value: parsed },
    ];
    setTokens(newTokens);
    syncUpdate(targetKey, newTokens);
    setValInput('');
  }, [tokens, valInput, syncUpdate, targetKey]);

  const removeToken = useCallback(
    (id: string) => {
      if (tokens.length <= 1) return;
      const newTokens = tokens.filter((t) => t.id !== id);
      setTokens(newTokens);
      syncUpdate(targetKey, newTokens);
    },
    [tokens, syncUpdate, targetKey]
  );

  return (
    <Flex
      align="center"
      gap="2"
      p="2"
      style={{
        backgroundColor: 'var(--gray-3)',
        border: '1px solid var(--gray-5)',
        borderRadius: 'var(--radius-2)',
        overflowX: 'auto',
      }}
    >
      {/* Target Variable Dropdown */}
      <Box style={{ width: getAdaptiveWidth(targetKey || 'x', 1, 28), flexShrink: 0 }}>
        <Select.Root
          size="1"
          value={targetKey}
          onValueChange={(val) => {
            setTargetKey(val);
            syncUpdate(val, tokens);
          }}
          disabled={disabled}
        >
          <Select.Trigger style={{ width: '100%', fontFamily: 'monospace', fontWeight: 'bold' }} />
          <Select.Content>
            {stateVariables.map((v) => (
              <Select.Item key={v.id} value={v.key}>
                {v.key}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </Box>

      <Text size="2" weight="bold" color="purple" style={{ flexShrink: 0 }}>
        =
      </Text>

      {/* Inline Physical Expression Line (Placed Chips + Tail-End Active Controls) */}
      <Flex align="center" gap="1" style={{ flexGrow: 1, minWidth: 0, overflowX: 'auto' }}>
        {tokens.map((token) => (
          <Flex
            key={token.id}
            align="center"
            gap="1"
            style={{
              padding: '2px 6px',
              borderRadius: 'var(--radius-1)',
              backgroundColor:
                token.type === 'var'
                  ? 'var(--blue-3)'
                  : token.type === 'op'
                  ? 'var(--purple-3)'
                  : 'var(--green-3)',
              border:
                token.type === 'var'
                  ? '1px solid var(--blue-6)'
                  : token.type === 'op'
                  ? '1px solid var(--purple-6)'
                  : '1px solid var(--green-6)',
              flexShrink: 0,
            }}
          >
            <Text
              size="1"
              weight={token.type === 'op' ? 'bold' : 'regular'}
              style={{
                fontFamily: 'monospace',
                color:
                  token.type === 'var'
                    ? 'var(--blue-11)'
                    : token.type === 'op'
                    ? 'var(--purple-11)'
                    : 'var(--green-11)',
              }}
            >
              {token.type === 'var'
                ? token.varKey
                : token.type === 'op'
                ? token.op
                : String(token.value ?? '')}
            </Text>

            <IconButton
              size="1"
              variant="ghost"
              color="gray"
              onClick={() => removeToken(token.id)}
              disabled={disabled || tokens.length <= 1}
              style={{ cursor: 'pointer', padding: 0, width: '14px', height: '14px' }}
            >
              <Cross2Icon width="10" height="10" />
            </IconButton>
          </Flex>
        ))}

        {/* Tail-End Grammatically Active Adders (Renders ONLY what makes sense next!) */}
        {isExpectingAction && (
          <Box style={{ width: '110px', flexShrink: 0 }}>
            <Select.Root
              size="1"
              value=""
              onValueChange={(op: any) => {
                if (op) handleSelectOp(op);
              }}
              disabled={disabled}
            >
              <Select.Trigger placeholder="+ Action..." style={{ width: '100%', fontWeight: 'bold' }} />
              <Select.Content>
                <Select.Item value="+">+</Select.Item>
                <Select.Item value="-">-</Select.Item>
                <Select.Item value="*">*</Select.Item>
                <Select.Item value="/">/</Select.Item>
                <Select.Item value="==">==</Select.Item>
                <Select.Item value="!=">!=</Select.Item>
                <Select.Item value=">">&gt;</Select.Item>
                <Select.Item value="<">&lt;</Select.Item>
              </Select.Content>
            </Select.Root>
          </Box>
        )}

        {isExpectingOperand && (
          <Flex align="center" gap="1" style={{ flexShrink: 0 }}>
            <Box style={{ width: '120px' }}>
              <Select.Root
                size="1"
                value=""
                onValueChange={(v) => {
                  if (v) handleSelectVar(v);
                }}
                disabled={disabled || stateVariables.length === 0}
              >
                <Select.Trigger placeholder="+ Variable..." style={{ width: '100%', fontFamily: 'monospace' }} />
                <Select.Content>
                  {stateVariables.map((v) => (
                    <Select.Item key={v.id} value={v.key}>
                      {v.key}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </Box>

            <TextField.Root
              size="1"
              placeholder="+ Val..."
              value={valInput}
              onChange={(e) => setValInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAddValToken();
              }}
              disabled={disabled}
              style={{
                width: getAdaptiveWidth(valInput || 'val', 1, 16),
                fontFamily: 'monospace',
              }}
            />
          </Flex>
        )}
      </Flex>

      {/* Trash Line Button */}
      <IconButton size="1" variant="ghost" color="red" onClick={onDelete} disabled={disabled} style={{ flexShrink: 0 }}>
        <TrashIcon width="14" height="14" />
      </IconButton>
    </Flex>
  );
}

// Convert AST to Tokens Array
function astToTokens(expr: ASTExpression | null | undefined): LegoToken[] {
  if (!expr) return [];
  if (expr.kind === 'literal') {
    return [
      {
        id: `tk_${Math.random()}`,
        type: 'val',
        value: expr.value,
      },
    ];
  }
  if (expr.kind === 'stateRef') {
    return [{ id: `tk_${Math.random()}`, type: 'var', varKey: expr.varKey }];
  }
  if (expr.kind === 'binaryOp') {
    const leftToks = astToTokens(expr.left);
    const opTok: LegoToken = { id: `tk_${Math.random()}`, type: 'op', op: expr.op as any };
    const rightToks = astToTokens(expr.right);
    return [...leftToks, opTok, ...rightToks];
  }
  return [];
}

// Convert Tokens Array back to ASTExpression
function tokensToAst(tokens: LegoToken[], fallbackVarKey: string): ASTExpression | null {
  if (tokens.length === 0) return null;

  const tokenToAstNode = (t: LegoToken): ASTExpression => {
    if (t.type === 'var') {
      return { kind: 'stateRef', varKey: t.varKey || fallbackVarKey } as ASTExpression;
    }
    if (t.type === 'val') {
      let v: any = t.value;
      if (!isNaN(Number(t.value))) v = Number(t.value);
      if (String(t.value) === 'true' || String(t.value) === 'false') v = String(t.value) === 'true';
      return { kind: 'literal', value: v } as ASTExpression;
    }
    return { kind: 'literal', value: 0 } as ASTExpression;
  };

  let leftAst = tokenToAstNode(tokens[0]);

  for (let i = 1; i < tokens.length; i++) {
    const token = tokens[i];
    if (token.type === 'op') {
      const op = token.op || '+';
      const nextOperandToken = tokens[i + 1];
      const rightAst = nextOperandToken ? tokenToAstNode(nextOperandToken) : ({ kind: 'literal', value: 0 } as ASTExpression);
      leftAst = {
        kind: 'binaryOp',
        op: op as any,
        left: leftAst,
        right: rightAst,
      } as ASTExpression;
      if (nextOperandToken) i++; // Consume operand
    }
  }

  return leftAst;
}

// Adaptive width calculator for crisp, auto-hugging inline elements
function getAdaptiveWidth(text: string, minChar: number = 2, padding: number = 28): string {
  const len = Math.max((text || '').length, minChar);
  return `${len * 7.5 + padding}px`;
}
