import { TrashIcon } from '@radix-ui/react-icons';
import { Box, Card, Flex, IconButton, Select, Text, TextField } from '@radix-ui/themes';
import { useMemo, type ReactNode } from 'react';
import type { DefinerVariable } from '../../canvas/types';
import { useGraphQuery } from '../../hooks/graph/useGraphQuery';
import { getTokenStyle, TARGET_TOKEN_STYLE } from './ExpressionEngine';

export function ExpressionChip({
  chip,
}: {
  chip: {
    kind: 'var' | 'op' | 'val';
    valType?: 'string' | 'number' | 'boolean' | 'float';
    value?: any;
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

/** 
 * Custom hook to abstract common data fetching and graph parsing for all node editors 
 */
export function useNodeEditorData(graphId: string, nodeId: string) {
  const { data: graphFlow } = useGraphQuery(graphId);
  const rawFlow = (graphFlow || {}) as Record<string, any>;
  const nodes = rawFlow.nodes || [];
  const definerOps = rawFlow.operations?.definer || [];
  const logicalOps = rawFlow.operations?.logical || [];
  
  const node = useMemo(() => {
    return nodes.find((n: any) => n.id === nodeId);
  }, [nodes, nodeId]);

  const stateVariables: DefinerVariable[] = useMemo(() => {
    return definerOps.flatMap((op: any) => op.variables || []);
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
