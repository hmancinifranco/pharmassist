import { Sha256 } from '@aws-crypto/sha256-js';
import { SignatureV4 } from '@smithy/signature-v4';
import { HttpRequest } from '@smithy/protocol-http';
import type { VoiceState } from '../components/Voice/ParticleSphere';
import { getAwsCredentials, isCacheValid, type AwsCredentials } from './credentials';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const REGION = import.meta.env.VITE_AWS_REGION ?? 'us-east-1';
const BIDIAGENT_ARN = import.meta.env.VITE_BIDIAGENT_AGENT_ARN ?? '';
const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 16000;
const CHUNK_SIZE = 4096; // samples per chunk
const PRESIGNED_URL_EXPIRY = 300; // 5 minutes
const SESSION_TIMEOUT_MS = 8 * 60 * 1000; // 8 minutes (Nova Sonic limit)
const CREDENTIAL_CHECK_INTERVAL_MS = 60 * 1000; // check credentials every 60s

// ---------------------------------------------------------------------------
// Error classification
// ---------------------------------------------------------------------------

/** Error types for differentiated handling. */
export type VoiceErrorType = 'microphone' | 'credentials' | 'nova_sonic' | 'connection' | 'timeout';

export interface VoiceError {
  type: VoiceErrorType;
  message: string;
  /** If true, the voice button should be disabled until re-login. */
  disableVoice?: boolean;
  /** If true, offer the user to switch to text chat. */
  offerTextChat?: boolean;
  /** If true, offer the user to reconnect. */
  offerReconnect?: boolean;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type VoiceStateChangeHandler = (state: VoiceState) => void;
export type AudioLevelHandler = (level: number) => void;

export interface VoiceServiceCallbacks {
  onStateChange: VoiceStateChangeHandler;
  onAudioLevel: AudioLevelHandler;
  onError: (message: string) => void;
  /** Structured error with type info for richer UI handling. */
  onVoiceError?: (error: VoiceError) => void;
  onDisconnect: () => void;
}

// ---------------------------------------------------------------------------
// Helpers — exported for testing
// ---------------------------------------------------------------------------

/** Extract the agent ID from a Bedrock AgentCore ARN. */
export function extractAgentId(arn: string): string {
  const match = /\/([^/]+)$/.exec(arn);
  return match ? match[1] : arn;
}

/** Convert Float32 audio samples to Int16 PCM. */
export function float32ToInt16(input: Float32Array): Int16Array {
  const pcm = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm;
}

/** Convert Int16 PCM to Float32 audio samples. */
export function int16ToFloat32(input: Int16Array): Float32Array {
  const float = new Float32Array(input.length);
  for (let i = 0; i < input.length; i++) {
    float[i] = input[i] / 0x8000;
  }
  return float;
}

/** Encode an Int16Array to base64 string. */
export function int16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/** Decode a base64 string to Int16Array. */
export function base64ToInt16(b64: string): Int16Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer);
}

/**
 * Map a BidiAgent response event to a UI VoiceState.
 * Returns null if the event doesn't trigger a state change.
 */
export function mapEventToState(event: Record<string, unknown>): VoiceState | null {
  if ('contentStart' in event) {
    const cs = event.contentStart as Record<string, unknown>;
    if (cs.role === 'ASSISTANT' && cs.type === 'AUDIO') return 'speaking';
    return null;
  }
  if ('textOutput' in event) {
    const to = event.textOutput as Record<string, unknown>;
    // Barge-in detection
    if (to.content && typeof to.content === 'string') {
      try {
        const parsed = JSON.parse(to.content);
        if (parsed.interrupted === true) return 'listening';
      } catch {
        // not JSON, continue
      }
    }
    if (to.role === 'USER') return 'listening';
    return null;
  }
  if ('toolUse' in event) return 'thinking';
  if ('contentEnd' in event) {
    const ce = event.contentEnd as Record<string, unknown>;
    if (ce.type === 'AUDIO' && ce.role === 'ASSISTANT') return 'listening';
    return null;
  }
  return null;
}

