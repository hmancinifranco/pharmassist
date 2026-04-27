"""SLA breach calculation utilities for visit cadence compliance."""

from datetime import date
from typing import Optional

try:
    from backend.data.product_catalog import CADENCIA_DIAS
    from backend.models.schemas import Medico
except ImportError:
    from data.product_catalog import CADENCIA_DIAS
    from models.schemas import Medico


def calcular_dias_vencido(
    cadencia: str,
    fecha_ultima_visita: Optional[date],
    fecha_referencia: Optional[date] = None,
) -> tuple[int, str]:
    """Calculate days overdue for a médico given cadencia and last visit date.

    Args:
        cadencia: Visit cadence (Mensual, Trimestral, Semestral, Anual, Digital).
        fecha_ultima_visita: Last visit date, or None if never visited.
        fecha_referencia: Reference date for calculation. Defaults to today.

    Returns:
        Tuple of (days_overdue, display_message).
        days_overdue is positive when overdue, negative/zero when compliant.
        For null fecha_ultima_visita, returns a large overdue value.
    """
    if fecha_referencia is None:
        fecha_referencia = date.today()

    intervalo = CADENCIA_DIAS.get(cadencia)
    if intervalo is None:
        return 0, f"Cadencia desconocida: {cadencia}"

    if fecha_ultima_visita is None:
        return intervalo + 1, "Sin visitas registradas"

    dias_desde_visita = (fecha_referencia - fecha_ultima_visita).days
    dias_vencido = dias_desde_visita - intervalo

    return dias_vencido, f"{dias_vencido} días vencido" if dias_vencido > 0 else "Al día"


def obtener_alertas_sla(
    medicos: list[Medico],
    fecha_referencia: Optional[date] = None,
) -> list[dict]:
    """Filter médicos with SLA breaches and sort by days overdue descending.

    Args:
        medicos: List of Medico objects to evaluate.
        fecha_referencia: Reference date. Defaults to today.

    Returns:
        List of dicts with medico data and breach info, sorted by dias_vencido desc.
    """
    alertas: list[dict] = []

    for medico in medicos:
        dias_vencido, mensaje = calcular_dias_vencido(
            medico.cadencia,
            medico.fecha_ultima_visita,
            fecha_referencia,
        )

        if dias_vencido > 0:
            alertas.append({
                "medico": medico,
                "cadencia": medico.cadencia,
                "fecha_ultima_visita": (
                    medico.fecha_ultima_visita.isoformat()
                    if medico.fecha_ultima_visita
                    else None
                ),
                "dias_vencido": dias_vencido,
                "mensaje": mensaje,
            })

    alertas.sort(key=lambda a: a["dias_vencido"], reverse=True)
    return alertas
