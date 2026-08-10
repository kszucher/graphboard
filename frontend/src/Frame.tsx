import { CaretDownIcon, CheckIcon, PlayIcon } from '@radix-ui/react-icons';
import { Box, Button, DropdownMenu, Flex, IconButton, Text } from '@radix-ui/themes';
import { ReactFlowProvider } from '@xyflow/react';
import { useCallback, useMemo, useState } from 'react';
import { useCreateGraph, useRunGraph, useSetActiveGraph } from './api/mutations';
import { useActiveGraphId, useGraphQuery, useUserGraphs, useUserId } from './api/queries';
import { Flow } from './canvas/Flow.tsx';
import { RightSidebar } from './editor/RightSidebar.tsx';
import { CopilotPanel } from './editor/CopilotPanel.tsx';


export const Frame = () => {
  const { data: userId } = useUserId();
  const { data: selectedGraphId } = useActiveGraphId(userId ?? null);
  const [prevGraphId, setPrevGraphId] = useState(selectedGraphId);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [baseVersion, setBaseVersion] = useState<number | null>(null);

  if (selectedGraphId !== prevGraphId) {
    setPrevGraphId(selectedGraphId);
    setSelectedVersion(null);
    setBaseVersion(null);
  }

  const { data: graphFlow } = useGraphQuery(selectedGraphId || '', selectedVersion);
  const { data: graphs } = useUserGraphs(userId ?? null);

  const { mutate: runGraph } = useRunGraph(selectedGraphId || '');

  const createGraphMutation = useCreateGraph();
  const setActiveGraphMutation = useSetActiveGraph();

  const handleCreateGraph = useCallback(() => {
    if (!userId) return;
    createGraphMutation.mutate({ userId, graphName: 'New Graph' });
  }, [userId, createGraphMutation]);

  const handleSelectGraph = useCallback(
    (graphId: string) => {
      if (!userId) return;
      setActiveGraphMutation.mutate({ userId, graphId });
    },
    [userId, setActiveGraphMutation]
  );

  const activeGraphName = useMemo(
    () => graphs?.find(graph => graph.id === selectedGraphId)?.name ?? 'Select graph',
    [graphs, selectedGraphId]
  );

  const currentVersionObj = useMemo(() => {
    if (!graphFlow?.versions) return null;
    return graphFlow.versions.find(v => v.sequence_number === (selectedVersion ?? graphFlow.current_version));
  }, [graphFlow, selectedVersion]);

  const activeVersionName = currentVersionObj?.name ?? (graphFlow?.current_version !== undefined ? `v${graphFlow.current_version + 1}` : 'v1');

  const baseVersionObj = useMemo(() => {
    if (!graphFlow?.versions || baseVersion === null) return null;
    return graphFlow.versions.find(v => v.sequence_number === baseVersion);
  }, [graphFlow, baseVersion]);

  const baseVersionName = baseVersionObj ? `Compare: ${baseVersionObj.name}` : 'Compare: None';

  const isGraphSelected = !!selectedGraphId;

  return (
    <>
      {/* App Bar */}
      <Box
        position="fixed"
        width="100%"
        height="40px"
        px="3"
        style={{
          zIndex: 9999,
          backgroundColor: 'rgba(32, 32, 36, 0.9)',
          borderBottom: '1px solid var(--gray-4)',
        }}
      >
        <Flex direction="row" align="center" justify="between" height="100%">
          {/* Left */}
          <Flex align="center" gap="2" width={'192px'}>
            <Text size="2" weight="bold" color="gray">
              graphboard
            </Text>
          </Flex>

          {/* Center */}
          <Flex align="center" gap="2">
            <DropdownMenu.Root>
              <DropdownMenu.Trigger>
                <IconButton variant="soft" color="gray" radius="full">
                  <CaretDownIcon/>
                </IconButton>
              </DropdownMenu.Trigger>
              <DropdownMenu.Content onCloseAutoFocus={e => e.preventDefault()}>
                <DropdownMenu.Label>My Graphs</DropdownMenu.Label>
                {!graphs && <DropdownMenu.Item disabled>Loading…</DropdownMenu.Item>}
                {graphs && graphs.length === 0 && <DropdownMenu.Item disabled>No graphs yet</DropdownMenu.Item>}
                {graphs?.map(graph => (
                  <DropdownMenu.Item key={graph.id} onClick={() => handleSelectGraph(graph.id)}>
                    <Flex align="center" gap="2">
                      {graph.id === selectedGraphId && <CheckIcon/>}
                      <Text>{graph.name}</Text>
                    </Flex>
                  </DropdownMenu.Item>
                ))}
              </DropdownMenu.Content>
            </DropdownMenu.Root>

            <Button variant="solid" radius="full" disabled={!isGraphSelected}>
              {activeGraphName}
            </Button>

            {/* New Graph Button */}
            <IconButton variant="soft" color="gray" radius="full" onClick={handleCreateGraph}>
              +
            </IconButton>
          </Flex>

          {/* Right */}
          <Flex align="center" gap="3">
            {isGraphSelected && graphFlow?.versions && (
              <Flex align="center" gap="2">
                <DropdownMenu.Root>
                  <DropdownMenu.Trigger>
                    <Button variant="soft" color="gray" radius="full">
                      {activeVersionName} <CaretDownIcon/>
                    </Button>
                  </DropdownMenu.Trigger>
                  <DropdownMenu.Content>
                    <DropdownMenu.Label>Versions</DropdownMenu.Label>
                    {graphFlow.versions.map(v => (
                      <DropdownMenu.Item
                        key={v.sequence_number}
                        onClick={() => setSelectedVersion(v.sequence_number)}
                      >
                        <Flex align="center" gap="2">
                          {v.sequence_number === (selectedVersion ?? graphFlow.current_version) && <CheckIcon/>}
                          <Text>{v.name}</Text>
                          <Text size="1" color="gray">
                            ({new Date(v.created_at).toLocaleTimeString()})
                          </Text>
                        </Flex>
                      </DropdownMenu.Item>
                    ))}
                  </DropdownMenu.Content>
                </DropdownMenu.Root>

                <DropdownMenu.Root>
                  <DropdownMenu.Trigger>
                    <Button variant="soft" color="gray" radius="full">
                      {baseVersionName} <CaretDownIcon/>
                    </Button>
                  </DropdownMenu.Trigger>
                  <DropdownMenu.Content>
                    <DropdownMenu.Label>Compare Base Version</DropdownMenu.Label>
                    <DropdownMenu.Item onClick={() => setBaseVersion(null)}>
                      <Flex align="center" gap="2">
                        {baseVersion === null && <CheckIcon/>}
                        <Text>None (No Diff)</Text>
                      </Flex>
                    </DropdownMenu.Item>
                    {graphFlow.versions.map(v => (
                      <DropdownMenu.Item
                        key={v.sequence_number}
                        onClick={() => setBaseVersion(v.sequence_number)}
                        disabled={v.sequence_number === (selectedVersion ?? graphFlow.current_version)}
                      >
                        <Flex align="center" gap="2">
                          {v.sequence_number === baseVersion && <CheckIcon/>}
                          <Text>{v.name}</Text>
                          <Text size="1" color="gray">
                            ({new Date(v.created_at).toLocaleTimeString()})
                          </Text>
                        </Flex>
                      </DropdownMenu.Item>
                    ))}
                  </DropdownMenu.Content>
                </DropdownMenu.Root>
              </Flex>
            )}

            <IconButton
              variant="solid"
              color="gray"
              radius="full"
              onClick={() => runGraph(selectedVersion ?? graphFlow?.current_version ?? null)}
              disabled={!isGraphSelected}
            >
              <PlayIcon width="20" height="20"/>
            </IconButton>
          </Flex>
        </Flex>
      </Box>

      {/* Main Workspace (Left Sidebar + Canvas + Right Sidebar) */}
      <ReactFlowProvider key={`${selectedGraphId || 'no-graph'}-${selectedVersion ?? 'latest'}`}>
        <Flex
          style={{
            width: '100vw',
            height: '100vh',
            paddingTop: '40px',
            boxSizing: 'border-box',
            overflow: 'hidden',
            backgroundColor: 'var(--gray-1)',
          }}
        >
          {/* Flow Canvas Container */}
          <Box
            style={{
              flexGrow: 1,
              height: '100%',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            {isGraphSelected && (
              <>
                <Flow selectedGraphId={selectedGraphId} version={selectedVersion}/>
                <CopilotPanel graphId={selectedGraphId}/>
              </>
            )}
          </Box>

          {/* Right Sidebar Component */}
          <RightSidebar graphId={selectedGraphId || ''} version={selectedVersion} baseVersion={baseVersion}/>
        </Flex>
      </ReactFlowProvider>
    </>
  );
};