/**
 * Compute backoff delay for reconnection attempt N (1-based).
 * Returns delay in ms, or -1 if no more retries.
 */
export function backoffDelay(attempt: number, baseDelay = 1000): number {
  if (attempt < 1 || attempt > 3) return -1;
  return baseDelay * Math.pow(2, attempt - 1);
}

/**
 * Wrap a single event value into the BidiAgent protocol envelope.
 * Returns `{"event": {<eventType>: <payload>}}`.
 */
export function wrapEvent(eventType: string, payload: unknown): string {
  return JSON.stringify({ event: { [eventType]: payload } });
}

// ---------------------------------------------------------------------------
// Presigned WebSocket URL generation (SigV4)
// ---------------------------------------------------------------------------

/**
 * Generate a SigV4 presigned WebSocket URL for connecting to a BidiAgent
 * in AgentCore.
 */
export async function generatePresignedUrl(
  credentials: AwsCredentials,
  region: string,
  agentArn: string,
): Promise<string> {
  const encodedArn = encodeURIComponent(agentArn);
  const host = `bedrock-agentcore.${region}.amazonaws.com`;
  const path = `/runtimes/${encodedArn}/ws`;

  // Generate a session ID (must be at least 33 chars per AWS requirements)
  const sessionId = crypto.randomUUID();

  const signer = new SignatureV4({
    service: 'bedrock-agentcore',
    region,
    credentials: {
      accessKeyId: credentials.accessKeyId,
      secretAccessKey: credentials.secretAccessKey,
      sessionToken: credentials.sessionToken,
    },
    sha256: Sha256,
  });

  // Sign with https: protocol (matching the official sample), then convert to wss:
  const request = new HttpRequest({
    method: 'GET',
    protocol: 'https:',
    hostname: host,
    path,
    headers: { host },
    query: {
      'qualifier': 'DEFAULT',
      'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': sessionId,
    },
  });

  const presigned = await signer.presign(request, { expiresIn: PRESIGNED_URL_EXPIRY });
  const queryString = Object.entries(presigned.query as Record<string, string>)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&');
  return `wss://${host}${path}?${queryString}`;
}

// ---------------------------------------------------------------------------
// VoiceService — WebSocket SigV4 connection to AgentCore BidiAgent
// ---------------------------------------------------------------------------

export class VoiceService {
  private ws: WebSocket | null = null;
  private audioContext: AudioContext | null = null;
  private playbackContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private processorNode: ScriptProcessorNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private isPlaying = false;
  private muted = false;
  private callbacks: VoiceServiceCallbacks;
  private idToken: string;
  // @ts-ignore - apmId will be used when BidiAgent session context is implemented
  private apmId: string;
  private sessionTimer: ReturnType<typeof setTimeout> | null = null;
  private credentialCheckTimer: ReturnType<typeof setInterval> | null = null;

  // Reconnection state
  private reconnectAttempt = 0;
  private isDisconnecting = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private cachedCredentials: AwsCredentials | null = null;

  constructor(idToken: string, apmId: string, callbacks: VoiceServiceCallbacks) {
    this.idToken = idToken;
    this.apmId = apmId;
    this.callbacks = callbacks;
  }

  // ── Public API ──────────────────────────────────────────────────────────

  async connect(): Promise<void> {
    if (!BIDIAGENT_ARN) {
      this.callbacks.onError('ARN del BidiAgent no configurado.');
      return;
    }

    this.isDisconnecting = false;
    this.reconnectAttempt = 0;

    try {
      // 1. Get AWS temporary credentials
      this.cachedCredentials = await getAwsCredentials(this.idToken);
    } catch {
      this._emitVoiceError({
        type: 'credentials',
        message: 'No se pudieron obtener credenciales para el modo voz. Intentá reloguearte.',
        disableVoice: true,
      });
      this.callbacks.onDisconnect();
      return;
    }

    // 2. Request microphone before connecting WebSocket
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: INPUT_SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
    } catch {
      this._emitVoiceError({
        type: 'microphone',
        message: 'Se necesita acceso al micrófono para el modo voz.',
      });
      this.callbacks.onDisconnect();
      return;
    }

