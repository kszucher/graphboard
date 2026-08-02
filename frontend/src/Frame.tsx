import { CaretDownIcon, CheckIcon, MixIcon, PlayIcon, ResetIcon } from '@radix-ui/react-icons';
import { Box, Button, DropdownMenu, Flex, IconButton, Text } from '@radix-ui/themes';
import { ReactFlowProvider } from '@xyflow/react';
import { useCallback, useMemo } from 'react';
import { useAddNode, useCreateGraph, useRedo, useRunGraph, useSetActiveGraph, useUndo } from './api/mutations';
import { useActiveGraphId, useGraphQuery, useUserGraphs, useUserId } from './api/queries';
import { Flow } from './canvas/Flow.tsx';
import { INSERTABLE_NODE_ITEMS, type NodeType } from './canvas/types';
import { LeftSidebar } from './editor/LeftSidebar.tsx';
import { RightSidebar } from './editor/RightSidebar.tsx';

export const Frame = () => {
  const { data: userId } = useUserId();
  const { data: selectedGraphId } = useActiveGraphId(userId ?? null);
  const { data: graphFlow } = useGraphQuery(selectedGraphId || '');
  const { data: graphs } = useUserGraphs(userId ?? null);

  const { mutate: undo } = useUndo(selectedGraphId || '');
  const { mutate: redo } = useRedo(selectedGraphId || '');
  const { mutate: addNode } = useAddNode(selectedGraphId || '');
  const { mutate: runGraph } = useRunGraph(selectedGraphId || '');

  const canUndo = graphFlow?.can_undo ?? false;
  const canRedo = graphFlow?.can_redo ?? false;

  const createGraphMutation = useCreateGraph();
  const setActiveGraphMutation = useSetActiveGraph();

  const handleCreateNode = useCallback(
    (nodeType: NodeType) => {
      void addNode(nodeType);
    },
    [addNode]
  );

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
          <Flex align="center" gap="2">
            <IconButton
              variant="solid"
              color="gray"
              radius="full"
              disabled={!isGraphSelected || !canUndo}
              onClick={() => undo()}
            >
              <ResetIcon width="20" height="20"/>
            </IconButton>

            <IconButton
              variant="solid"
              color="gray"
              radius="full"
              disabled={!isGraphSelected || !canRedo}
              onClick={() => redo()}
            >
              <ResetIcon width="20" height="20" style={{ transform: 'scaleX(-1)' }}/>
            </IconButton>

            <DropdownMenu.Root>
              <DropdownMenu.Trigger>
                <IconButton variant="solid" color="gray" radius="full" disabled={!isGraphSelected} title="Add Node">
                  <MixIcon width="20" height="20"/>
                </IconButton>
              </DropdownMenu.Trigger>
              {isGraphSelected && (
                <DropdownMenu.Content onCloseAutoFocus={e => e.preventDefault()}>
                  <DropdownMenu.Label>Add Primitive Node</DropdownMenu.Label>
                  {INSERTABLE_NODE_ITEMS.map((item) => (
                    <DropdownMenu.Item onClick={() => handleCreateNode(item.type)} key={item.type}>
                      {item.label}
                    </DropdownMenu.Item>
                  ))}
                </DropdownMenu.Content>
              )}
            </DropdownMenu.Root>

            <IconButton variant="solid" color="gray" radius="full" onClick={() => runGraph()}
                        disabled={!isGraphSelected}>
              <PlayIcon width="20" height="20"/>
            </IconButton>
          </Flex>
        </Flex>
      </Box>

      {/* Main Workspace (Left Sidebar + Canvas + Right Sidebar) */}
      <ReactFlowProvider key={selectedGraphId || 'no-graph'}>
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
          {/* Left Sidebar Component */}
          <LeftSidebar isGraphSelected={isGraphSelected} graphId={selectedGraphId || ''}/>

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
              <Flow selectedGraphId={selectedGraphId}/>
            )}
          </Box>

          {/* Right Sidebar Component */}
          <RightSidebar graphId={selectedGraphId || ''}/>
        </Flex>
      </ReactFlowProvider>
    </>
  );
};
