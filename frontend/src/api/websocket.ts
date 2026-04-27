const WS_URL = import.meta.env.VITE_WS_URL ?? "";

export type MessageType = "chunk" | "complete" | "error" | "tools";

export interface WSMessage {
  type: MessageType;
  content?: string;
  session_id?: string;
  message?: string;
  steps?: string[];
}

export type WSMessageHandler = (msg: WSMessage) => void;

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnects = 3;
  private baseDelay = 1000;
  private onMessage: WSMessageHandler;
  private onStatusChange: (connected: boolean) => void;
  private token: string;

  constructor(
    token: string,
    onMessage: WSMessageHandler,
    onStatusChange: (connected: boolean) => void,
  ) {
    this.token = token;
    this.onMessage = onMessage;
    this.onStatusChange = onStatusChange;
  }

  connect() {
    if (!WS_URL) return;

    const url = `${WS_URL}?token=${encodeURIComponent(this.token)}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.onStatusChange(true);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        this.onMessage(msg);
      } catch {
        /* ignore malformed messages */
      }
    };

    this.ws.onclose = () => {
      this.onStatusChange(false);
      this._tryReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  send(prompt: string, sessionId: string, apmId?: string) {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(
      JSON.stringify({
        action: "sendMessage",
        data: { prompt, session_id: sessionId, apm_id: apmId },
      }),
    );
    return true;
  }

  disconnect() {
    this.maxReconnects = 0; // prevent reconnect on intentional close
    this.ws?.close();
    this.ws = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  updateToken(token: string) {
    this.token = token;
  }

  private _tryReconnect() {
    if (this.reconnectAttempts >= this.maxReconnects) return;
    this.reconnectAttempts++;
    const delay = this.baseDelay * Math.pow(2, this.reconnectAttempts - 1);
    setTimeout(() => this.connect(), delay);
  }
}
