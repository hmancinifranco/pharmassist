import { create } from 'zustand';
import type {
  VisitaPlanificada,
  CumpleañosEntry,
  AlertaSLA,
  ChatMessage,
  Medico,
} from '../types';
import {
  getVisitsToday,
  getBirthdays,
  getSlaAlerts,
  sendChatMessage,
  completeVisit as apiCompleteVisit,
  generateBirthdayMessage as apiGenerateBirthdayMessage,
} from '../api/client';
import { ChatWebSocket, type WSMessage } from '../api/websocket';
import useAuthStore from './useAuthStore';

// ── Store shape ─────────────────────────────────────────────────────────────

interface AppState {
  // APM identity
  apmId: string;

  // Dashboard data
  visits: VisitaPlanificada[];
  birthdays: CumpleañosEntry[];
  alerts: AlertaSLA[];

  // Chat
  chatMessages: ChatMessage[];
  sessionId: string;
  streamingContent: string;
  toolSteps: string[];

  // WebSocket
  wsConnected: boolean;
  wsInstance: ChatWebSocket | null;
  fallbackActive: boolean;

  // Loading flags
  visitsLoading: boolean;
  birthdaysLoading: boolean;
  alertsLoading: boolean;
  chatLoading: boolean;

  // Error flags
  visitsError: string | null;
  birthdaysError: string | null;
  alertsError: string | null;
  chatError: string | null;

  // Actions
  setApmId: (id: string) => void;
  fetchVisitsToday: () => Promise<void>;
  fetchBirthdays: () => Promise<void>;
  fetchSlaAlerts: () => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  completeVisit: (fechaPlanificada: string, medicoMn: number) => Promise<void>;
  generateBirthdayMessage: (medicoMn: number) => Promise<void>;
  addChatMessage: (msg: ChatMessage) => void;
  clearChat: () => void;
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
  retryWebSocket: () => void;
}

// ── Response transformers ───────────────────────────────────────────────────

/**
 * Transform backend visit item (flat fields) into the VisitaPlanificada shape
 * expected by the frontend, with a nested `medico` object.
 */
function transformVisit(raw: Record<string, unknown>): VisitaPlanificada {
  const productos = raw.Productos_Sugeridos;
  let productosList: string[] = [];
  if (typeof productos === 'string') {
    productosList = productos.split('|').map((p: string) => p.trim()).filter(Boolean);
  } else if (Array.isArray(productos)) {
    productosList = productos as string[];
  }

  const medico: Medico | undefined =
    raw.Medico_Nombre || raw.Medico_Apellido
      ? {
          medico_mn: (raw.Medico_MN as number) ?? 0,
          nombre: (raw.Medico_Nombre as string) ?? '',
          apellido: (raw.Medico_Apellido as string) ?? '',
          especialidad_medica: (raw.Especialidad_Medica as string) ?? '',
          zona: (raw.Zona as string) ?? '',
          apm: (raw.APM as string) ?? '',
          cadencia: (raw.Cadencia as Medico['cadencia']) ?? 'Mensual',
          calle: (raw.Calle as string) ?? undefined,
          altura: (raw.Altura as string) ?? undefined,
          barrio: (raw.Barrio as string) ?? undefined,
          latitud: raw.Latitud != null ? Number(raw.Latitud) : undefined,
          longitud: raw.Longitud != null ? Number(raw.Longitud) : undefined,
        }
      : undefined;

  return {
    apm: (raw.APM as string) ?? '',
    medico_mn: (raw.Medico_MN as number) ?? 0,
    fecha_planificada: (raw.Fecha_Planificada as string) ?? '',
    zona: (raw.Zona as string) ?? '',
    tipo_visita: (raw.Tipo_Visita as VisitaPlanificada['tipo_visita']) ?? 'Presencial',
    productos_sugeridos: productosList,
    estado: (raw.Estado as VisitaPlanificada['estado']) ?? 'Pendiente',
    medico,
  };
}

/**
 * Transform backend SLA alert item (flat fields) into the AlertaSLA shape
 * expected by the frontend, with a nested `medico` object.
 */
