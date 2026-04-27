"""Visit history summary aggregation utilities."""

from collections import Counter
from datetime import date
from typing import Optional

try:
    from backend.models.schemas import Visita
except ImportError:
    from models.schemas import Visita


def resumir_historial_visitas(visitas: list[Visita]) -> dict:
    """Compute an aggregated summary of visit history for a médico.

    Args:
        visitas: List of Visita objects for a single médico.

    Returns:
        Dict with:
        - total_visitas: int
        - fecha_ultima_visita: Optional[str] (ISO date or None)
        - productos_presentados: list[str] (distinct, sorted)
        - distribucion_tipo_visita: dict[str, int] (counts per tipo)
    """
    if not visitas:
        return {
            "total_visitas": 0,
            "fecha_ultima_visita": None,
            "productos_presentados": [],
            "distribucion_tipo_visita": {},
        }

    total = len(visitas)

    fecha_max: Optional[date] = max(v.fecha_visita for v in visitas)

    productos: set[str] = set()
    for v in visitas:
        productos.update(v.productos_presentados)

    tipo_counter: Counter[str] = Counter(v.tipo_visita for v in visitas)

    return {
        "total_visitas": total,
        "fecha_ultima_visita": fecha_max.isoformat() if fecha_max else None,
        "productos_presentados": sorted(productos),
        "distribucion_tipo_visita": dict(tipo_counter),
    }