    // 3. Pre-create playback AudioContext during user gesture (required for mobile)
    // Don't force sampleRate — let the browser use the hardware default.
    // Audio buffers specify their own sampleRate and the browser resamples.
    if (!this.playbackContext || this.playbackContext.state === 'closed') {
      this.playbackContext = new AudioContext();
    }
    if (this.playbackContext.state === 'suspended') {
      await this.playbackContext.resume();
    }

    // 4. Connect WebSocket
    await this._connectWebSocket();
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    // Disable/enable the microphone track directly for true muting
    if (this.mediaStream) {
      this.mediaStream.getAudioTracks().forEach((track) => {
        track.enabled = !muted;
      });
    }
  }

  disconnect(): void {
    this.isDisconnecting = true;
    this._clearReconnectTimer();
    this._clearSessionTimer();
    this._clearCredentialCheckTimer();
    this._closeWebSocket();
    this._stopMicrophone();
    this._stopPlayback();
    this._closeAudioContexts();
  }

  // ── Internal WebSocket connection ───────────────────────────────────────

  /**
   * Establish the WebSocket connection. Used for both initial connect and
   * reconnection attempts. Credentials and microphone must already be acquired.
   */
  private async _connectWebSocket(): Promise<void> {
    try {
      // Ensure credentials are fresh
      if (!this.cachedCredentials || !isCacheValid(this.cachedCredentials.expiration)) {
        this.cachedCredentials = await getAwsCredentials(this.idToken);
      }

      const url = await generatePresignedUrl(this.cachedCredentials, REGION, BIDIAGENT_ARN);

      this._closeWebSocket(); // clean up any previous socket
      this.ws = new WebSocket(url);
      this.ws.onopen = () => this._onOpen();
      this.ws.onmessage = (e) => this._onMessage(e);
      this.ws.onerror = () => {
        // onerror is always followed by onclose, so we handle reconnection there
      };
      this.ws.onclose = (ev) => this._onClose(ev);
    } catch (err) {
      // Credential renewal failure during reconnection
      const isCredentialError =
        err instanceof Error &&
        err.message.includes('credenciales');

      if (isCredentialError) {
        this._emitVoiceError({
          type: 'credentials',
          message: 'No se pudieron obtener credenciales para el modo voz. Intentá reloguearte.',
          disableVoice: true,
        });
        this._fullCleanup();
        this.callbacks.onDisconnect();
      } else {
        // Try reconnecting
        this._attemptReconnect();
      }
    }
  }

  // ── WebSocket event handlers ────────────────────────────────────────────

  private async _onOpen(): Promise<void> {
    // Reset reconnection state on successful connect
    this.reconnectAttempt = 0;

    // Start 8-minute session timer
    this._startSessionTimer();

    // Start credential renewal checker
    this._startCredentialCheck();

    // Send init message with apm_id so the BidiAgent can identify the user
    this._sendRaw({ type: 'init', apm_id: this.apmId });

    // Start microphone capture (reuse existing mediaStream if reconnecting)
    if (!this.processorNode) {
      await this._startMicrophone();
    }
  }

  private _onMessage(event: MessageEvent): void {
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(event.data as string) as Record<string, unknown>;
    } catch {
      return; // ignore malformed events
    }

    const eventType = data.type as string | undefined;

    // Handle errors
    if (eventType === 'error' || 'error' in data) {
      this._emitVoiceError({
        type: 'nova_sonic',
        message: 'El asistente de voz no está disponible.',
        offerTextChat: true,
      });
      this._fullCleanup();
      this.callbacks.onDisconnect();
      return;
    }

    // Handle audio output from BidiAgent
    if (eventType === 'bidi_audio_stream' && data.audio && typeof data.audio === 'string') {
      this._enqueueAudio(data.audio);
      this.callbacks.onStateChange('speaking');
    }

    // Handle tool use — agent is consulting data
    if (eventType === 'bidi_tool_use' || eventType === 'bidi_tool_start') {
      this.callbacks.onStateChange('thinking');
    }

    // Handle transcripts
    if (eventType === 'bidi_transcript_stream') {
      const role = data.role as string;
      if (role === 'user') {
        this.callbacks.onStateChange('listening');
      }
      // When user transcript is final, switch to thinking (agent is processing)
      if (role === 'user' && data.is_final === true) {
        this.callbacks.onStateChange('thinking');
      }
    }

    // Handle text responses (final assistant text)
    if (eventType === 'bidi_text_response') {
      // Assistant finished speaking
      this.callbacks.onStateChange('listening');
    }

    // Handle interruptions (barge-in)
    if (eventType === 'bidi_interruption') {
      this.callbacks.onStateChange('listening');
      if (this.isPlaying) {
        this._stopPlayback();
      }
    }
  }

  private _onClose(_ev?: CloseEvent): void {
    this._clearSessionTimer();
    this._clearCredentialCheckTimer();

    // If this was a deliberate disconnect, just clean up
    if (this.isDisconnecting) {
      this._stopMicrophone();
      this._stopPlayback();
      this._closeAudioContexts();
      this.callbacks.onDisconnect();
      return;
    }

    // Unexpected close — attempt reconnection
    this._stopPlayback();
    this._attemptReconnect();
  }

  // ── Reconnection with exponential backoff ───────────────────────────────

  private _attemptReconnect(): void {
    this.reconnectAttempt++;
    const delay = backoffDelay(this.reconnectAttempt);

    if (delay === -1) {
      // Max retries exceeded
      this._emitVoiceError({
        type: 'connection',
        message: 'No se pudo conectar al asistente de voz. Verificá tu conexión.',
        offerReconnect: true,
      });
      this._fullCleanup();
      this.callbacks.onDisconnect();
      return;
    }

    this.callbacks.onStateChange('idle');

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this._connectWebSocket();
    }, delay);
  }

  private _clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  // ── Protocol events (client → server) ───────────────────────────────────

  private _sendRaw(payload: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  private _sendAudioInput(base64Chunk: string): void {
    this._sendRaw({
      type: 'bidi_audio_input',
      audio: base64Chunk,
      format: 'pcm',
      sample_rate: INPUT_SAMPLE_RATE,
      channels: 1,
    });
  }

  // ── Microphone capture ──────────────────────────────────────────────────

  private async _startMicrophone(): Promise<void> {
    // mediaStream is acquired in connect() before WebSocket setup.
    // If it's missing here, something went wrong.
    if (!this.mediaStream) {
      this._emitVoiceError({
        type: 'microphone',
        message: 'Se necesita acceso al micrófono para el modo voz.',
      });
      return;
    }

    this.audioContext = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE });
    this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);

    // ScriptProcessorNode for broad compatibility
    const processor = this.audioContext.createScriptProcessor(CHUNK_SIZE, 1, 1);
    this.processorNode = processor;

    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);

      // Compute RMS audio level for UI
      let sum = 0;
      for (let i = 0; i < input.length; i++) {
        sum += input[i] * input[i];
      }
      const rms = Math.sqrt(sum / input.length);
      const level = Math.min(1, rms * 5);
      this.callbacks.onAudioLevel(level);

      // Send PCM to BidiAgent if not muted
      if (!this.muted && this.ws?.readyState === WebSocket.OPEN) {
        const pcm = float32ToInt16(input);
        const b64 = int16ToBase64(pcm);
        this._sendAudioInput(b64);
      }
    };

    this.sourceNode.connect(processor);
    processor.connect(this.audioContext.destination);
  }

  private _stopMicrophone(): void {
    if (this.processorNode) {
      this.processorNode.disconnect();
      this.processorNode = null;
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }
  }

  // ── Audio playback ──────────────────────────────────────────────────────

  private nextPlayTime = 0;

  private _enqueueAudio(base64Chunk: string): void {
    // Create playback context if needed (should already exist from connect())
    if (!this.playbackContext || this.playbackContext.state === 'closed') {
      this.playbackContext = new AudioContext();
    }
    // Resume if suspended (mobile browsers)
    if (this.playbackContext.state === 'suspended') {
      this.playbackContext.resume();
    }

    const int16 = base64ToInt16(base64Chunk);
    const float32 = int16ToFloat32(int16);

    const buffer = this.playbackContext.createBuffer(1, float32.length, OUTPUT_SAMPLE_RATE);
    buffer.getChannelData(0).set(float32);

    const source = this.playbackContext.createBufferSource();
    source.buffer = buffer;
    source.connect(this.playbackContext.destination);

    const now = this.playbackContext.currentTime;
    const startTime = Math.max(now, this.nextPlayTime);
    source.start(startTime);
    this.nextPlayTime = startTime + buffer.duration;
    this.isPlaying = true;

    source.onended = () => {
      if (
        this.playbackContext &&
        this.playbackContext.currentTime >= this.nextPlayTime - 0.01
      ) {
        this.isPlaying = false;
      }
    };
  }

  private _stopPlayback(): void {
    this.isPlaying = false;
    this.nextPlayTime = 0;
    // Close and recreate playback context to stop all scheduled audio
    if (this.playbackContext) {
      this.playbackContext.close().catch(() => {});
      this.playbackContext = null;
    }
  }

  // ── Session timer (8 min Nova Sonic limit) ──────────────────────────────

  private _startSessionTimer(): void {
    this._clearSessionTimer();
    this.sessionTimer = setTimeout(() => {
      this._emitVoiceError({
        type: 'timeout',
        message: 'La sesión de voz expiró. Podés iniciar una nueva.',
        offerReconnect: true,
      });
      this.isDisconnecting = true; // prevent reconnection on close
      this.disconnect();
    }, SESSION_TIMEOUT_MS);
  }

  private _clearSessionTimer(): void {
    if (this.sessionTimer) {
      clearTimeout(this.sessionTimer);
      this.sessionTimer = null;
    }
  }

  // ── Credential renewal during active session ────────────────────────────

  private _startCredentialCheck(): void {
    this._clearCredentialCheckTimer();
    this.credentialCheckTimer = setInterval(async () => {
      if (!this.cachedCredentials) return;

      // If credentials expire within 5 minutes, renew them proactively
      if (!isCacheValid(this.cachedCredentials.expiration)) {
        try {
          this.cachedCredentials = await getAwsCredentials(this.idToken);
        } catch {
          // Credential renewal failed — the current session may still work
          // until the WebSocket connection drops, at which point reconnection
          // will handle it.
        }
      }
    }, CREDENTIAL_CHECK_INTERVAL_MS);
  }

  private _clearCredentialCheckTimer(): void {
    if (this.credentialCheckTimer) {
      clearInterval(this.credentialCheckTimer);
      this.credentialCheckTimer = null;
    }
  }

  // ── Cleanup helpers ─────────────────────────────────────────────────────

  private _closeWebSocket(): void {
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }
  }

  private _closeAudioContexts(): void {
    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }
    if (this.playbackContext) {
      this.playbackContext.close().catch(() => {});
      this.playbackContext = null;
    }
  }

  /** Full cleanup of all resources — used when giving up on reconnection. */
  private _fullCleanup(): void {
    this._clearReconnectTimer();
    this._clearSessionTimer();
    this._clearCredentialCheckTimer();
    this._closeWebSocket();
    this._stopMicrophone();
    this._stopPlayback();
    this._closeAudioContexts();
    this.cachedCredentials = null;
  }

  // ── Error emission ──────────────────────────────────────────────────────

  /** Emit a structured error via onVoiceError (if available) and always via onError. */
  private _emitVoiceError(error: VoiceError): void {
    this.callbacks.onError(error.message);
    this.callbacks.onVoiceError?.(error);
  }
}
