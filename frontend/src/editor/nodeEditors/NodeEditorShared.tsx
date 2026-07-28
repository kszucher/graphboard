import { TrashIcon } from '@radix-ui/react-icons';
import { Box, Flex, IconButton, Select, Text, TextField } from '@radix-ui/themes';
import type { ReactNode } from 'react';
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
