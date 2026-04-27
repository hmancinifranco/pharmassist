"""
Herramientas Strands para búsqueda web de información pública de médicos.

Usa DDGS (metabuscador open source, sin API key) para buscar publicaciones,
afiliaciones hospitalarias y logros profesionales de médicos.
"""

import logging
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)


@tool
def buscar_info_publica_medico(
    nombre: str,
    apellido: str,
    especialidad: str,
    hospital: str = "",
) -> dict[str, Any]:
    """
    Busca información pública de un médico en internet.

    Usa esta herramienta cuando el APM pide un brief de un médico y se
    necesita complementar los datos internos del CRM con información
    pública: publicaciones, afiliaciones hospitalarias, logros
    profesionales, participación en congresos, etc.

    Args:
        nombre: Nombre del médico.
        apellido: Apellido del médico.
        especialidad: Especialidad médica del médico.
        hospital: Hospital donde trabaja (opcional, mejora la búsqueda).

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        from ddgs import DDGS

        query = f"Dr. {nombre} {apellido} {especialidad}"
        if hospital:
            query += f" {hospital}"
        query += " Argentina"

        results = DDGS().text(
            query, region="ar-es", max_results=3
        )

        # Snippets son suficientes — el LLM combina con datos CRM
        search_data = [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in results
        ]

        return {
            "success": True,
            "message": (
                f"✅ Se encontraron {len(results)} resultados "
                f"para Dr. {nombre} {apellido}."
            ),
            "data": search_data,
        }

    except Exception as e:
        logger.error(f"Web search FAILED for Dr. {nombre} {apellido}: {type(e).__name__}: {e}")
        return {
            "success": False,
            "message": (
                "⚠️ No se pudo buscar información pública del médico. "
                "Se generará el brief solo con datos del CRM."
            ),
            "data": None,
        }