function transformAlert(raw: Record<string, unknown>): AlertaSLA {
  // Backend returns flat: nombre, especialidad, cadencia, fecha_ultima_visita, dias_vencido, zona
  // Frontend expects nested medico object
  const fullName = (raw.nombre as string) ?? '';
  const nameParts = fullName.split(' ');
  const nombre = nameParts[0] ?? '';
  const apellido = nameParts.slice(1).join(' ') ?? '';

  return {
    medico: {
      medico_mn: (raw.medico_mn as number) ?? 0,
      nombre,
      apellido,
      especialidad_medica: (raw.especialidad as string) ?? '',
      zona: (raw.zona as string) ?? '',
      apm: '',
      cadencia: (raw.cadencia as Medico['cadencia']) ?? 'Mensual',
    },
    cadencia: (raw.cadencia as AlertaSLA['cadencia']) ?? 'Mensual',
    fecha_ultima_visita: (raw.fecha_ultima_visita as string) ?? undefined,
    dias_vencido: (raw.dias_vencido as number) ?? 0,
  };
}

// ── Timeout helper ──────────────────────────────────────────────────────────

const CHAT_TIMEOUT_MS = 120_000;

// ── WebSocket message handler (defined outside store to avoid closures) ─────

let _chatTimeoutId: ReturnType<typeof setTimeout> | null = null;
let _streamingMsgId: string | null = null;

function _handleWSMessage(msg: WSMessage) {
  const state = useAppStore.getState();

  // Legacy "tools" format (array of step labels)
  if (msg.type === 'tools' && msg.steps) {
    useAppStore.setState({ toolSteps: msg.steps });
    return;
  }

  // New WsServerChunk: tool_step (single tool indicator)
  if (msg.type === 'tool_step' && msg.label) {
    useAppStore.setState((s) => ({
      toolSteps: [...s.toolSteps, msg.label!],
    }));
    return;
  }

  if (msg.type === 'chunk' && (msg.content || msg.text)) {
    const chunkText = msg.content ?? msg.text ?? '';
    const newContent = state.streamingContent + chunkText;
    // Upsert the streaming assistant message
    if (!_streamingMsgId) {
      _streamingMsgId = crypto.randomUUID();
      const assistantMsg: ChatMessage = {
        id: _streamingMsgId,
        role: 'assistant',
        content: newContent,
        timestamp: new Date().toISOString(),
      };
      useAppStore.setState((s) => ({
        streamingContent: newContent,
        chatMessages: [...s.chatMessages, assistantMsg],
      }));
    } else {
      useAppStore.setState((s) => ({
        streamingContent: newContent,
        chatMessages: s.chatMessages.map((m) =>
          m.id === _streamingMsgId ? { ...m, content: newContent } : m,
        ),
      }));
    }
    return;
  }

  if (msg.type === 'complete') {
    if (_chatTimeoutId) {
      clearTimeout(_chatTimeoutId);
      _chatTimeoutId = null;
    }

    // New WsServerChunk: "complete" carries a payload with AgentResponse
    const payload = msg.payload;
    if (payload && _streamingMsgId) {
      // Update the streaming message with final content and structured data
      const finalContent = payload.result ?? state.streamingContent;
      useAppStore.setState((s) => ({
        chatMessages: s.chatMessages.map((m) =>
          m.id === _streamingMsgId
            ? { ...m, content: finalContent, structured: payload.structured }
            : m,
        ),
        chatLoading: false,
        streamingContent: '',
        toolSteps: [],
      }));
    } else if (payload && !_streamingMsgId) {
      // No streaming happened — insert complete message directly
      const completeMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: payload.result ?? '',
        timestamp: new Date().toISOString(),
        structured: payload.structured,
      };
      useAppStore.setState((s) => ({
        chatMessages: [...s.chatMessages, completeMsg],
        chatLoading: false,
        streamingContent: '',
        toolSteps: [],
      }));
    } else {
      // Legacy complete (no payload) — just finalize
      useAppStore.setState({
        chatLoading: false,
        streamingContent: '',
        toolSteps: [],
      });
    }
    _streamingMsgId = null;
    return;
  }

  if (msg.type === 'error' && msg.message) {
    if (_chatTimeoutId) {
      clearTimeout(_chatTimeoutId);
      _chatTimeoutId = null;
    }
    const errorMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: msg.message,
      timestamp: new Date().toISOString(),
      isError: true,
    };
    useAppStore.setState((s) => ({
      chatMessages: [...s.chatMessages, errorMsg],
      chatLoading: false,
      streamingContent: '',
      toolSteps: [],
    }));
    _streamingMsgId = null;
  }
}

