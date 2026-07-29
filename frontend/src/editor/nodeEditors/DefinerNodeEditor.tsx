import { PlusIcon, ResetIcon } from '@radix-ui/react-icons';
import { Badge, Button, Flex, IconButton, Select, Text, TextField } from '@radix-ui/themes';
import { useCallback, useMemo, useState } from 'react';
import type { DefinerVariable } from '../../canvas/types';
import { useCreateDefinerVariable, useDeleteDefinerVariable, } from '../../hooks/graph/useGraphMutations';
import { coerceTypedValue, validateVariableName } from './ExpressionEngine';
import {
  ExpressionChip,
  NodeEditorCard,
  StaticRow,
  TargetVariableChip,
  TypedValueInput,
  useNodeEditorData,
} from './NodeEditorShared';

interface DefinerNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

type DefinerDraftStep = 'key' | 'type' | 'value_and_save';

export const DefinerNodeEditor = ({
  graphId,
  nodeId,
  disabled = false,
}: DefinerNodeEditorProps) => {
  const { node, nodes } = useNodeEditorData(graphId, nodeId);

  const variables: DefinerVariable[] = node?.variables || [];

  const allVariableKeys = useMemo(() => {
    const set = new Set<string>();
    nodes.forEach(n => {
      if (n.node_type === 'DEFINER') {
        n.variables?.forEach(v => set.add(v.key));
      }
    });
    return set;
  }, [nodes]);

  const { mutateAsync: createVar } = useCreateDefinerVariable(graphId);
  const { mutateAsync: deleteVar } = useDeleteDefinerVariable(graphId);

  // Left-to-Right Step-by-Step Workbench State
  const [definerStep, setDefinerStep] = useState<DefinerDraftStep>('key');
  const [draftKey, setDraftKey] = useState('');
  const [lockedKey, setLockedKey] = useState('');
  const [lockedType, setLockedType] = useState<'boolean' | 'string' | 'number' | 'float'>('string');
  const [draftDefault, setDraftDefault] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleLockKey = useCallback(() => {
    const err = validateVariableName(draftKey, allVariableKeys);
    if (err) {
      setErrorMsg(err);
      return;
    }
    setErrorMsg(null);
    setLockedKey(draftKey.trim());
    setDefinerStep('type');
  }, [draftKey, allVariableKeys]);

  const handleSelectType = useCallback((type: 'boolean' | 'string' | 'number' | 'float') => {
    setLockedType(type);
    setDraftDefault('');
    setDefinerStep('value_and_save');
  }, []);

  const handleResetDraft = useCallback(() => {
    setDefinerStep('key');
    setDraftKey('');
    setLockedKey('');
    setLockedType('string');
    setDraftDefault('');
    setErrorMsg(null);
  }, []);

  const handleSaveVariable = useCallback(async () => {
    if (disabled || definerStep !== 'value_and_save' || !lockedKey) return;
    setErrorMsg(null);
    const parsedDefault = coerceTypedValue(lockedType, draftDefault);

    try {
      await createVar({
        nodeId,
        key: lockedKey,
        type: lockedType,
        defaultValue: parsedDefault,
      });
      handleResetDraft();
    } catch (e: unknown) {
      setErrorMsg((e as Error)?.message || 'Failed to add state variable.');
    }
  }, [disabled, definerStep, lockedKey, lockedType, draftDefault, createVar, nodeId, handleResetDraft]);

  const handleDelete = useCallback(
    async (varId: string) => {
      if (disabled) return;
      try {
        await deleteVar(varId);
      } catch (e: unknown) {
        setErrorMsg((e as Error)?.message || 'Failed to delete variable.');
      }
    },
    [disabled, deleteVar]
  );

  const listContent = (
    <Flex direction="column" gap="1">
      {variables.length === 0 && (
        <Text size="1" color="gray" style={{ fontStyle: 'italic', padding: '4px 0' }}>
          No state variables declared.
        </Text>
      )}

      {variables.map((v) => (
        <StaticRow key={v.id} onDelete={() => handleDelete(v.id)} disabled={disabled}>
          <TargetVariableChip varKey={v.key}/>
          <Badge color="blue" variant="soft" style={{ fontFamily: 'monospace', fontWeight: 'bold' }}>
            {v.type}
          </Badge>
          <Text size="2" weight="bold" style={{ color: '#61afef' }}>
            =
          </Text>
          <ExpressionChip
            chip={{
              kind: 'val',
              valType: v.type,
              value: v.default_value ?? (v.type === 'number' || v.type === 'float' ? 0 : v.type === 'boolean' ? false : '""'),
            }}
          />
        </StaticRow>
      ))}
    </Flex>
  );

  const workbenchContent = (
    <Flex align="center" gap="2" style={{ overflowX: 'auto' }}>
      {/* Step 0: Input Variable Key */}
      {definerStep === 'key' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          <TextField.Root
            size="1"
            placeholder="var_name..."
            value={draftKey}
            onChange={(e) => setDraftKey(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleLockKey();
            }}
            disabled={disabled}
            color="red"
            style={{ width: '130px', fontFamily: 'monospace', fontWeight: 'bold' }}
          />
          <Button
            size="1"
            variant="solid"
            color="blue"
            onClick={handleLockKey}
            disabled={disabled || !draftKey.trim()}
          >
            :
          </Button>
        </Flex>
      )}

      {/* Step 1: Locked Key -> Select Variable Type */}
      {definerStep === 'type' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          <TargetVariableChip varKey={lockedKey}/>
          <Text size="2" weight="bold" style={{ color: '#61afef' }}>
            :
          </Text>
          <Select.Root
            size="1"
            value=""
            onValueChange={(val: 'boolean' | 'string' | 'number' | 'float') => {
              if (val) handleSelectType(val);
            }}
            disabled={disabled}
          >
            <Select.Trigger
              placeholder="select type..."
              color="blue"
              variant="surface"
              style={{ width: '95px', fontFamily: 'monospace' }}
            />
            <Select.Content color="blue">
              <Select.Item value="string">string</Select.Item>
              <Select.Item value="number">number</Select.Item>
              <Select.Item value="float">float</Select.Item>
              <Select.Item value="boolean">boolean</Select.Item>
            </Select.Content>
          </Select.Root>
        </Flex>
      )}

      {/* Step 2: Locked Key & Type -> Input Default Value & Save */}
      {definerStep === 'value_and_save' && (
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          <TargetVariableChip varKey={lockedKey}/>
          <Badge color="blue" variant="soft" style={{ fontFamily: 'monospace', fontWeight: 'bold' }}>
            {lockedType}
          </Badge>
          <Text size="2" weight="bold" style={{ color: '#61afef' }}>
            =
          </Text>
          <TypedValueInput
            targetVarType={lockedType}
            value={draftDefault}
            onChange={(val) => setDraftDefault(val)}
            disabled={disabled}
            onEnter={handleSaveVariable}
          />
          <Button
            size="1"
            variant="solid"
            color="green"
            onClick={handleSaveVariable}
            disabled={disabled}
            style={{ cursor: 'pointer' }}
          >
            <PlusIcon width="14" height="14"/> Save
          </Button>
        </Flex>
      )}

      {/* Revert / Cancel Button */}
      {definerStep !== 'key' && (
        <IconButton
          size="1"
          variant="ghost"
          color="gray"
          title="Reset / Revert Draft"
          onClick={handleResetDraft}
          disabled={disabled}
          style={{ cursor: 'pointer', flexShrink: 0, marginLeft: 'auto' }}
        >
          <ResetIcon width="12" height="12"/>
        </IconButton>
      )}
    </Flex>
  );

  return (
    <NodeEditorCard
      title="Definer State Schema"
      nodeId={nodeId}
      errorMsg={errorMsg}
      listContent={listContent}
      workbenchContent={workbenchContent}
    />
  );
};
