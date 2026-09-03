import { getTokens } from './client';

// Use the browser's current origin when no explicit WebSocket server is set.
// This is important for the public HTTPS tunnel: browsers require WSS, and a
// relative path is not a valid value for the WebSocket constructor.
const WS_BASE_URL =
  import.meta.env.VITE_WS_BASE_URL ||
  (typeof window === 'undefined'
    ? ''
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`);

type SocketOptions<T> = {
  path: string;
  onMessage: (payload: T) => void;
  onStatus?: (status: 'connecting' | 'open' | 'closed' | 'reconnecting') => void;
};

export function connectSocket<T>({ path, onMessage, onStatus }: SocketOptions<T>) {
  let socket: WebSocket | null = null;
  let stopped = false;
  let retryMs = 1500;

  const connect = () => {
    if (stopped) return;
    onStatus?.(socket ? 'reconnecting' : 'connecting');
    const tokens = getTokens();
    const separator = path.includes('?') ? '&' : '?';
    const tokenQuery = tokens?.access ? `${separator}token=${encodeURIComponent(tokens.access)}` : '';
    socket = new WebSocket(`${WS_BASE_URL}${path}${tokenQuery}`);
    socket.onopen = () => {
      retryMs = 1500;
      onStatus?.('open');
    };
    socket.onmessage = (event) => onMessage(JSON.parse(event.data) as T);
    socket.onclose = () => {
      if (stopped) return;
      onStatus?.('closed');
      window.setTimeout(connect, retryMs);
      retryMs = Math.min(10000, retryMs * 1.6);
    };
  };

  connect();

  return {
    send: (payload: unknown) => {
      if (socket?.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify(payload));
      return true;
    },
    close: () => {
      stopped = true;
      socket?.close();
    },
  };
}