function _handleWSStatusChange(connected: boolean) {
  console.debug('[PharmAssist] WebSocket status:', connected ? 'connected' : 'disconnected');
  useAppStore.setState({ wsConnected: connected });

  if (connected) {
    // WS reconnected — deactivate fallback
    useAppStore.setState({ fallbackActive: false });
    console.debug('[PharmAssist] WebSocket reconnected, fallback deactivated');
  } else {
    // WS disconnected — activate HTTP fallback during reconnection
    useAppStore.setState({ fallbackActive: true });
    console.debug('[PharmAssist] WebSocket disconnected, HTTP fallback active');
  }

  // If disconnected mid-stream, append "(respuesta incompleta)"
  if (!connected) {
    const state = useAppStore.getState();
    if (state.chatLoading && state.streamingContent && _streamingMsgId) {
      const partial = state.streamingContent + ' (respuesta incompleta)';
      useAppStore.setState((s) => ({
        chatMessages: s.chatMessages.map((m) =>
          m.id === _streamingMsgId ? { ...m, content: partial } : m,
        ),
        chatLoading: false,
        streamingContent: '',
        toolSteps: [],
      }));
      if (_chatTimeoutId) {
        clearTimeout(_chatTimeoutId);
        _chatTimeoutId = null;
      }
      _streamingMsgId = null;
    }
  }
}

// ── Store implementation ────────────────────────────────────────────────────

