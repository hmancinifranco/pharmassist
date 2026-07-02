import axios from 'axios';
import type {
  VisitaPlanificada,
  CumpleañosEntry,
  AlertaSLA,
  MinutaVisita,
} from '../types';
import useAuthStore from '../stores/useAuthStore';

// ── Axios instance ──────────────────────────────────────────────────────────
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
});

// ── JWT interceptors ────────────────────────────────────────────────────────

// Attach Authorization header with Cognito idToken
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().getIdToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401, attempt token refresh then retry once
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      try {
        await useAuthStore.getState().refresh();
        const newToken = useAuthStore.getState().getIdToken();
        if (newToken) {
          original.headers.Authorization = `Bearer ${newToken}`;
          return api(original);
        }
      } catch {
        useAuthStore.getState().logout();
      }
    }
    return Promise.reject(error);
  },
);

export default api;

// ── Response shapes (match backend) ─────────────────────────────────────────

export interface VisitsTodayResponse {
  visits: VisitaPlanificada[];
}

export interface BirthdaysResponse {
  birthdays: CumpleañosEntry[];
  messages: { medico_mn: number; mensaje: string }[];
}

export interface SlaAlertsResponse {
  alerts: AlertaSLA[];
}

export interface ChatApiResponse {
  response: string;
  sources: string[];
  session_id: string;
  structured?: import('../types/agent').StructuredData | null;
}

export interface AudioUploadResponse {
  transcription: string;
  minuta_draft: MinutaVisita;
}

export interface PresignedUrlResponse {
  upload_url: string;
  audio_key: string;
}

export interface SaveMinutaResponse {
  minuta_id: string;
}

export interface MinutasListResponse {
  minutas: MinutaVisita[];
}

// ── Typed API functions ─────────────────────────────────────────────────────

export async function getVisitsToday(apmId: string): Promise<VisitsTodayResponse> {
  const { data } = await api.get<VisitsTodayResponse>('/api/dashboard/visits-today', {
    params: { apm_id: apmId },
  });
  return data;
}

export async function getBirthdays(apmId: string): Promise<BirthdaysResponse> {
  const { data } = await api.get<BirthdaysResponse>('/api/dashboard/birthdays', {
    params: { apm_id: apmId },
  });
  return data;
}

export async function getSlaAlerts(apmId: string): Promise<SlaAlertsResponse> {
  const { data } = await api.get<SlaAlertsResponse>('/api/dashboard/sla-alerts', {
    params: { apm_id: apmId },
  });
  return data;
}

export async function sendChatMessage(
  message: string,
  apmId: string,
  sessionId?: string | null,
): Promise<ChatApiResponse> {
  const { data } = await api.post<ChatApiResponse>('/api/chat', {
    message,
    apm_id: apmId,
    session_id: sessionId ?? undefined,
  });
  return data;
}

export async function uploadAudio(
  audioFile: Blob,
  medicoMn: number,
): Promise<AudioUploadResponse> {
  const form = new FormData();
  form.append('audio', audioFile);
  form.append('medico_mn', String(medicoMn));

  const { data } = await api.post<AudioUploadResponse>('/api/audio/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60_000, // transcription can take longer
  });
  return data;
}

export async function getPresignedUrl(medicoMn: number): Promise<PresignedUrlResponse> {
  const { data } = await api.get<PresignedUrlResponse>('/api/audio/presigned-url', {
    params: { medico_mn: medicoMn },
  });
  return data;
}

export async function uploadAudioToS3(
  presignedUrl: string,
  audioBlob: Blob,
): Promise<void> {
  await fetch(presignedUrl, {
    method: 'PUT',
    body: audioBlob,
    headers: { 'Content-Type': 'audio/webm' },
  });
}

export async function pollMinutaByAudioKey(
  apmId: string,
  medicoMn: number,
  maxAttempts = 30,
  intervalMs = 4000,
): Promise<MinutaVisita | null> {
  for (let i = 0; i < maxAttempts; i++) {
    const { minutas } = await getMinutas(apmId, medicoMn);
    // Find the most recent minuta with estado "listo"
    const ready = minutas.find(
      (m) => m.estado === 'listo' || (!m.estado && m.resumen),
    );
    if (ready) return ready;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return null;
}

export async function saveMinuta(
  medicoMn: number,
  apmId: string,
  minuta: Omit<MinutaVisita, 'minuta_id'>,
): Promise<SaveMinutaResponse> {
  const { data } = await api.post<SaveMinutaResponse>('/api/minutas', {
    medico_mn: medicoMn,
    apm_id: apmId,
    minuta,
  });
  return data;
}

export async function getMinutas(
  apmId: string,
  medicoMn?: number,
): Promise<MinutasListResponse> {
  const { data } = await api.get<MinutasListResponse>('/api/minutas', {
    params: { apm_id: apmId, ...(medicoMn != null && { medico_mn: medicoMn }) },
  });
  return data;
}

export async function completeVisit(
  apmId: string,
  fechaPlanificada: string,
  medicoMn: number,
): Promise<{ success: boolean; message: string }> {
  const { data } = await api.post<{ success: boolean; message: string }>(
    '/api/dashboard/visits/complete',
    { apm_id: apmId, fecha_planificada: fechaPlanificada, medico_mn: medicoMn },
  );
  return data;
}

export async function generateBirthdayMessage(
  apmId: string,
  medicoMn: number,
): Promise<{ medico_mn: number; mensaje: string }> {
  const { data } = await api.post<{ medico_mn: number; mensaje: string }>(
    '/api/dashboard/birthdays/generate-message',
    { apm_id: apmId, medico_mn: medicoMn },
  );
  return data;
}
