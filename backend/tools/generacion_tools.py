"""
Herramientas Strands para generación de contenido enriquecido.

Incluye generación de briefs de médicos (CRM + web + visitas) y
preparación de contexto para mensajes de cumpleaños personalizados.
"""

import logging
import os
from collections import Counter
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from strands import tool

try:
    from backend.tools.web_search_tools import buscar_info_publica_medico
except ImportError:
    from tools.web_search_tools import buscar_info_publica_medico

try:
    from backend.data.product_catalog import ESPECIALIDAD_PRODUCTOS
except ImportError:
    from data.product_catalog import ESPECIALIDAD_PRODUCTOS

logger = logging.getLogger(__name__)

_MEDICOS_TABLE_NAME = os.environ.get("MEDICOS_TABLE_NAME", "crm_medicos")
_VISITAS_TABLE_NAME = os.environ.get("VISITAS_TABLE_NAME", "apm_visitas")
_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _get_dynamodb():
    """Obtiene el recurso DynamoDB."""
    return boto3.resource("dynamodb", region_name=_REGION)


def _get_medicos_table():
    """Obtiene la referencia a la tabla DynamoDB de médicos."""
    return _get_dynamodb().Table(_MEDICOS_TABLE_NAME)


def _get_visitas_table():
    """Obtiene la referencia a la tabla DynamoDB de visitas."""
    return _get_dynamodb().Table(_VISITAS_TABLE_NAME)


def _serialize_item(item: dict) -> dict:
    """Convierte Decimals de DynamoDB a int/float para serialización JSON."""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = int(v) if v == int(v) else float(v)
        elif isinstance(v, list):
            result[k] = [
                int(i) if isinstance(i, Decimal) and i == int(i)
                else float(i) if isinstance(i, Decimal)
                else i
                for i in v
            ]
        else:
            result[k] = v
    return result


def _compute_visit_summary(items: list[dict]) -> dict:
    """Calcula estadísticas resumen del historial de visitas."""
    if not items:
        return {
            "total_visitas": 0,
            "fecha_ultima_visita": None,
            "productos_presentados": [],
            "distribucion_tipo_visita": {},
        }

    total = len(items)

    fechas = [it.get("Fecha_Visita", "") for it in items if it.get("Fecha_Visita")]
    fecha_max = max(fechas) if fechas else None

    productos: set[str] = set()
    for it in items:
        raw = it.get("Productos_Presentados", "")
        if isinstance(raw, str) and raw:
            productos.update(p.strip() for p in raw.split("|") if p.strip())
        elif isinstance(raw, list):
            productos.update(raw)

    tipo_counter: Counter[str] = Counter(
        it.get("Tipo_Visita", "Desconocido") for it in items
    )

    return {
        "total_visitas": total,
        "fecha_ultima_visita": fecha_max,
        "productos_presentados": sorted(productos),
        "distribucion_tipo_visita": dict(tipo_counter),
    }


