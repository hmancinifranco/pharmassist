"""
Herramientas Strands para consultas de CRM/Médicos.

Cada función decorada con @tool es invocada por el agente Strands
cuando el APM hace consultas sobre médicos de su cartera.
Todas las consultas aplican aislamiento de datos por APM.
"""

import logging
import os
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key
from strands import tool

logger = logging.getLogger(__name__)

_TABLE_NAME = os.environ.get("MEDICOS_TABLE_NAME", "crm_medicos")
_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _get_table():
    """Obtiene la referencia a la tabla DynamoDB de médicos."""
    dynamodb = boto3.resource("dynamodb", region_name=_REGION)
    return dynamodb.Table(_TABLE_NAME)


def _serialize_item(item: dict) -> dict:
    """Convierte Decimals de DynamoDB a int/float para serialización JSON."""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = int(v) if v == int(v) else float(v)
        else:
            result[k] = v
    return result


def _medico_resumen(item: dict) -> dict:
    """Extrae campos de resumen para listas y desambiguación."""
    s = _serialize_item(item)
    return {
        "Medico_MN": s.get("Medico_MN"),
        "Nombre": s.get("Nombre"),
        "Apellido": s.get("Apellido"),
        "Especialidad_Medica": s.get("Especialidad_Medica"),
        "Zona": s.get("Zona"),
    }



@tool
def buscar_medico_por_nombre(nombre: str, apm_id: str) -> dict[str, Any]:
    """
    Busca un médico por nombre o apellido en la cartera del APM.

    Usa esta herramienta cuando el APM pregunta por un médico específico
    por su nombre, por ejemplo: "Buscame al Dr. Herrera" o
    "¿Tengo un médico que se llame Martínez?".

    Si hay múltiples coincidencias, devuelve una lista para desambiguar.

    Args:
        nombre: Nombre o apellido del médico a buscar.
        apm_id: Identificador del APM que realiza la consulta.

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_table()
        response = table.query(
            IndexName="APM-index",
            KeyConditionExpression=Key("APM").eq(apm_id),
        )
        items = response.get("Items", [])

        nombre_lower = nombre.lower()
        # Search each word independently against nombre and apellido
        search_words = nombre_lower.split()
        matches = []
        for item in items:
            item_nombre = item.get("Nombre", "").lower()
            item_apellido = item.get("Apellido", "").lower()
            full_name = f"{item_nombre} {item_apellido}"
            # Match if ALL search words appear in the full name
            if all(w in full_name for w in search_words):
                matches.append(item)
            # Also match if any single word matches nombre or apellido exactly
            elif any(w == item_nombre or w == item_apellido for w in search_words):
                matches.append(item)

        if not matches:
            return {
                "success": False,
                "message": "No se encontró un médico con ese nombre en tu cartera.",
                "data": None,
            }

        if len(matches) == 1:
            return {
                "success": True,
                "message": f"Se encontró al Dr/a. {matches[0].get('Nombre')} {matches[0].get('Apellido')}.",
                "data": _serialize_item(matches[0]),
            }

        # Múltiples coincidencias — desambiguación
        disambiguation = [_medico_resumen(m) for m in matches]
        return {
            "success": True,
            "message": (
                f"Se encontraron {len(matches)} médicos con ese nombre. "
                "¿A cuál te referís?"
            ),
            "data": disambiguation,
        }

    except Exception as e:
        logger.error(f"Error al buscar médico por nombre '{nombre}': {e}")
        return {
            "success": False,
            "message": "Error al buscar médico. Intentá de nuevo.",
            "data": None,
        }


@tool
def buscar_medicos_por_zona(zona: str, apm_id: str) -> dict[str, Any]:
    """
    Lista los médicos de una zona geográfica asignados al APM.

    Usa esta herramienta cuando el APM pregunta por médicos en una zona,
    por ejemplo: "¿Qué médicos tengo en Belgrano?" o
    "Mostrame los doctores de Recoleta-Norte".

    Args:
        zona: Nombre de la zona geográfica (ej: "Belgrano-R", "Recoleta-Norte").
        apm_id: Identificador del APM que realiza la consulta.

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_table()
        response = table.query(
            IndexName="Zona-index",
            KeyConditionExpression=Key("Zona").eq(zona),
            FilterExpression=Attr("APM").eq(apm_id),
        )
        items = response.get("Items", [])

        if not items:
            return {
                "success": False,
                "message": f"No se encontraron médicos en la zona {zona} en tu cartera.",
                "data": None,
            }

        medicos = [_medico_resumen(item) for item in items]
        return {
            "success": True,
            "message": f"Se encontraron {len(medicos)} médicos en {zona}.",
            "data": medicos,
        }

    except Exception as e:
        logger.error(f"Error al buscar médicos en zona '{zona}': {e}")
        return {
            "success": False,
            "message": "Error al buscar médicos por zona. Intentá de nuevo.",
            "data": None,
        }


@tool
def buscar_medicos_por_apm(apm_id: str) -> dict[str, Any]:
    """
    Lista todos los médicos asignados a un APM.

    Usa esta herramienta cuando el APM pregunta por toda su cartera,
    por ejemplo: "¿Cuántos médicos tengo?" o "Mostrame todos mis médicos".

    Args:
        apm_id: Identificador del APM que realiza la consulta.

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_table()
        response = table.query(
            IndexName="APM-index",
            KeyConditionExpression=Key("APM").eq(apm_id),
        )
        items = response.get("Items", [])

        if not items:
            return {
                "success": False,
                "message": "No se encontraron médicos en tu cartera.",
                "data": None,
            }

        medicos = [_medico_resumen(item) for item in items]
        return {
            "success": True,
            "message": f"Tenés {len(medicos)} médicos asignados.",
            "data": medicos,
        }

    except Exception as e:
        logger.error(f"Error al buscar médicos del APM '{apm_id}': {e}")
        return {
            "success": False,
            "message": "Error al buscar médicos. Intentá de nuevo.",
            "data": None,
        }


@tool
def obtener_perfil_medico(medico_mn: int, apm_id: str) -> dict[str, Any]:
    """
    Obtiene el perfil completo de un médico por su matrícula nacional.

    Usa esta herramienta cuando el APM necesita información detallada
    de un médico específico, por ejemplo después de desambiguar o
    cuando pide un brief: "Dame el perfil del MN 770487".

    Solo devuelve datos si el médico está asignado al APM solicitante.

    Args:
        medico_mn: Matrícula Nacional del médico (número entero).
        apm_id: Identificador del APM que realiza la consulta.

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_table()
        response = table.get_item(Key={"Medico_MN": medico_mn})
        item = response.get("Item")

        if not item:
            return {
                "success": False,
                "message": "No se encontró un médico con esa matrícula.",
                "data": None,
            }

        if item.get("APM") != apm_id:
            return {
                "success": False,
                "message": "No tenés acceso a la información de ese médico.",
                "data": None,
            }

        return {
            "success": True,
            "message": (
                f"Perfil completo del Dr/a. {item.get('Nombre')} "
                f"{item.get('Apellido')}."
            ),
            "data": _serialize_item(item),
        }

    except Exception as e:
        logger.error(f"Error al obtener perfil del médico MN {medico_mn}: {e}")
        return {
            "success": False,
            "message": "Error al obtener perfil del médico. Intentá de nuevo.",
            "data": None,
        }
