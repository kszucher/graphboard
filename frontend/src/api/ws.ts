import { getClientId, wsBaseUrl } from './client';

type GraphEvent =
  | { event: 'graph_created'; graph_id: string; payload: Record<string, unknown> }
  | { event: 'graph_updated'; graph_id: string; payload: Record<string, unknown> }
  | { event: 'ws_hello'; graph_id: string };

export type GraphEventWithSender = GraphEvent & { sender_client_id?: string | null };

/**
 * Open a websocket for a given graph and keep it alive with simple reconnect logic.
 * Logs connection state so issues are visible in the devtools console.
 */
export const connectGraphSocket = (graphId: string, onEvent: (event: GraphEventWithSender) => void): (() => void) => {
  let socket: WebSocket | null = null;
  let reconnectTimeout: number | null = null;
  let closedByUser = false;

  const clientId = getClientId();
  const socketUrl = `${wsBaseUrl}/ws/graphs/${graphId}?client_id=${encodeURIComponent(clientId)}`;

  const connect = () => {
    socket = new WebSocket(socketUrl);

    socket.onopen = () => {
      // Helpful for debugging connectivity issues
      console.info('[Graph WS] connected', { graphId, url: socketUrl });
    };

    socket.onmessage = evt => {
      try {
        const data = JSON.parse(evt.data) as GraphEventWithSender;
        onEvent(data);
      } catch (err) {
        console.warn('[Graph WS] Invalid payload', err);
      }
    };

    socket.onerror = evt => {
      console.error('[Graph WS] error', evt);
    };

    socket.onclose = evt => {
      console.warn('[Graph WS] closed', { code: evt.code, reason: evt.reason, graphId });
      if (!closedByUser) {
        reconnectTimeout = window.setTimeout(connect, 1000);
      }
    };
  };

  connect();

  return () => {
    closedByUser = true;
    if (reconnectTimeout !== null) {
      window.clearTimeout(reconnectTimeout);
    }
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.close();
    }
  };
};
