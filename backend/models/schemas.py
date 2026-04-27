from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class Medico(BaseModel):
    medico_mn: int
    nombre: str
    apellido: str
    especialidad_medica: str
    zona: str
    apm: str
    cadencia: str
    fecha_nacimiento: Optional[date] = None
    fecha_ultima_visita: Optional[date] = None
    telefono_celular: Optional[str] = None
    telefono_consultorio: Optional[str] = None
    mail: Optional[str] = None
    hobby_intereses: Optional[str] = None
    religion: Optional[str] = None
    hospital: Optional[str] = None
    facultad: Optional[str] = None
    anio_egresado: Optional[int] = None
    calle: Optional[str] = None
    altura: Optional[str] = None
    barrio: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None


class Visita(BaseModel):
    visita_id: int
    apm: str
    medico_mn: int
    fecha_visita: date
    zona: str
    tipo_visita: str
    productos_presentados: list[str]
    notas: Optional[str] = None


class VentaReportada(BaseModel):
    zona: str
    producto: str
    presentacion: str
    tipo_otc_rx: str
    anio: int
    mes: int
    unidades_vendidas: int
    valor_venta_ars: float
    crecimiento_yoy_pct: Optional[float] = None
    farmacia: Optional[str] = None


class VisitaPlanificada(BaseModel):
    apm: str
    medico_mn: int
    fecha_planificada: date
    zona: str
    tipo_visita: str
    productos_sugeridos: list[str]


class MinutaVisita(BaseModel):
    minuta_id: str
    apm: str
    medico_mn: int
    fecha_creacion: datetime
    transcripcion: str
    resumen: str
    productos_discutidos: list[str]
    compromisos: Optional[str] = None
    proximos_pasos: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    apm_id: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    sources: list[str] = []
    session_id: str
