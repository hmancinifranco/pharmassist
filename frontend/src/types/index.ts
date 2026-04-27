/** Frecuencia esperada de visitas a un médico */
export type Cadencia = 'Mensual' | 'Trimestral' | 'Semestral' | 'Anual' | 'Digital';

/** Modalidad de la visita */
export type TipoVisita = 'Presencial' | 'Virtual' | 'Telefónica';

/** Médico registrado en el CRM */
export interface Medico {
  medico_mn: number;
  nombre: string;
  apellido: string;
  especialidad_medica: string;
  zona: string;
  apm: string;
  cadencia: Cadencia;
  fecha_nacimiento?: string;
  fecha_ultima_visita?: string;
  telefono_celular?: string;
  calle?: string;
  altura?: string;
  barrio?: string;
  latitud?: number;
  longitud?: number;
  hobby_intereses?: string;
  religion?: string;
  hospital?: string;
  facultad?: string;
}

/** Estado de una visita planificada */
export type EstadoVisita = 'Pendiente' | 'Completada' | 'Vencida';

/** Visita planificada en la agenda del APM */
export interface VisitaPlanificada {
  apm: string;
  medico_mn: number;
  fecha_planificada: string;
  zona: string;
  tipo_visita: TipoVisita;
  productos_sugeridos: string[];
  estado?: EstadoVisita;
  medico?: Medico;
}

/** Entrada de cumpleaños próximo */
export interface CumpleañosEntry {
  medico: Medico;
  dias_hasta: number;
  mensaje_cumpleanos?: string;
}

/** Alerta de SLA de visita vencida */
export interface AlertaSLA {
  medico: Medico;
  cadencia: Cadencia;
  fecha_ultima_visita?: string;
  dias_vencido: number;
}

/** Mensaje en el chat conversacional */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sources?: string[];
}

/** Minuta de visita generada por IA */
export interface MinutaVisita {
  minuta_id: string;
  medico_mn: number;
  fecha_creacion: string;
  transcripcion: string;
  resumen: string;
  productos_discutidos: string[];
  compromisos?: string;
  proximos_pasos?: string;
  audio_s3_key?: string;
  estado?: 'procesando' | 'listo' | 'error';
}
