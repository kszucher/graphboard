import type { Connection, OnError } from '@xyflow/react';
import { Controls, ReactFlow, useReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useCallback } from 'react';
import { useCreateEdge, useDeleteEdge, useReconnectEdge } from '../api/mutations';
import { useGraphKeyboardShortcuts } from '../hooks/graph/useGraphKeyboardShortcuts';
import { useGraphWebSocket } from '../hooks/graph/useGraphWebSocket';
import { useLaidOutGraph } from '../hooks/graph/useLaidOutGraph';
import FlowEdge from './edge/FlowEdge.tsx';
import { CustomNode } from './node/FlowNode.tsx';
import type { AppFlowEdge } from './types';

const nodeTypes = { custom: CustomNode };
const edgeTypes = { custom: FlowEdge };

const FlowContent = ({
  selectedGraphId,
}: {
  selectedGraphId: string;
}) => {
  const { isLoading, onNodesChange, onEdgesChange } = useLaidOutGraph(selectedGraphId);

  const { mutateAsync: createEdge } = useCreateEdge(selectedGraphId);
  const { mutateAsync: deleteEdge } = useDeleteEdge(selectedGraphId);
  const { mutateAsync: reconnectEdge } = useReconnectEdge(selectedGraphId);

  const { fitView } = useReactFlow();

  useGraphWebSocket(selectedGraphId);
  useGraphKeyboardShortcuts(selectedGraphId);

  const isValidConnection = useCallback(() => true, []);

  const handleDoubleClick = useCallback(
    (event: React.MouseEvent) => {
      const target = event.target as HTMLElement;
      if (target.classList.contains('react-flow__pane')) {
        event.preventDefault();
        void fitView({ padding: 0.1, duration: 300 });
      }
    },
    [fitView],
  );

  const handleError: OnError = useCallback((code, message) => {
    if (code === '008') {
      return;
    }
    console.warn(message);
  }, []);

  const onConnect = useCallback((connection: Connection) => {
    if (connection.source && connection.target && connection.sourceHandle && connection.targetHandle) {
      void createEdge({
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle,
        targetHandle: connection.targetHandle,
      });
    }
  }, [createEdge]);

  const onEdgesDelete = useCallback((edgesToDelete: AppFlowEdge[]) => {
    edgesToDelete.forEach(e => {
      void deleteEdge(e.id);
    });
  }, [deleteEdge]);

  const onReconnect = useCallback((oldEdge: AppFlowEdge, newConnection: Connection) => {
    if (newConnection.source && newConnection.target && newConnection.sourceHandle && newConnection.targetHandle) {
      void reconnectEdge({
        edgeId: oldEdge.id,
        source: newConnection.source,
        target: newConnection.target,
        sourceHandle: newConnection.sourceHandle,
        targetHandle: newConnection.targetHandle,
      });
    }
  }, [reconnectEdge]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div style={{
        width: '100%',
        height: '100%',
        opacity: isLoading ? 0 : 1,
        transition: 'opacity 0.2s ease-in-out',
        pointerEvents: isLoading ? 'none' : 'auto',
      }}>
        <ReactFlow
          defaultNodes={[]}
          defaultEdges={[]}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onEdgesDelete={onEdgesDelete}
          onReconnect={onReconnect}
          isValidConnection={isValidConnection}
          nodesDraggable={false}
          multiSelectionKeyCode={null}
          deleteKeyCode={null}
          colorMode="dark"
          zoomOnScroll={true}
          zoomOnDoubleClick={false}
          panOnScroll={false}
          onDoubleClick={handleDoubleClick}
          onError={handleError}
        >
          <Controls/>
        </ReactFlow>
      </div>

      {isLoading && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--gray-11)',
          background: 'var(--gray-1)',
          zIndex: 10,
        }}>
          Loading Graph...
        </div>
      )}
    </div>
  );
};

export const Flow = ({ selectedGraphId }: { selectedGraphId: string }) => (
  <FlowContent selectedGraphId={selectedGraphId}/>
);
