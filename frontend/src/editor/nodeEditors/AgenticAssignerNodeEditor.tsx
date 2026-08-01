import { Cross2Icon, PlusIcon } from '@radix-ui/react-icons';
import { Badge, Box, Button, Flex, Select, Text } from '@radix-ui/themes';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useUpdateNode } from '../../api/mutations';
import { NodeEditorCard, TargetVariableChip, useNodeEditorData, } from './NodeEditorShared';

interface AgenticAssignerNodeEditorProps {
  graphId: string;
  nodeId: string;
  disabled?: boolean;
}

export const AgenticAssignerNodeEditor = ({
  graphId,
  nodeId,
  disabled = false,
}: AgenticAssignerNodeEditorProps) => {
  const { node, stateVariables } = useNodeEditorData(graphId, nodeId);
  const { mutateAsync: updateNode } = useUpdateNode(graphId);

  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Local state for prompt and variables, initialized from node data
  const [prompt, setPrompt] = useState('');
  const [inputs, setInputs] = useState<string[]>([]);
  const [outputs, setOutputs] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [selectedInput, setSelectedInput] = useState('');
  const [selectedOutput, setSelectedOutput] = useState('');

  // Sync state with node when it changes
  useEffect(() => {
    if (node) {
      setPrompt(node.prompt || '');
      setInputs(node.agentic_inputs || []);
      setOutputs(node.agentic_outputs || []);
    }
  }, [node]);

  // Compute variables available for selection
  const availableInputVars = useMemo(() => {
    return stateVariables.filter((v) => !inputs.includes(v.key));
  }, [stateVariables, inputs]);

  const availableOutputVars = useMemo(() => {
    return stateVariables.filter((v) => !outputs.includes(v.key));
  }, [stateVariables, outputs]);

  const handleAddInput = useCallback((key: string) => {
    if (key && !inputs.includes(key)) {
      setInputs((prev) => [...prev, key]);
    }
    setSelectedInput('');
  }, [inputs]);

  const handleRemoveInput = useCallback((key: string) => {
    setInputs((prev) => prev.filter((k) => k !== key));
  }, []);

  const handleAddOutput = useCallback((key: string) => {
    if (key && !outputs.includes(key)) {
      setOutputs((prev) => [...prev, key]);
    }
    setSelectedOutput('');
  }, [outputs]);

  const handleRemoveOutput = useCallback((key: string) => {
    setOutputs((prev) => prev.filter((k) => k !== key));
  }, []);

  const handleAppendPlaceholder = useCallback((key: string) => {
    setPrompt((prev) => prev + `{${key}}`);
  }, []);

  const handleSave = useCallback(async () => {
    if (disabled) return;
    setErrorMsg(null);
    setIsSaving(true);

    try {
      await updateNode({
        nodeId,
        updates: {
          prompt,
          agentic_inputs: inputs,
          agentic_outputs: outputs,
        },
      });
    } catch (e: unknown) {
      setErrorMsg((e as Error)?.message || 'Failed to save agentic assigner settings.');
    } finally {
      setIsSaving(false);
    }
  }, [disabled, nodeId, prompt, inputs, outputs, updateNode]);

  // Saved/Configured list view (read-only)
  const listContent = (
    <Flex direction="column" gap="3">
      {/* Inputs Preview */}
      <Flex direction="column" gap="1">
        <Text size="1" color="gray" weight="bold">
          INPUT VARIABLES (PARAMETERS):
        </Text>
        <Flex gap="1" wrap="wrap" align="center">
          {(node?.agentic_inputs || []).length === 0 && (
            <Text size="1" color="gray" style={{ fontStyle: 'italic' }}>
              No input variables defined.
            </Text>
          )}
          {(node?.agentic_inputs || []).map((inputKey) => {
            const isMissing = !stateVariables.some((v) => v.key === inputKey);
            return (
              <TargetVariableChip key={inputKey} varKey={inputKey} isMissing={isMissing}/>
            );
          })}
        </Flex>
      </Flex>

      {/* Outputs Preview */}
      <Flex direction="column" gap="1">
        <Text size="1" color="gray" weight="bold">
          OUTPUT VARIABLES (ASSIGNMENT TARGETS):
        </Text>
        <Flex gap="1" wrap="wrap" align="center">
          {(node?.agentic_outputs || []).length === 0 && (
            <Text size="1" color="gray" style={{ fontStyle: 'italic' }}>
              No output variables defined.
            </Text>
          )}
          {(node?.agentic_outputs || []).map((outputKey) => {
            const isMissing = !stateVariables.some((v) => v.key === outputKey);
            const type = stateVariables.find((v) => v.key === outputKey)?.type;
            return (
              <Flex key={outputKey} align="center" gap="1">
                <TargetVariableChip varKey={outputKey} isMissing={isMissing}/>
                {type && (
                  <Badge color="blue" size="1" variant="soft" style={{ fontFamily: 'monospace' }}>
                    {type}
                  </Badge>
                )}
              </Flex>
            );
          })}
        </Flex>
      </Flex>

      {/* Prompt Preview */}
      <Flex direction="column" gap="1">
        <Text size="1" color="gray" weight="bold">
          PROMPT TEMPLATE:
        </Text>
        <Box
          style={{
            backgroundColor: 'var(--gray-3)',
            border: '1px dashed var(--gray-6)',
            borderRadius: 'var(--radius-2)',
            padding: '8px 10px',
            minHeight: '40px',
            maxHeight: '120px',
            overflowY: 'auto',
            boxSizing: 'border-box',
          }}
        >
          {node?.prompt ? (
            <Text size="1" style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
              {node.prompt}
            </Text>
          ) : (
            <Text size="1" color="gray" style={{ fontStyle: 'italic' }}>
              No prompt template defined.
            </Text>
          )}
        </Box>
      </Flex>
    </Flex>
  );

  // Edit / Action workbench
  const workbenchContent = (
    <Flex direction="column" gap="3">
      <Text size="1" color="gray" weight="bold">
        EDIT STATEMENT SETTINGS
      </Text>

      {/* Edit Inputs */}
      <Flex direction="column" gap="1">
        <Text size="1" color="gray">
          Inputs:
        </Text>
        <Flex gap="1.5" align="center" wrap="wrap">
          {inputs.map((key) => (
            <Badge
              key={key}
              color="purple"
              variant="surface"
              style={{ display: 'flex', alignItems: 'center', gap: '4px', paddingLeft: '6px' }}
            >
              {key}
              <Box
                onClick={() => handleRemoveInput(key)}
                style={{ cursor: disabled ? 'default' : 'pointer', display: 'flex', alignItems: 'center' }}
              >
                <Cross2Icon width="10" height="10"/>
              </Box>
            </Badge>
          ))}
          {availableInputVars.length > 0 && (
            <Box style={{ width: '120px' }}>
              <Select.Root
                size="1"
                value={selectedInput}
                onValueChange={handleAddInput}
                disabled={disabled}
              >
                <Select.Trigger
                  placeholder="+ Add Input..."
                  variant="surface"
                  color="purple"
                  style={{ width: '100%' }}
                />
                <Select.Content color="purple">
                  {availableInputVars.map((v) => (
                    <Select.Item key={v.id} value={v.key}>
                      {v.key}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </Box>
          )}
        </Flex>
      </Flex>

      {/* Edit Outputs */}
      <Flex direction="column" gap="1">
        <Text size="1" color="gray">
          Outputs:
        </Text>
        <Flex gap="1.5" align="center" wrap="wrap">
          {outputs.map((key) => (
            <Badge
              key={key}
              color="blue"
              variant="surface"
              style={{ display: 'flex', alignItems: 'center', gap: '4px', paddingLeft: '6px' }}
            >
              {key}
              <Box
                onClick={() => handleRemoveOutput(key)}
                style={{ cursor: disabled ? 'default' : 'pointer', display: 'flex', alignItems: 'center' }}
              >
                <Cross2Icon width="10" height="10"/>
              </Box>
            </Badge>
          ))}
          {availableOutputVars.length > 0 && (
            <Box style={{ width: '120px' }}>
              <Select.Root
                size="1"
                value={selectedOutput}
                onValueChange={handleAddOutput}
                disabled={disabled}
              >
                <Select.Trigger
                  placeholder="+ Add Output..."
                  variant="surface"
                  color="blue"
                  style={{ width: '100%' }}
                />
                <Select.Content color="blue">
                  {availableOutputVars.map((v) => (
                    <Select.Item key={v.id} value={v.key}>
                      {v.key} ({v.type})
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </Box>
          )}
        </Flex>
      </Flex>

      {/* Edit Prompt Textarea */}
      <Flex direction="column" gap="1">
        <Text size="1" color="gray">
          Prompt Template:
        </Text>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={disabled}
          placeholder="e.g. Generate quiz questions about {category} for difficulty {level}..."
          style={{
            width: '100%',
            height: '80px',
            backgroundColor: 'var(--gray-3)',
            border: '1px solid var(--gray-5)',
            borderRadius: 'var(--radius-2)',
            color: 'var(--gray-12)',
            padding: '8px',
            fontFamily: 'monospace',
            fontSize: '11px',
            resize: 'vertical',
            boxSizing: 'border-box',
          }}
        />

        {/* Input tokens helper */}
        {inputs.length > 0 && (
          <Flex gap="1" align="center" wrap="wrap" mt="1">
            <Text size="1" color="gray" style={{ flexShrink: 0 }}>
              Click to insert:
            </Text>
            {inputs.map((key) => (
              <Badge
                key={key}
                color="purple"
                size="1"
                variant="soft"
                onClick={() => handleAppendPlaceholder(key)}
                style={{ cursor: disabled ? 'default' : 'pointer' }}
              >
                {`{${key}}`}
              </Badge>
            ))}
          </Flex>
        )}
      </Flex>

      {/* Save Button */}
      <Button
        size="1"
        variant="solid"
        color="green"
        onClick={handleSave}
        disabled={disabled || isSaving || !prompt.trim() || outputs.length === 0}
        style={{ cursor: disabled ? 'default' : 'pointer', width: '100%', marginTop: '4px' }}
      >
        <PlusIcon width="14" height="14"/> {isSaving ? 'Saving...' : 'Save Agentic Statement'}
      </Button>
    </Flex>
  );

  return (
    <NodeEditorCard
      title="Agentic Assigner"
      nodeId={nodeId}
      errorMsg={errorMsg}
      listContent={listContent}
      workbenchContent={workbenchContent}
    />
  );
};
