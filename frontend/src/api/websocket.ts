import type {
  WsServerChunk,
  AgentResponse,
} from '../types/agent';

// ─────────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────────

const WS_URL = import.meta.env.VITE_WS_URL ?? '';

// ─────────────────────────────────────────────────────────────────────────────
// Callback interfaces
// ─────────────────────────────────────────────────────────────────────────────

/** Callbacks for streaming protocol events */
export interface ChatWebSocketCallbacks {
  /** Called for each progressive text chunk */
  onChunk: (text: string) => void;
  /** Called when a tool starts executing */
  onToolStep: (tool: string, label: string) => void;
  /** Called when processing completes with full response */
  onComplete: (response: AgentResponse) => void;
  /** Called on error from the server */
  onError: (message: string, code?: string) => void;
  /** Called when connection status changes */
  onStatusChange: (connected: boolean) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Legacy types (backward compatibility)
// ─────────────────────────────────────────────────────────────────────────────

/** @deprecated Use ChatWebSocketCallbacks instead */
export type MessageType = 'chunk' | 'complete' | 'error' | 'tools' | 'tool_step';

/** @deprecated Use WsServerChunk from types/agent instead */
export interface WSMessage {
  type: MessageType;
  content?: string;
  session_id?: string;
  message?: string;
  steps?: string[];
  /** New protocol: text field from WsChunkMessage */
  text?: string;
  /** New protocol: tool label from WsToolStepMessage */
  label?: string;
  /** New protocol: tool name from WsToolStepMessage */
  tool?: string;
  /** New protocol: AgentResponse payload from WsCompleteMessage */
  payload?: AgentResponse;
  /** New protocol: error code from WsErrorMessage */
  code?: string;
}

/** @deprecated Use ChatWebSocketCallbacks instead */
export type WSMessageHandler = (msg: WSMessage) => void;

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket client
// ─────────────────────────────────────────────────────────────────────────────

/**
 * WebSocket client for streaming communication with the Lambda proxy.
 *
 * Handles the streaming protocol:
 * - `chunk`     → progressive text rendering
 * - `tool_step` → tool activity indicator
 * - `complete`  → final response with structured data
 * - `error`     → error display
 *
 * Supports both the new typed callbacks (ChatWebSocketCallbacks) and
 * the legacy WSMessageHandler for backward compatibility.
 */
export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxDelay = 30_000; // Cap at 30 seconds
  private baseDelay = 1000;
  private intentionalClose = false;
  private callbacks: ChatWebSocketCallbacks;
  private legacyHandler: WSMessageHandler | null = null;
  private token: string;

  /**
   * Create a new ChatWebSocket with typed streaming callbacks.
   */
  constructor(token: string, callbacks: ChatWebSocketCallbacks);
  /**
   * @deprecated Use the callbacks-based constructor instead.
   * Legacy constructor for backward compatibility.
   */
  constructor(
    token: string,
    onMessage: WSMessageHandler,
    onStatusChange: (connected: boolean) => void,
  );
  constructor(
    token: string,
    callbacksOrHandler: ChatWebSocketCallbacks | WSMessageHandler,
    onStatusChange?: (connected: boolean) => void,
  ) {
    this.token = token;

    if (typeof callbacksOrHandler === 'function') {
      // Legacy mode: wrap in callbacks
      this.legacyHandler = callbacksOrHandler;
      this.callbacks = {
        onChunk: () => {},
        onToolStep: () => {},
        onComplete: () => {},
        onError: () => {},
        onStatusChange: onStatusChange ?? (() => {}),
      };
    } else {
      // New mode: typed callbacks
      this.callbacks = callbacksOrHandler;
    }
  }

  connect() {
    if (!WS_URL) return;

    this.intentionalClose = false;
    const url = `${WS_URL}?token=${encodeURIComponent(this.token)}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.debug('[ChatWebSocket] Connected');
      this.reconnectAttempts = 0;
      this.callbacks.onStatusChange(true);
    };

    this.ws.onmessage = (event: MessageEvent) => {
      this._handleMessage(event.data);
    };

    this.ws.onclose = () => {
      this.callbacks.onStatusChange(false);
      this._tryReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  send(prompt: string, sessionId: string, apmId?: string, token?: string): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(
      JSON.stringify({
        action: 'sendMessage',
        data: { prompt, session_id: sessionId, apm_id: apmId, token: token ?? this.token },
      }),
    );
    return true;
  }

  disconnect() {
    this.intentionalClose = true;
    this.ws?.close();
    this.ws = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  updateToken(token: string) {
    this.token = token;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Private methods
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Parse and dispatch incoming WebSocket messages based on `type` field.
   * Handles malformed messages gracefully (logs warning, doesn't crash).
   */
  private _handleMessage(raw: string) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      console.warn('[ChatWebSocket] Failed to parse message:', raw);
      return;
    }

    // Validate that parsed is an object with a type field
    if (!parsed || typeof parsed !== 'object' || !('type' in parsed)) {
      console.warn('[ChatWebSocket] Message missing "type" field:', parsed);
      return;
    }

    const msg = parsed as WsServerChunk;

    // Dispatch to legacy handler if present (backward compat)
    if (this.legacyHandler) {
      this.legacyHandler(parsed as WSMessage);
    }

    // Dispatch to typed callbacks based on message type
    switch (msg.type) {
      case 'chunk':
        this.callbacks.onChunk(msg.text);
        break;

      case 'tool_step':
        this.callbacks.onToolStep(msg.tool, msg.label);
        break;

      case 'complete':
        this.callbacks.onComplete(msg.payload);
        break;

      case 'error':
        this.callbacks.onError(msg.message, msg.code);
        break;

      default:
        console.warn(
          '[ChatWebSocket] Unknown message type:',
          (parsed as Record<string, unknown>).type,
        );
        break;
    }
  }

  private _tryReconnect() {
    if (this.intentionalClose) return;
    this.reconnectAttempts++;
    const delay = Math.min(this.baseDelay * Math.pow(2, this.reconnectAttempts - 1), this.maxDelay);
    console.debug(`[ChatWebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    setTimeout(() => this.connect(), delay);
  }
}
