/**
 * Tipos para la integración con el CodeAgent (AgentCore runtime).
 *
 * Define las interfaces de respuesta estructurada del agente,
 * el protocolo de streaming por WebSocket, y el payload de request.
 *
 * @see design.md — Componente 1: Unified Agent (AgentCore Runtime)
 */

// ─────────────────────────────────────────────────────────────────────────────
// Datos estructurados en la respuesta del agente
// ─────────────────────────────────────────────────────────────────────────────

/** Serie de datos para gráficos MUI X Charts */
export interface ChartSeries {
  /** Nombre de la columna que contiene los valores numéricos */
  dataKey: string;
  /** Etiqueta visible en la leyenda del gráfico */
  label: string;
}

/** Datos de gráfico para renderizar con MUI X Charts (LineChart o BarChart) */
export interface ChartData {
  /** Tipo de gráfico a renderizar */
  type: 'line' | 'bar';
  /** Nombre de la columna que se usa como eje X (generalmente temporal) */
  xAxis: string;
  /** Series de datos a graficar */
  series: ChartSeries[];
}

/** Datos tabulares para renderizar con MUI DataGrid */
export interface TableData {
  /** Nombres de las columnas */
  columns: string[];
  /** Filas de datos — cada fila es un objeto con claves = nombres de columna */
  rows: Record<string, unknown>[];
}

/**
 * Datos estructurados opcionales que acompañan la respuesta del agente.
 * El frontend renderiza cada campo con el componente correspondiente.
 */
export interface StructuredData {
  /** Datos tabulares para DataGrid (se muestra cuando rows > 2) */
  table?: TableData;
  /** Query SQL generada por el agente (se muestra en toggle "Ver SQL") */
  sql?: string;
  /** Datos de gráfico para MUI X Charts (detectado en queries temporales) */
  chart?: ChartData;
  /** Sugerencias de follow-up contextuales (2-3 chips clickeables) */
  suggestions?: string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Respuesta completa del agente
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Payload completo de respuesta cuando el agente completa el procesamiento.
 * Se recibe como payload del mensaje WsServerChunk type="complete".
 */
export interface AgentResponse {
  /** Texto de respuesta en Markdown */
  result: string;
  /** Datos estructurados opcionales para rendering enriquecido */
  structured?: StructuredData;
  /** Indica si la ejecución fue exitosa */
  success: boolean;
  /** Cantidad de reintentos realizados (0 = éxito en primer intento, max 2) */
  retries: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Protocolo WebSocket — mensajes del servidor al frontend
// ─────────────────────────────────────────────────────────────────────────────

/** Chunk de texto parcial durante streaming progresivo */
export interface WsChunkMessage {
  type: 'chunk';
  /** Fragmento de texto Markdown a acumular */
  text: string;
}

/** Indicador de actividad de herramienta (ej: "Consultando base de datos...") */
export interface WsToolStepMessage {
  type: 'tool_step';
  /** Nombre interno de la herramienta ejecutándose */
  tool: string;
  /** Etiqueta amigable para mostrar al usuario (en español) */
  label: string;
}

/** Mensaje de completitud con la respuesta final del agente */
export interface WsCompleteMessage {
  type: 'complete';
  /** Respuesta completa del agente con datos estructurados */
  payload: AgentResponse;
}

/** Mensaje de error del servidor */
export interface WsErrorMessage {
  type: 'error';
  /** Mensaje de error amigable en español */
  message: string;
  /** Código de error opcional para categorización (ej: "TIMEOUT", "AUTH") */
  code?: string;
}

/**
 * Unión discriminada de todos los tipos de mensaje WebSocket del servidor.
 * Discriminador: campo `type`.
 *
 * Flujo típico:
 * 1. Varios `chunk` → texto progresivo
 * 2. Intercalados con `tool_step` → indicador de herramienta activa
 * 3. Un `complete` final → respuesta completa con structured data
 * 4. O un `error` si algo falla
 */
export type WsServerChunk =
  | WsChunkMessage
  | WsToolStepMessage
  | WsCompleteMessage
  | WsErrorMessage;

// ─────────────────────────────────────────────────────────────────────────────
// Request del frontend al servidor
// ─────────────────────────────────────────────────────────────────────────────

/** Payload enviado desde el frontend al WebSocket para iniciar una consulta */
export interface AgentRequest {
  /** Acción del WebSocket — siempre "sendMessage" para consultas */
  action: 'sendMessage';
  /** Texto del mensaje del APM */
  message: string;
}
