"""Sales filtering and zone extraction utilities."""

try:
    from backend.models.schemas import Medico, VentaReportada
except ImportError:
    from models.schemas import Medico, VentaReportada  # type: ignore[no-redef]


def filtrar_ventas_declinando(ventas: list[VentaReportada]) -> list[VentaReportada]:
    """Filter sales records with negative YoY growth, sorted ascending.

    Args:
        ventas: List of VentaReportada objects.

    Returns:
        Only records where crecimiento_yoy_pct < 0, sorted by crecimiento_yoy_pct asc.
    """
    declinando = [
        v for v in ventas
        if v.crecimiento_yoy_pct is not None and v.crecimiento_yoy_pct < 0
    ]
    declinando.sort(key=lambda v: v.crecimiento_yoy_pct)  # type: ignore[arg-type]
    return declinando


def extraer_zonas_apm(medicos: list[Medico], apm_id: str) -> list[str]:
    """Extract distinct zones assigned to an APM from CRM data.

    Args:
        medicos: Full list of Medico objects.
        apm_id: APM identifier to filter by.

    Returns:
        Sorted list of distinct Zona values for the given APM.
    """
    zonas = {m.zona for m in medicos if m.apm == apm_id}
    return sorted(zonas)
