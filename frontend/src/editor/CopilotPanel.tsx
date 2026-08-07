import { Box, Button, Dialog, Flex, Text } from '@radix-ui/themes';
import { useState } from 'react';
import {
  useInitiateCopilot,
  useApproveCopilotPlan,
  useApplyCopilotPatch,
  useSubmitCopilotFeedback,
} from '../api/mutations/copilot';
import type { CopilotStatusResponse } from '../api/mutations/copilot';

interface CopilotPanelProps {
  graphId: string;
}

export const CopilotPanel = ({ graphId }: CopilotPanelProps) => {
  const [prompt, setPrompt] = useState('');
  const [copilotState, setCopilotState] = useState<CopilotStatusResponse | null>(null);
  const [rejectingStage, setRejectingStage] = useState<'plan' | 'apply' | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  const initiateCopilot = useInitiateCopilot(graphId);
  const approvePlan = useApproveCopilotPlan(graphId);
  const applyPatch = useApplyCopilotPatch(graphId);
  const submitFeedback = useSubmitCopilotFeedback(graphId);

  const isPending =
    initiateCopilot.isPending ||
    approvePlan.isPending ||
    applyPatch.isPending ||
    submitFeedback.isPending;

  const handleInitiate = async () => {
    if (!prompt.trim() || isPending) return;
    setRejectingStage(null);
    setRejectReason('');
    try {
      const res = await initiateCopilot.mutateAsync({ prompt });
      setCopilotState(res);
    } catch (err) {
      console.error(err);
      alert('Failed to initiate Copilot workflow.');
    }
  };

  const handleApprovePlan = async (approved: boolean) => {
    try {
      const res = await approvePlan.mutateAsync({ approved });
      setCopilotState(res);
      if (!approved) {
        setPrompt('');
      }
    } catch (err) {
      console.error(err);
      alert('Failed to process plan decision.');
    }
  };

  const handleApplyPatch = async (approved: boolean) => {
    try {
      const res = await applyPatch.mutateAsync({ approved });
      setCopilotState(res);
      setPrompt('');
    } catch (err) {
      console.error(err);
      alert('Failed to apply Copilot patch.');
    }
  };

  const handleCancelRejection = () => {
    setRejectingStage(null);
    setRejectReason('');
  };

  const handleConfirmRejection = async (withFeedback: boolean) => {
    try {
      if (withFeedback && rejectReason.trim()) {
        await submitFeedback.mutateAsync({
          score: 0,
          comment: rejectReason.trim(),
        });
      }

      if (rejectingStage === 'plan') {
        const res = await approvePlan.mutateAsync({ approved: false });
        setCopilotState(res);
      } else if (rejectingStage === 'apply') {
        const res = await applyPatch.mutateAsync({ approved: false });
        setCopilotState(res);
      }

      setPrompt('');
      setRejectReason('');
      setRejectingStage(null);
    } catch (err) {
      console.error(err);
      alert('Failed to submit rejection.');
    }
  };

  const showPlanDialog =
    copilotState?.status === 'pending_plan_approval' || rejectingStage === 'plan';
  const showApplyDialog =
    copilotState?.status === 'pending_apply_approval' || rejectingStage === 'apply';

  return (
    <>
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

      {/* STEP 1: Plan Review Dialog */}
      <Dialog.Root open={showPlanDialog} onOpenChange={(open) => { if (!open) { if (rejectingStage) handleCancelRejection(); else setRejectingStage('plan'); } }}>
        <Dialog.Content style={{ maxWidth: 500, backgroundColor: '#202024', color: 'white' }}>
          {rejectingStage === 'plan' ? (
            <Flex direction="column" gap="3">
              <Dialog.Title>Reject Proposed Plan</Dialog.Title>
              <Dialog.Description size="2" color="gray" mb="2">
                Help us improve Copilot by describing what was wrong with the plan.
              </Dialog.Description>
              <input
                type="text"
                placeholder="Reason for rejection (e.g. missing variable definition, wrong node name)..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                disabled={isPending}
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  outline: 'none',
                  color: 'white',
                  fontSize: '13px',
                  borderRadius: '6px',
                  padding: '8px 12px',
                  width: '100%',
                  boxSizing: 'border-box',
                  fontFamily: 'inherit',
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleConfirmRejection(true);
                }}
              />
              <Flex gap="3" justify="end" mt="2">
                <Button variant="soft" color="gray" onClick={handleCancelRejection} disabled={isPending} style={{ cursor: 'pointer' }}>
                  Back
                </Button>
                <Button variant="soft" color="gray" onClick={() => handleConfirmRejection(false)} disabled={isPending} style={{ cursor: 'pointer' }}>
                  Skip & Reject
                </Button>
                <Button onClick={() => handleConfirmRejection(true)} disabled={isPending} style={{ cursor: 'pointer' }}>
                  {isPending ? 'Submitting...' : 'Submit & Reject'}
                </Button>
              </Flex>
            </Flex>
          ) : (
            <>
              <Dialog.Title>Review Proposed Plan</Dialog.Title>
              <Dialog.Description size="2" color="gray" mb="4">
                The Copilot Planner has generated a checklist of actions to achieve your request.
              </Dialog.Description>

              <Flex direction="column" gap="2" mb="4">
                {copilotState?.plan?.map((step: any, idx: number) => (
                  <Box
                    key={idx}
                    p="2"
                    style={{
                      backgroundColor: 'rgba(255, 255, 255, 0.05)',
                      borderRadius: '6px',
                      borderLeft: '4px solid var(--accent-9)',
                    }}
                  >
                    <Text size="2" weight="bold">
                      {idx + 1}. {step.action.toUpperCase()}
                    </Text>
                    <Text as="p" size="2" color="gray">
                      {step.description}
                    </Text>
                    {step.details && (
                      <Text as="p" size="1" color="teal" style={{ fontStyle: 'italic' }}>
                        {step.details}
                      </Text>
                    )}
                  </Box>
                ))}
              </Flex>

              <Flex gap="3" justify="end">
                <Button variant="soft" color="gray" onClick={() => setRejectingStage('plan')} style={{ cursor: 'pointer' }}>
                  Reject
                </Button>
                <Button onClick={() => handleApprovePlan(true)} disabled={isPending} style={{ cursor: 'pointer' }}>
                  {isPending ? 'Executing...' : 'Proceed to Step 2'}
                </Button>
              </Flex>
            </>
          )}
        </Dialog.Content>
      </Dialog.Root>

      {/* STEP 2: Operations Review & Validation Dialog */}
      <Dialog.Root open={showApplyDialog} onOpenChange={(open) => { if (!open) { if (rejectingStage) handleCancelRejection(); else setRejectingStage('apply'); } }}>
        <Dialog.Content style={{ maxWidth: 550, backgroundColor: '#202024', color: 'white' }}>
          {rejectingStage === 'apply' ? (
            <Flex direction="column" gap="3">
              <Dialog.Title>Reject Proposed Mutations</Dialog.Title>
              <Dialog.Description size="2" color="gray" mb="2">
                Help us improve Copilot by describing what was wrong with the generated mutations.
              </Dialog.Description>
              <input
                type="text"
                placeholder="Reason for rejection (e.g. invalid operation details, missing edge)..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                disabled={isPending}
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  outline: 'none',
                  color: 'white',
                  fontSize: '13px',
                  borderRadius: '6px',
                  padding: '8px 12px',
                  width: '100%',
                  boxSizing: 'border-box',
                  fontFamily: 'inherit',
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleConfirmRejection(true);
                }}
              />
              <Flex gap="3" justify="end" mt="2">
                <Button variant="soft" color="gray" onClick={handleCancelRejection} disabled={isPending} style={{ cursor: 'pointer' }}>
                  Back
                </Button>
                <Button variant="soft" color="gray" onClick={() => handleConfirmRejection(false)} disabled={isPending} style={{ cursor: 'pointer' }}>
                  Skip & Reject
                </Button>
                <Button onClick={() => handleConfirmRejection(true)} disabled={isPending} style={{ cursor: 'pointer' }}>
                  {isPending ? 'Submitting...' : 'Submit & Reject'}
                </Button>
              </Flex>
            </Flex>
          ) : (
            <>
              <Dialog.Title>Operations & Validation Review</Dialog.Title>
              <Dialog.Description size="2" color="gray" mb="4">
                The Executor has generated API mutations. Check the validation status before applying.
              </Dialog.Description>

              {/* Validation Banner */}
              {copilotState?.validation_error ? (
                <Box
                  p="3"
                  mb="4"
                  style={{
                    backgroundColor: 'rgba(255, 80, 80, 0.15)',
                    border: '1px solid rgb(255, 80, 80)',
                    borderRadius: '6px',
                  }}
                >
                  <Text size="2" weight="bold" style={{ color: 'rgb(255, 100, 100)' }}>
                    ❌ Validation Failed
                  </Text>
                  <Text as="p" size="1" style={{ color: 'rgba(255, 255, 255, 0.8)', whiteSpace: 'pre-wrap' }}>
                    {copilotState.validation_error}
                  </Text>
                </Box>
              ) : (
                <Box
                  p="3"
                  mb="4"
                  style={{
                    backgroundColor: 'rgba(80, 255, 80, 0.15)',
                    border: '1px solid rgb(80, 255, 80)',
                    borderRadius: '6px',
                  }}
                >
                  <Text size="2" weight="bold" style={{ color: 'rgb(100, 255, 100)' }}>
                    ✅ Validation Passed
                  </Text>
                  <Text as="p" size="1" style={{ color: 'rgba(255, 255, 255, 0.8)' }}>
                    Graph mutations verified and ready to commit.
                  </Text>
                </Box>
              )}

              <Flex direction="column" gap="2" mb="4" style={{ maxHeight: '250px', overflowY: 'auto' }}>
                <Text size="2" weight="bold" color="gray">
                  Generated Mutations:
                </Text>
                {copilotState?.operations?.map((op: any, idx: number) => (
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
                    <pre style={{ fontSize: '11px', color: 'var(--gray-11)', whiteSpace: 'pre-wrap', margin: 0 }}>
                      {JSON.stringify(op, null, 2)}
                    </pre>
                  </Box>
                ))}
              </Flex>

              <Flex gap="3" justify="end">
                <Button variant="soft" color="gray" onClick={() => setRejectingStage('apply')} style={{ cursor: 'pointer' }}>
                  Reject
                </Button>
                <Button
                  onClick={() => handleApplyPatch(true)}
                  disabled={isPending || !!copilotState?.validation_error}
                  style={{
                    backgroundColor: !!copilotState?.validation_error ? 'var(--gray-8)' : 'var(--accent-9)',
                    cursor: !!copilotState?.validation_error ? 'not-allowed' : 'pointer',
                  }}
                >
                  Apply Patch
                </Button>
              </Flex>
            </>
          )}
        </Dialog.Content>
      </Dialog.Root>
    </>
  );
};
