import { PlusIcon, TrashIcon } from '@radix-ui/react-icons';
import { Badge, Box, Button, Card, Flex, IconButton, Select, Text, TextField } from '@radix-ui/themes';
import { useCallback, useMemo, useState } from 'react';
import type { DefinerVariable } from '../canvas/types';
import {
  useCreateDefinerVariable,
  useDeleteDefinerVariable,
  useUpdateDefinerVariable,
} from '../hooks/graph/useGraphMutations';
import { useGraphQuery } from '../hooks/graph/useGraphQuery';

const PYTHON_KEYWORDS = new Set([
  'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
  'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import',
  'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
]);

interface DefinerVariableEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export const DefinerVariableEditor = ({
  graphId,
  nodeId,
  disabled = false,
}: DefinerVariableEditorProps) => {
  const { data: graphFlow } = useGraphQuery(graphId);
  const rawFlow = (graphFlow || {}) as Record<string, any>;
  const definerOps = rawFlow.operations?.definer || [];

  const nodeRefId = useMemo(() => {
    const nodes = rawFlow.nodes || [];
    const n = nodes.find((nd: any) => nd.id === nodeId);
    return n?.ref_id || 'op_def_main';
  }, [rawFlow.nodes, nodeId]);

  const currentOp = useMemo(() => {
    return definerOps.find((op: any) => op.id === nodeRefId) || definerOps[0] || { variables: [] };
  }, [definerOps, nodeRefId]);

  const variables: DefinerVariable[] = currentOp.variables || [];

  const allVariableKeys = useMemo(() => {
    const set = new Set<string>();
    for (const op of definerOps) {
      for (const v of op.variables || []) {
        set.add(v.key);
      }
    }
    return set;
  }, [definerOps]);

  const { mutateAsync: createVar } = useCreateDefinerVariable(graphId);
  const { mutateAsync: updateVar } = useUpdateDefinerVariable(graphId);
  const { mutateAsync: deleteVar } = useDeleteDefinerVariable(graphId);

  const [draftKey, setDraftKey] = useState('');
  const [draftType, setDraftType] = useState<'boolean' | 'string' | 'number' | 'float'>('string');
  const [draftDefault, setDraftDefault] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const validateKey = useCallback((key: string): string | null => {
    const trimmed = key.trim();
    if (!trimmed) return 'Variable name cannot be empty.';
    if (!/^[a-z_][a-z0-9_]*$/.test(trimmed)) {
      return 'Must be valid snake_case (lowercase letters, numbers, underscores).';
    }
    if (PYTHON_KEYWORDS.has(trimmed)) {
      return `'${trimmed}' is a Python reserved keyword.`;
    }
    if (allVariableKeys.has(trimmed)) {
      return `Variable '${trimmed}' already exists in graph state schema.`;
    }
    return null;
  }, [allVariableKeys]);

  const handleAdd = useCallback(async () => {
    if (disabled) return;
    const err = validateKey(draftKey);
    if (err) {
      setErrorMsg(err);
      return;
    }

    setErrorMsg(null);
    let parsedDefault: any = draftDefault;
    if (draftType === 'number') parsedDefault = parseInt(draftDefault, 10) || 0;
    if (draftType === 'float') parsedDefault = parseFloat(draftDefault) || 0.0;
    if (draftType === 'boolean') parsedDefault = draftDefault === 'true';

    try {
      await createVar({
        nodeId,
        key: draftKey.trim(),
        type: draftType,
        defaultValue: parsedDefault,
      });
      setDraftKey('');
      setDraftDefault('');
    } catch (e: any) {
      setErrorMsg(e?.message || 'Failed to create variable');
    }
  }, [disabled, validateKey, draftKey, draftType, draftDefault, createVar, nodeId]);

  const handleUpdateType = useCallback(
    (varId: string, type: 'boolean' | 'string' | 'number' | 'float') => {
      if (disabled) return;
      void updateVar({ varId, type });
    },
    [disabled, updateVar]
  );

  const handleDelete = useCallback(
    (varId: string) => {
      if (disabled) return;
      void deleteVar(varId);
    },
    [disabled, deleteVar]
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
            Definer Variables ({nodeId})
          </Text>
          <Badge color="blue" variant="soft" size="1">
            State Schema
          </Badge>
        </Flex>

        {/* Existing Variables List */}
        <Box style={{ flexGrow: 1, minHeight: 0, overflowY: 'auto' }}>
          <Flex direction="column" gap="2">
            {variables.length === 0 && (
              <Text size="1" color="gray" style={{ fontStyle: 'italic', padding: '8px 0' }}>
                No variables declared yet. Add a state variable below.
              </Text>
            )}

            {variables.map((v) => (
              <Flex key={v.id} align="center" gap="2">
                {/* Locked Key Name */}
                <Box style={{ width: '130px', flexShrink: 0 }}>
                  <TextField.Root
                    size="1"
                    value={v.key}
                    readOnly
                    style={{
                      fontFamily: 'Consolas, Menlo, Monaco, "Courier New", monospace',
                      backgroundColor: 'var(--gray-3)',
                      color: 'var(--gray-11)',
                    }}
                  />
                </Box>

                {/* Type Selector */}
                <Box style={{ width: '90px', flexShrink: 0 }}>
                  <Select.Root
                    size="1"
                    value={v.type}
                    onValueChange={(val) => handleUpdateType(v.id, val as any)}
                    disabled={disabled}
                  >
                    <Select.Trigger style={{ width: '100%' }} />
                    <Select.Content>
                      <Select.Item value="string">string</Select.Item>
                      <Select.Item value="number">number</Select.Item>
                      <Select.Item value="float">float</Select.Item>
                      <Select.Item value="boolean">boolean</Select.Item>
                    </Select.Content>
                  </Select.Root>
                </Box>

                {/* Default Value Preview */}
                <Box style={{ flexGrow: 1, minWidth: 0 }}>
                  <Text size="1" color="gray" style={{ fontFamily: 'monospace' }}>
                    {v.default_value !== undefined && v.default_value !== null ? String(v.default_value) : 'None'}
                  </Text>
                </Box>

                {/* Trash Button */}
                <IconButton
                  size="1"
                  variant="ghost"
                  color="red"
                  onClick={() => handleDelete(v.id)}
                  disabled={disabled}
                >
                  <TrashIcon width="14" height="14" />
                </IconButton>
              </Flex>
            ))}
          </Flex>
        </Box>

        {/* Error Feedback */}
        {errorMsg && (
          <Text size="1" color="red">
            ⚠️ {errorMsg}
          </Text>
        )}

        {/* Draft Creation Row */}
        <Flex direction="column" gap="1" style={{ flexShrink: 0, borderTop: '1px solid var(--gray-4)', paddingTop: '8px' }}>
          <Text size="1" color="gray" weight="bold">
            Add New Variable
          </Text>

          <Flex align="center" gap="2">
            <Box style={{ width: '140px' }}>
              <TextField.Root
                size="1"
                placeholder="variable_name"
                value={draftKey}
                onChange={(e) => {
                  setDraftKey(e.target.value);
                  setErrorMsg(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleAdd();
                }}
                disabled={disabled}
                style={{ fontFamily: 'Consolas, Menlo, Monaco, "Courier New", monospace' }}
              />
            </Box>

            <Box style={{ width: '90px' }}>
              <Select.Root
                size="1"
                value={draftType}
                onValueChange={(val) => setDraftType(val as any)}
                disabled={disabled}
              >
                <Select.Trigger style={{ width: '100%' }} />
                <Select.Content>
                  <Select.Item value="string">string</Select.Item>
                  <Select.Item value="number">number</Select.Item>
                  <Select.Item value="float">float</Select.Item>
                  <Select.Item value="boolean">boolean</Select.Item>
                </Select.Content>
              </Select.Root>
            </Box>

            <Button
              size="1"
              variant="solid"
              color="blue"
              onClick={handleAdd}
              disabled={disabled || !draftKey.trim()}
              style={{ cursor: disabled || !draftKey.trim() ? 'default' : 'pointer' }}
            >
              <PlusIcon width="14" height="14" /> Add
            </Button>
          </Flex>
        </Flex>
      </Flex>
    </Card>
  );
};
