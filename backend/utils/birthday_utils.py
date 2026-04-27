"""Birthday filtering and sorting utilities."""

from datetime import date
from typing import Optional

try:
    from backend.models.schemas import Medico
except ImportError:
    from models.schemas import Medico  # type: ignore[no-redef]


def dias_hasta_cumpleanos(fecha_nacimiento: date, fecha_referencia: date) -> int:
    """Calculate days until next birthday from a reference date.

    Handles year wrap-around (e.g., ref Dec 15, birthday Jan 10 → 26 days).

    Args:
        fecha_nacimiento: Birth date.
        fecha_referencia: Reference date.

    Returns:
        Number of days until the next birthday (0–365).
    """
    cumple_este_anio = fecha_nacimiento.replace(year=fecha_referencia.year)

    if cumple_este_anio >= fecha_referencia:
        return (cumple_este_anio - fecha_referencia).days

    cumple_proximo_anio = fecha_nacimiento.replace(year=fecha_referencia.year + 1)
    return (cumple_proximo_anio - fecha_referencia).days


def filtrar_cumpleanos_proximos(
    medicos: list[Medico],
    dias_ventana: int = 30,
    fecha_referencia: Optional[date] = None,
) -> list[dict]:
    """Filter médicos with birthdays in the next N days, sorted by proximity.

    Args:
        medicos: List of Medico objects.
        dias_ventana: Number of days to look ahead (default 30).
        fecha_referencia: Reference date. Defaults to today.

    Returns:
        List of dicts with medico and dias_hasta, sorted ascending by dias_hasta.
    """
    if fecha_referencia is None:
        fecha_referencia = date.today()

    resultados: list[dict] = []

    for medico in medicos:
        if medico.fecha_nacimiento is None:
            continue

        dias = dias_hasta_cumpleanos(medico.fecha_nacimiento, fecha_referencia)

        if 0 <= dias <= dias_ventana:
            resultados.append({
                "medico": medico,
                "dias_hasta": dias,
            })

    resultados.sort(key=lambda r: r["dias_hasta"])
    return resultados