const useAppStore = create<AppState>((set, get) => ({
  apmId: 'Demo APM',

  visits: [],
  birthdays: [],
  alerts: [],

  chatMessages: [],
  sessionId: crypto.randomUUID(),
  streamingContent: '',
  toolSteps: [],

  wsConnected: false,
  wsInstance: null,
  fallbackActive: false,

  visitsLoading: false,
  birthdaysLoading: false,
  alertsLoading: false,
  chatLoading: false,

  visitsError: null,
  birthdaysError: null,
  alertsError: null,
  chatError: null,

  setApmId: (id) => set({ apmId: id }),

  connectWebSocket: () => {
    const token = useAuthStore.getState().getIdToken();
    if (!token) return;

    // Disconnect existing instance if any
    get().wsInstance?.disconnect();

    const ws = new ChatWebSocket(token, _handleWSMessage, _handleWSStatusChange);
    set({ wsInstance: ws });
    ws.connect();
  },

  disconnectWebSocket: () => {
    get().wsInstance?.disconnect();
    set({ wsInstance: null, wsConnected: false });
  },

  retryWebSocket: () => {
    get().connectWebSocket();
  },

  fetchVisitsToday: async () => {
    set({ visitsLoading: true, visitsError: null });
    try {
      const res = await getVisitsToday(get().apmId);
      const visits = (res.visits as unknown as Record<string, unknown>[]).map(transformVisit);
      set({ visits });
    } catch {
      set({ visitsError: 'No se pudo conectar con el servidor. Verificá tu conexión.' });
    } finally {
      set({ visitsLoading: false });
    }
  },

  fetchBirthdays: async () => {
    set({ birthdaysLoading: true, birthdaysError: null });
    try {
      const res = await getBirthdays(get().apmId);
      const birthdays: CumpleañosEntry[] = res.birthdays.map((b: CumpleañosEntry) => ({
        medico: b.medico,
        dias_hasta: b.dias_hasta,
        mensaje_cumpleanos: b.mensaje_cumpleanos ?? undefined,
      }));
      set({ birthdays });
    } catch {
      set({ birthdaysError: 'No se pudo conectar con el servidor. Verificá tu conexión.' });
    } finally {
      set({ birthdaysLoading: false });
    }
  },

  fetchSlaAlerts: async () => {
    set({ alertsLoading: true, alertsError: null });
    try {
      const res = await getSlaAlerts(get().apmId);
      const alerts = (res.alerts as unknown as Record<string, unknown>[]).map(transformAlert);
      set({ alerts });
    } catch {
      set({ alertsError: 'No se pudo conectar con el servidor. Verificá tu conexión.' });
    } finally {
      set({ alertsLoading: false });
    }
  },

  sendMessage: async (text) => {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };
    set((s) => ({
      chatMessages: [...s.chatMessages, userMsg],
      chatLoading: true,
      chatError: null,
      streamingContent: '',
      toolSteps: [],
    }));

    const { wsInstance, wsConnected, sessionId, apmId } = get();

    // Try WebSocket first
    if (wsInstance && wsConnected) {
      const token = useAuthStore.getState().getIdToken() ?? '';
      const sent = wsInstance.send(text, sessionId, apmId, token);
      if (sent) {
        console.debug('[PharmAssist] Message sent via WebSocket');
        set({ fallbackActive: false });
        // Set timeout for WS response
        _chatTimeoutId = setTimeout(() => {
          const s = useAppStore.getState();
          if (s.chatLoading) {
            const partial = s.streamingContent;
            if (partial && _streamingMsgId) {
              // Had partial content — mark incomplete
              useAppStore.setState((prev) => ({
                chatMessages: prev.chatMessages.map((m) =>
                  m.id === _streamingMsgId
                    ? { ...m, content: partial + ' (respuesta incompleta)' }
                    : m,
                ),
                chatLoading: false,
                streamingContent: '',
                toolSteps: [],
              }));
            } else {
              // No content at all — timeout message
              const timeoutMsg: ChatMessage = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: 'El asistente está tardando. Intentá de nuevo.',
                timestamp: new Date().toISOString(),
              };
              useAppStore.setState((prev) => ({
                chatMessages: [...prev.chatMessages, timeoutMsg],
                chatLoading: false,
                streamingContent: '',
                toolSteps: [],
              }));
            }
            _streamingMsgId = null;
          }
          _chatTimeoutId = null;
        }, CHAT_TIMEOUT_MS);
        return;
      }
    }

    // HTTP fallback
    console.debug('[PharmAssist] WebSocket unavailable, using HTTP fallback');
    set({ fallbackActive: true });
    const timeoutPromise = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('TIMEOUT')), CHAT_TIMEOUT_MS),
    );

    try {
      const res = await Promise.race([
        sendChatMessage(text, apmId, sessionId),
        timeoutPromise,
      ]);
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: res.response,
        timestamp: new Date().toISOString(),
        sources: res.sources,
        structured: res.structured ?? undefined,
      };
      set((s) => ({
        chatMessages: [...s.chatMessages, assistantMsg],
      }));
    } catch (err) {
      const isTimeout = err instanceof Error && err.message === 'TIMEOUT';
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: isTimeout
          ? 'El asistente está tardando. Intentá de nuevo.'
          : 'No se pudo conectar con el servidor. Verificá tu conexión.',
        timestamp: new Date().toISOString(),
      };
      set((s) => ({ chatMessages: [...s.chatMessages, errorMsg] }));
    } finally {
      set({ chatLoading: false });
    }
  },

  addChatMessage: (msg) => set((s) => ({ chatMessages: [...s.chatMessages, msg] })),

  completeVisit: async (fechaPlanificada, medicoMn) => {
    try {
      await apiCompleteVisit(get().apmId, fechaPlanificada, medicoMn);
      set((s) => ({
        visits: s.visits.map((v) =>
          v.medico_mn === medicoMn && v.fecha_planificada === fechaPlanificada
            ? { ...v, estado: 'Completada' as const }
            : v,
        ),
      }));
    } catch {
      // Silently fail — the user can retry
    }
  },

  generateBirthdayMessage: async (medicoMn) => {
    try {
      const res = await apiGenerateBirthdayMessage(get().apmId, medicoMn);
      set((s) => ({
        birthdays: s.birthdays.map((b) =>
          b.medico.medico_mn === medicoMn
            ? { ...b, mensaje_cumpleanos: res.mensaje }
            : b,
        ),
      }));
    } catch {
      // Silently fail
    }
  },

  clearChat: () =>
    set({
      chatMessages: [],
      sessionId: crypto.randomUUID(),
      streamingContent: '',
      toolSteps: [],
      chatError: null,
    }),
}));

export default useAppStore;