@tool
def generar_brief_medico(medico_mn: int, apm_id: str) -> dict[str, Any]:
    """
    Genera un brief completo de un médico combinando datos del CRM,
    información pública de internet e historial de visitas.

    Usa esta herramienta cuando el APM pide un brief o perfil enriquecido
    de un médico, por ejemplo: "Dame un brief del Dr. Herrera" o
    "Preparame información para visitar al MN 770487".

    El brief incluye: perfil profesional, información pública, historial
    de visitas, sugerencias de rapport y productos recomendados.

    Args:
        medico_mn: Matrícula Nacional del médico (número entero).
        apm_id: Identificador del APM que realiza la consulta.

    Returns:
        Diccionario con {success, message, data} conteniendo el brief estructurado.
    """
    try:
        # 1. Obtener perfil del médico del CRM
        medicos_table = _get_medicos_table()
        response = medicos_table.get_item(Key={"Medico_MN": medico_mn})
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

        # Track sub-steps for transparency
        pasos = ["Consultando perfil en CRM"]

        medico = _serialize_item(item)

        # 2. Buscar información pública
        pasos.append("Buscando información pública en internet (DDGS)")
        logger.info(f"Buscando info pública de Dr. {medico.get('Nombre')} {medico.get('Apellido')}...")
        web_result = buscar_info_publica_medico(
            nombre=medico.get("Nombre", ""),
            apellido=medico.get("Apellido", ""),
            especialidad=medico.get("Especialidad_Medica", ""),
            hospital=medico.get("Hospital", ""),
        )
        logger.info(f"Web search result: success={web_result.get('success')}, message={web_result.get('message')}")

        if web_result.get("success"):
            info_publica = web_result.get("data", {})
            pasos.append(f"Se encontraron {len(info_publica)} resultados web")
        else:
            info_publica = None
            pasos.append("Sin resultados de búsqueda web")

        # 3. Obtener historial de visitas
        pasos.append("Consultando historial de visitas en DynamoDB")
        visitas_table = _get_visitas_table()
        visitas_response = visitas_table.query(
            IndexName="Medico-Fecha-index",
            KeyConditionExpression=Key("Medico_MN").eq(medico_mn),
            ScanIndexForward=False,
        )
        visitas_items = visitas_response.get("Items", [])
        visitas_items = [v for v in visitas_items if v.get("APM") == apm_id]
        resumen_visitas = _compute_visit_summary(visitas_items)

        # 4. Productos recomendados por especialidad
        pasos.append("Mapeando productos recomendados por especialidad")
        especialidad = medico.get("Especialidad_Medica", "")
        productos_recomendados = ESPECIALIDAD_PRODUCTOS.get(especialidad, [])

        # 5. Construir brief estructurado
        brief = {
            "perfil_profesional": {
                "nombre_completo": f"Dr/a. {medico.get('Nombre', '')} {medico.get('Apellido', '')}",
                "medico_mn": medico.get("Medico_MN"),
                "especialidad": especialidad,
                "hospital": medico.get("Hospital", "No registrado"),
                "facultad": medico.get("Facultad", "No registrada"),
                "anio_egresado": medico.get("Anio_Egresado", "No registrado"),
                "zona": medico.get("Zona", ""),
                "cadencia": medico.get("Cadencia", ""),
            },
            "informacion_publica": (
                info_publica
                if info_publica
                else "No se encontró información pública adicional."
            ),
            "historial_visitas": resumen_visitas,
            "sugerencias_rapport": {
                "hobby_intereses": medico.get("Hobby_Intereses", "No registrado"),
                "religion": medico.get("Religion", "No registrada"),
            },
            "productos_recomendados": productos_recomendados,
        }

        nombre_completo = f"{medico.get('Nombre', '')} {medico.get('Apellido', '')}"
        pasos_str = " → ".join(pasos)
        return {
            "success": True,
            "message": f"✅ Brief generado para Dr/a. {nombre_completo}. Pasos: {pasos_str}",
            "data": brief,
        }

    except Exception as e:
        logger.error(f"Error al generar brief del médico MN {medico_mn}: {e}")
        return {
            "success": False,
            "message": "❌ Error al generar el brief del médico. Intentá de nuevo.",
            "data": None,
        }


@tool
def generar_mensaje_cumpleanos(medico_mn: int) -> dict[str, Any]:
    """
    Obtiene los datos del CRM necesarios para generar un mensaje de
    cumpleaños personalizado para un médico.

    Usa esta herramienta cuando se necesita preparar un saludo de
    cumpleaños para un médico. Devuelve el contexto del CRM (intereses,
    especialidad, datos personales) para que el agente componga el
    mensaje final.

    Args:
        medico_mn: Matrícula Nacional del médico (número entero).

    Returns:
        Diccionario con {success, message, data} conteniendo la info
        del médico y contexto para generar el mensaje.
    """
    try:
        medicos_table = _get_medicos_table()
        response = medicos_table.get_item(Key={"Medico_MN": medico_mn})
        item = response.get("Item")

        if not item:
            return {
                "success": False,
                "message": "No se encontró un médico con esa matrícula.",
                "data": None,
            }

        medico = _serialize_item(item)

        medico_info = {
            "nombre": medico.get("Nombre", ""),
            "apellido": medico.get("Apellido", ""),
            "especialidad": medico.get("Especialidad_Medica", ""),
            "hospital": medico.get("Hospital", ""),
            "facultad": medico.get("Facultad", ""),
            "hobby_intereses": medico.get("Hobby_Intereses", ""),
            "religion": medico.get("Religion", ""),
        }

        context_for_message = (
            f"Médico: Dr/a. {medico_info['nombre']} {medico_info['apellido']}, "
            f"especialista en {medico_info['especialidad']}. "
        )
        if medico_info["hospital"]:
            context_for_message += f"Trabaja en {medico_info['hospital']}. "
        if medico_info["facultad"]:
            context_for_message += f"Egresado/a de {medico_info['facultad']}. "
        if medico_info["hobby_intereses"]:
            context_for_message += f"Intereses: {medico_info['hobby_intereses']}. "
        if medico_info["religion"]:
            context_for_message += f"Religión: {medico_info['religion']}. "

        nombre_completo = f"{medico_info['nombre']} {medico_info['apellido']}"
        return {
            "success": True,
            "message": (
                f"✅ Datos obtenidos para generar mensaje de cumpleaños "
                f"del Dr/a. {nombre_completo}."
            ),
            "data": {
                "medico_info": medico_info,
                "context_for_message": context_for_message,
            },
        }

    except Exception as e:
        logger.error(
            f"Error al obtener datos para cumpleaños del MN {medico_mn}: {e}"
        )
        return {
            "success": False,
            "message": "❌ Error al obtener datos del médico. Intentá de nuevo.",
            "data": None,
        }
