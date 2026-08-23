import { AlertDialog, Box, Button, Flex, Select, Text } from '@radix-ui/themes';
import { useState } from 'react';
import { useInitiateCopilot } from '../api/mutations/copilot';

interface CopilotPanelProps {
  graphId: string;
}

const MODEL_OPTIONS = [
  { value: 'gemini-3.5-flash-lite', label: '3.5 Flash Lite' },
  { value: 'gemini-3.6-flash', label: '3.6 Flash' },
] as const;

export const CopilotPanel = ({ graphId }: CopilotPanelProps) => {
  const [prompt, setPrompt] = useState('');
  const [selectedModel, setSelectedModel] = useState<string>('gemini-3.5-flash-lite');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const initiateCopilot = useInitiateCopilot(graphId);
  const isPending = initiateCopilot.isPending;

  const handleInitiate = async () => {
    if (!prompt.trim() || isPending) return;
    setErrorMessage(null);
    try {
      const res = await initiateCopilot.mutateAsync({ prompt, model: selectedModel });
      if (res.applied) {
        setPrompt('');
      } else {
        setErrorMessage(res.validation_error ?? 'The Copilot pipeline completed but changes were not applied.');
      }
    } catch (err) {
      setErrorMessage('Failed to initiate Copilot workflow.');
      console.error(err);
    }
  };

  return (
    <>
      {/* Error Dialog */}
      <AlertDialog.Root open={errorMessage !== null} onOpenChange={(open) => { if (!open) setErrorMessage(null); }}>
        <AlertDialog.Content maxWidth="480px">
          <AlertDialog.Title>Copilot Error</AlertDialog.Title>
          <AlertDialog.Description>
            <Text as="p" size="2" style={{ whiteSpace: 'pre-wrap' }}>
              {errorMessage}
            </Text>
          </AlertDialog.Description>
          <Flex gap="3" mt="4" justify="end">
            <AlertDialog.Cancel>
              <Button variant="soft" color="gray">Dismiss</Button>
            </AlertDialog.Cancel>
          </Flex>
        </AlertDialog.Content>
      </AlertDialog.Root>

      {/* Floating Pill Panel */}
      <Box
        position="absolute"
        style={{
          bottom: '24px',
          left: '50%',
          transform: 'translateX(-50%)',
          width: 'calc(100% - 48px)',
          maxWidth: '620px',
          zIndex: 99,
          backgroundColor: 'rgba(24, 24, 28, 0.88)',
          backdropFilter: 'blur(16px)',
          borderRadius: '99px',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          boxShadow: '0 12px 32px rgba(0, 0, 0, 0.45)',
          padding: '6px 8px 6px 20px',
        }}
      >
        <Flex gap="3" align="center" width="100%">
          <input
            type="text"
            placeholder="Ask Copilot to build or refactor your graph..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={isPending}
            style={{
              flexGrow: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'white',
              fontSize: '13px',
              height: '32px',
              fontFamily: 'inherit',
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleInitiate();
            }}
          />

          <Select.Root
            size="1"
            value={selectedModel}
            onValueChange={setSelectedModel}
            disabled={isPending}
          >
            <Select.Trigger
              variant="ghost"
              color="gray"
              style={{
                borderRadius: '8px',
                cursor: isPending ? 'not-allowed' : 'pointer',
                color: 'var(--gray-11)',
                fontWeight: 500,
                fontSize: '12px',
                flexShrink: 0,
              }}
            />
            <Select.Content position="popper" side="top" align="end">
              <Select.Group>
                {MODEL_OPTIONS.map((opt) => (
                  <Select.Item key={opt.value} value={opt.value}>
                    {opt.label}
                  </Select.Item>
                ))}
              </Select.Group>
            </Select.Content>
          </Select.Root>

          <Button
            size="2"
            onClick={() => void handleInitiate()}
            disabled={isPending || !prompt.trim()}
            style={{
              borderRadius: '99px',
              paddingLeft: '16px',
              paddingRight: '16px',
              cursor: isPending || !prompt.trim() ? 'not-allowed' : 'pointer',
              backgroundColor: 'var(--accent-9)',
              fontWeight: 500,
              flexShrink: 0,
            }}
          >
            {isPending ? 'Planning...' : 'Submit'}
          </Button>
        </Flex>
      </Box>
    </>
  );
};
