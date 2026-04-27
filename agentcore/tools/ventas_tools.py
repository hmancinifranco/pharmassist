"""
Herramientas Strands para consultas de Ventas.

Cada función decorada con @tool es invocada por el agente Strands
cuando el APM hace consultas sobre ventas por zona, productos con
caída de ventas y detalle de ventas por producto.
"""

import logging
import os
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from strands import tool

logger = logging.getLogger(__name__)

_VENTAS_TABLE_NAME = os.environ.get("VENTAS_TABLE_NAME", "ventas_reportadas")
_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _get_ventas_table():
    """Obtiene la referencia a la tabla DynamoDB de ventas."""
    dynamodb = boto3.resource("dynamodb", region_name=_REGION)
    return dynamodb.Table(_VENTAS_TABLE_NAME)


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


def _extract_venta_fields(item: dict) -> dict:
    """Extrae los campos relevantes de un registro de venta serializado."""
    return {
        "Zona": item.get("Zona"),
        "Producto": item.get("Producto"),
        "Presentacion": item.get("Presentacion"),
        "Tipo_OTC_RX": item.get("Tipo_OTC_RX"),
        "Unidades_Vendidas": item.get("Unidades_Vendidas"),
        "Valor_Venta_ARS": item.get("Valor_Venta_ARS"),
        "Crecimiento_YoY_Pct": item.get("Crecimiento_YoY_Pct"),
        "Farmacia": item.get("Farmacia"),
        "Anio_Mes": item.get("Anio_Mes"),
    }


@tool
def obtener_ventas_por_zona(zona: str, anio: int, mes: int) -> dict[str, Any]:
    """
    Obtiene las ventas reportadas para una zona en un período específico.

    Usa esta herramienta cuando el APM pregunta por ventas de una zona,
    por ejemplo: "¿Cómo fueron las ventas en Belgrano-R en enero 2025?"
    o "Mostrame las ventas de mi zona en marzo".

    Devuelve la lista de productos vendidos con unidades, valor en ARS
    y crecimiento interanual.

    Args:
        zona: Nombre de la zona geográfica (ej: "Belgrano-R", "Recoleta-Norte").
        anio: Año del período a consultar (ej: 2025).
        mes: Mes del período a consultar (1-12).

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_ventas_table()
        anio_mes = f"{anio}#{mes:02d}"

        response = table.query(
            IndexName="Zona-index",
            KeyConditionExpression=(
                Key("Zona").eq(zona) & Key("Anio_Mes").begins_with(anio_mes)
            ),
        )
        items = response.get("Items", [])

        if not items:
            return {
                "success": True,
                "message": (
                    f"No se encontraron ventas en {zona} para "
                    f"{mes:02d}/{anio}."
                ),
                "data": [],
            }

        serialized = [_extract_venta_fields(_serialize_item(it)) for it in items]

        return {
            "success": True,
            "message": (
                f"✅ Se encontraron {len(serialized)} registros de ventas "
                f"en {zona} para {mes:02d}/{anio}."
            ),
            "data": serialized,
        }

    except Exception as e:
        logger.error(f"Error al obtener ventas de zona {zona}: {e}")
        return {
            "success": False,
            "message": "❌ Error al consultar ventas por zona. Intentá de nuevo.",
            "data": None,
        }


@tool
def obtener_ventas_declinando(zonas: list[str]) -> dict[str, Any]:
    """
    Obtiene los productos con caída de ventas interanual en las zonas indicadas.

    Usa esta herramienta cuando el APM pregunta por productos que están
    bajando, por ejemplo: "¿Qué ventas bajaron en mis zonas?" o
    "¿Qué productos tienen caída en Belgrano-R y Recoleta-Norte?".

    Devuelve solo productos con Crecimiento_YoY_Pct negativo, ordenados
    del más severo al menos severo.

    Args:
        zonas: Lista de nombres de zonas a consultar (ej: ["Belgrano-R", "Recoleta-Norte"]).

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_ventas_table()
        all_declining = []

        for zona in zonas:
            response = table.query(
                IndexName="Zona-index",
                KeyConditionExpression=Key("Zona").eq(zona),
            )
            items = response.get("Items", [])

            for item in items:
                serialized = _serialize_item(item)
                crecimiento = serialized.get("Crecimiento_YoY_Pct")
                if crecimiento is not None and crecimiento < 0:
                    all_declining.append(_extract_venta_fields(serialized))

        # Ordenar por crecimiento ascendente (más severo primero)
        # Limitar a top 15 para mantener la respuesta rápida
        all_declining.sort(key=lambda v: v.get("Crecimiento_YoY_Pct", 0))
        all_declining = all_declining[:15]

        if not all_declining:
            zonas_str = ", ".join(zonas)
            return {
                "success": True,
                "message": (
                    f"No se detectaron caídas de ventas en tus zonas "
                    f"asignadas ({zonas_str})."
                ),
                "data": [],
            }

        return {
            "success": True,
            "message": (
                f"✅ Se encontraron {len(all_declining)} productos con "
                f"caída de ventas en {len(zonas)} zona(s)."
            ),
            "data": all_declining,
        }

    except Exception as e:
        logger.error(f"Error al obtener ventas declinando: {e}")
        return {
            "success": False,
            "message": "❌ Error al consultar ventas en declive. Intentá de nuevo.",
            "data": None,
        }


@tool
def obtener_ventas_por_producto(producto: str, zona: str) -> dict[str, Any]:
    """
    Obtiene el detalle de ventas de un producto específico en una zona.

    Usa esta herramienta cuando el APM pregunta por un producto en particular,
    por ejemplo: "¿Cómo van las ventas de PAMOXET en Belgrano-R?" o
    "Dame el historial de ventas de ALACIR en mi zona".

    Devuelve todos los períodos disponibles para ese producto/zona,
    ordenados del más reciente al más antiguo, con tendencia de
    crecimiento interanual.

    Args:
        producto: Nombre del producto (ej: "PAMOXET", "ALACIR").
        zona: Nombre de la zona geográfica (ej: "Belgrano-R").

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_ventas_table()
        zona_producto = f"{zona}#{producto}"

        response = table.query(
            KeyConditionExpression=Key("Zona_Producto").eq(zona_producto),
            ScanIndexForward=False,  # descendente por Anio_Mes
        )
        items = response.get("Items", [])

        if not items:
            return {
                "success": True,
                "message": (
                    f"No se encontraron ventas de {producto} en {zona}."
                ),
                "data": [],
            }

        serialized = [_extract_venta_fields(_serialize_item(it)) for it in items]

        return {
            "success": True,
            "message": (
                f"✅ Se encontraron {len(serialized)} períodos de ventas "
                f"de {producto} en {zona}."
            ),
            "data": serialized,
        }

    except Exception as e:
        logger.error(
            f"Error al obtener ventas del producto {producto} en {zona}: {e}"
        )
        return {
            "success": False,
            "message": (
                f"❌ Error al consultar ventas de {producto}. Intentá de nuevo."
            ),
            "data": None,
        }
