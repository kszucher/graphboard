import { Box, Button, Flex, Text } from '@radix-ui/themes';
import { useState } from 'react';
import { useInitiateCopilot } from '../api/mutations/copilot';
import type { CopilotStatusResponse } from '../api/mutations/copilot';

interface CopilotPanelProps {
  graphId: string;
}

export const CopilotPanel = ({ graphId }: CopilotPanelProps) => {
  const [prompt, setPrompt] = useState('');
  const [copilotState, setCopilotState] = useState<CopilotStatusResponse | null>(null);

  const initiateCopilot = useInitiateCopilot(graphId);
  const isPending = initiateCopilot.isPending;

  const handleInitiate = async () => {
    if (!prompt.trim() || isPending) return;
    try {
      const res = await initiateCopilot.mutateAsync({ prompt });
      setCopilotState(res);
      if (res.applied) {
        setPrompt('');
      }
    } catch (err) {
      console.error(err);
      alert('Failed to initiate Copilot workflow.');
    }
  };

  return (
    <>
      {/* Floating Status Panel */}
      {copilotState && (
        <Box
          position="absolute"
          style={{
            bottom: '90px',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 'calc(100% - 48px)',
            maxWidth: '580px',
            zIndex: 99,
            backgroundColor: '#202024',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            boxShadow: '0 12px 32px rgba(0, 0, 0, 0.45)',
            padding: '16px',
            maxHeight: '400px',
            overflowY: 'auto',
            color: 'white',
          }}
        >
          <Flex justify="between" align="center" mb="3">
            <Text size="2" weight="bold">Copilot Execution Summary</Text>
            <Button
              size="1"
              variant="ghost"
              color="gray"
              onClick={() => setCopilotState(null)}
              style={{ cursor: 'pointer' }}
            >
              Clear
            </Button>
          </Flex>

          {/* Validation / Execution Banner */}
          {copilotState.validation_error ? (
            <Box
              p="3"
              mb="3"
              style={{
                backgroundColor: 'rgba(255, 80, 80, 0.15)',
                border: '1px solid rgb(255, 80, 80)',
                borderRadius: '6px',
              }}
            >
              <Text size="2" weight="bold" style={{ color: 'rgb(255, 100, 100)' }}>
                ❌ Validation Failed
              </Text>
              <Text as="p" size="1" style={{ color: 'rgba(255, 255, 255, 0.8)', whiteSpace: 'pre-wrap', marginTop: '4px' }}>
                {copilotState.validation_error}
              </Text>
            </Box>
          ) : copilotState.applied ? (
            <Box
              p="3"
              mb="3"
              style={{
                backgroundColor: 'rgba(80, 255, 80, 0.15)',
                border: '1px solid rgb(80, 255, 80)',
                borderRadius: '6px',
              }}
            >
              <Text size="2" weight="bold" style={{ color: 'rgb(100, 255, 100)' }}>
                ✅ Successfully Applied Changes
              </Text>
              <Text as="p" size="1" style={{ color: 'rgba(255, 255, 255, 0.8)', marginTop: '4px' }}>
                The mutations have been successfully applied to your graph.
              </Text>
            </Box>
          ) : (
            <Box
              p="3"
              mb="3"
              style={{
                backgroundColor: 'rgba(255, 255, 80, 0.15)',
                border: '1px solid rgb(255, 255, 80)',
                borderRadius: '6px',
              }}
            >
              <Text size="2" weight="bold" style={{ color: 'rgb(255, 255, 100)' }}>
                ⚠️ Pipeline Ended Without Apply
              </Text>
              <Text as="p" size="1" style={{ color: 'rgba(255, 255, 255, 0.8)', marginTop: '4px' }}>
                The execution pipeline completed but changes were not applied.
              </Text>
            </Box>
          )}

          {/* Plan Steps */}
          {copilotState.plan && copilotState.plan.length > 0 && (
            <Box mb="3">
              <Text size="2" weight="bold" color="gray" mb="2" as="div">Planner Checklist:</Text>
              <Flex direction="column" gap="2">
                {copilotState.plan.map((step: any, idx: number) => (
                  <Box
                    key={idx}
                    p="2"
                    style={{
                      backgroundColor: 'rgba(255, 255, 255, 0.03)',
                      borderRadius: '6px',
                    }}
                  >
                    <Text size="1" weight="bold">
                      {idx + 1}. {step.action.toUpperCase()}
                    </Text>
                    <Text as="p" size="1" color="gray">
                      {step.description}
                    </Text>
                  </Box>
                ))}
              </Flex>
            </Box>
          )}

          {/* Operations List */}
          {copilotState.operations && copilotState.operations.length > 0 && (
            <Box>
              <Text size="2" weight="bold" color="gray" mb="2" as="div">Generated Mutations:</Text>
              <Flex direction="column" gap="2" style={{ maxHeight: '150px', overflowY: 'auto' }}>
                {copilotState.operations.map((op: any, idx: number) => (
                  <Box
                    key={idx}
                    p="2"
                    style={{
                      backgroundColor: 'rgba(255, 255, 255, 0.03)',
                      borderRadius: '6px',
                    }}
                  >
                    <Text size="1" weight="bold">
                      {op.op.toUpperCase()}
                    </Text>
                    <pre style={{ fontSize: '10px', color: 'var(--gray-11)', whiteSpace: 'pre-wrap', margin: 0 }}>
                      {JSON.stringify(op, null, 2)}
                    </pre>
                  </Box>
                ))}
              </Flex>
            </Box>
          )}
        </Box>
      )}

      {/* Floating Pill Panel */}
      <Box
        position="absolute"
        style={{
          bottom: '24px',
          left: '50%',
          transform: 'translateX(-50%)',
          width: 'calc(100% - 48px)',
          maxWidth: '580px',
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
              if (e.key === 'Enter') handleInitiate();
            }}
          />

          <Button
            size="2"
            onClick={handleInitiate}
            disabled={isPending || !prompt.trim()}
            style={{
              borderRadius: '99px',
              paddingLeft: '16px',
              paddingRight: '16px',
              cursor: isPending || !prompt.trim() ? 'not-allowed' : 'pointer',
              backgroundColor: 'var(--accent-9)',
              fontWeight: 500,
            }}
          >
            {isPending ? 'Planning...' : 'Submit'}
          </Button>
        </Flex>
      </Box>
    </>
  );
};
