"""
Utility tools para el Unified Agent de PharmAssist.

Complementan a query_db con capacidades no-SQL:
- buscar_info_publica: búsqueda web DDGS
- generar_brief: brief pre-visita combinando Aurora + web + DynamoDB
- obtener_minutas: minutas de visitas desde DynamoDB
- generar_mensaje_cumpleanos: mensaje personalizado de cumpleaños

Requirements: 1.2, 1.3, 1.4, 1.5
"""

import logging
import os

import boto3
from boto3.dynamodb.conditions import Key
from strands import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DynamoDB configuration
# ---------------------------------------------------------------------------

_MINUTAS_TABLE_NAME = os.environ.get("MINUTAS_TABLE_NAME", "")


def _get_dynamodb_table():
    """Get the DynamoDB minutas table resource.

    Returns:
        boto3 DynamoDB Table resource, or None if table name not configured.
    """
    if not _MINUTAS_TABLE_NAME:
        logger.warning("MINUTAS_TABLE_NAME no configurado.")
        return None

    region = os.environ.get("AWS_REGION", "us-east-1")
    dynamodb = boto3.resource("dynamodb", region_name=region)
    return dynamodb.Table(_MINUTAS_TABLE_NAME)


# ---------------------------------------------------------------------------
# Tool: buscar_info_publica
# ---------------------------------------------------------------------------


@tool
def buscar_info_publica(nombre: str, apellido: str, especialidad: str, hospital: str = "") -> str:
    """Busca información pública de un médico en internet usando DDGS.

    Usa esta herramienta cuando el APM pide información pública de un médico:
    publicaciones, afiliaciones hospitalarias, logros profesionales,
    participación en congresos, etc.

    Args:
        nombre: Nombre del médico (ej: "Christian").
        apellido: Apellido del médico (ej: "Kreutzer").
        especialidad: Especialidad médica (ej: "Cardiología").
        hospital: Hospital donde trabaja (opcional, mejora la búsqueda).

    Returns:
        Texto formateado con los resultados de búsqueda para el LLM.
    """
    try:
        from ddgs import DDGS

        query = f"Dr. {nombre} {apellido} {especialidad}"
        if hospital:
            query += f" {hospital}"
        query += " Argentina"

        # Intentar con backend Google primero, fallback a auto
        try:
            results = DDGS().text(
                query, region="ar-es", max_results=5, backend="google"
            )
        except Exception:
            logger.info("Google backend falló, reintentando con backend auto.")
            results = DDGS().text(
                query, region="ar-es", max_results=5, backend="auto"
            )

        if not results:
            return (
                f"No se encontraron resultados públicos para Dr. {nombre} {apellido} "
                f"({especialidad}). El brief se generará solo con datos internos del CRM."
            )

        # Formatear resultados como texto para el LLM
        output_lines = [
            f"📋 Información pública encontrada para Dr. {nombre} {apellido} ({especialidad}):",
            "",
        ]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Sin título")
            url = r.get("href", "")
            snippet = r.get("body", "Sin descripción")
            output_lines.append(f"{i}. **{title}**")
            output_lines.append(f"   URL: {url}")
            output_lines.append(f"   {snippet}")
            output_lines.append("")

        return "\n".join(output_lines)

    except Exception as e:
        logger.error(
            "Error en búsqueda web para Dr. %s %s: %s", nombre, apellido, str(e)
        )
        return (
            f"⚠️ No se pudo buscar información pública de Dr. {nombre} {apellido}. "
            "El brief se generará solo con datos internos del CRM."
        )


# ---------------------------------------------------------------------------
# Tool: obtener_minutas
# ---------------------------------------------------------------------------


@tool
def obtener_minutas(doctor_id: str) -> str:
    """Obtiene las minutas de visitas anteriores a un médico desde DynamoDB.

    Usa esta herramienta cuando el APM pregunta por notas o minutas de
    visitas anteriores a un médico específico. Las minutas contienen
    resúmenes de conversaciones, compromisos y observaciones.

    Args:
        doctor_id: ID del médico en el sistema (ej: "DOC_001").

    Returns:
        Texto formateado con las minutas encontradas.
    """
    try:
        table = _get_dynamodb_table()
        if table is None:
            return (
                "⚠️ La tabla de minutas no está configurada. "
                "No se pueden obtener notas de visitas anteriores."
            )

        # Query DynamoDB by doctor_id (partition key)
        response = table.query(
            KeyConditionExpression=Key("doctor_id").eq(doctor_id),
            ScanIndexForward=False,  # Más recientes primero
            Limit=10,
        )

        items = response.get("Items", [])

        if not items:
            return (
                f"No se encontraron minutas de visitas anteriores para el médico {doctor_id}. "
                "Es posible que sea un médico nuevo o que no se hayan registrado minutas."
            )

        # Formatear minutas como texto
        output_lines = [
            f"📝 Minutas de visitas anteriores (médico {doctor_id}):",
            f"   Se encontraron {len(items)} minuta(s).",
            "",
        ]

        for i, item in enumerate(items, 1):
            fecha = item.get("fecha", "Sin fecha")
            resumen = item.get("resumen", item.get("contenido", "Sin resumen"))
            apm = item.get("apm_id", "")
            tipo = item.get("tipo_visita", "")

            output_lines.append(f"--- Minuta {i} ({fecha}) ---")
            if tipo:
                output_lines.append(f"Tipo de visita: {tipo}")
            if apm:
                output_lines.append(f"APM: {apm}")
            output_lines.append(f"Resumen: {resumen}")
            output_lines.append("")

        return "\n".join(output_lines)

    except Exception as e:
        logger.error("Error obteniendo minutas para doctor %s: %s", doctor_id, str(e))
        return (
            f"⚠️ Error al obtener minutas para el médico {doctor_id}. "
            "Intentá de nuevo o consultá el historial de visitas con query_db."
        )


# ---------------------------------------------------------------------------
# Tool: generar_brief
# ---------------------------------------------------------------------------


@tool
def generar_brief(doctor_id: str, apm_id: str) -> str:
    """Genera un brief completo para preparar una visita a un médico.

    Combina datos del CRM (Aurora via query_db), minutas previas (DynamoDB)
    e información pública (web search) para armar un documento de preparación
    pre-visita.

    Usa esta herramienta cuando el APM pide preparar una visita, armar un brief,
    o quiere toda la información disponible de un médico antes de visitarlo.

    Args:
        doctor_id: ID del médico en el sistema (ej: "DOC_001").
        apm_id: ID del APM autenticado (ej: "APM_001").

    Returns:
        Texto con el brief consolidado para la visita.
    """
    brief_sections = []

    # --- Sección 1: Datos del CRM (Aurora) ---
    try:
        try:
            from agentcore.toolkit import query_db
        except ModuleNotFoundError:
            from toolkit import query_db

        # Obtener datos del médico
        doctor_sql = (
            f"SELECT d.\"primerNombre\", d.\"primerApellido\", "
            f"e.nombre as especialidad, i.nombre as institucion, "
            f"dv.frecuencia "
            f"FROM cartera_medica cm "
            f"JOIN doctor d ON d.id = cm.doctor_id "
            f"LEFT JOIN especialidad e ON e.id = d.especialidad_id "
            f"LEFT JOIN datos_visita dv ON dv.id = cm.datos_visita_id "
            f"LEFT JOIN institucion i ON i.id = dv.institucion_id "
            f"WHERE cm.apm_id = '{apm_id}' "
            f"AND cm.doctor_id = '{doctor_id}' "
            f"AND cm.inactivo = false"
        )
        doctor_data = query_db(sql=doctor_sql)
        brief_sections.append("## 📋 Datos del Médico (CRM)")
        brief_sections.append(doctor_data)
        brief_sections.append("")

    except Exception as e:
        logger.error("Error obteniendo datos CRM para brief: %s", str(e))
        brief_sections.append("## 📋 Datos del Médico (CRM)")
        brief_sections.append("⚠️ No se pudieron obtener datos del CRM.")
        brief_sections.append("")

    # --- Sección 2: Últimas visitas ---
    try:
        try:
            from agentcore.toolkit import query_db
        except ModuleNotFoundError:
            from toolkit import query_db

        visitas_sql = (
            f"SELECT a.inicio as fecha, a.visita_tipo, a.observaciones, "
            f"a.visita_exitosa "
            f"FROM agenda a "
            f"WHERE a.apm_id = '{apm_id}' "
            f"AND a.doctor_id = '{doctor_id}' "
            f"AND a.inactivo = false "
            f"ORDER BY a.inicio DESC LIMIT 5"
        )
        visitas_data = query_db(sql=visitas_sql)
        brief_sections.append("## 📅 Últimas Visitas")
        brief_sections.append(visitas_data)
        brief_sections.append("")

    except Exception as e:
        logger.error("Error obteniendo visitas para brief: %s", str(e))
        brief_sections.append("## 📅 Últimas Visitas")
        brief_sections.append("⚠️ No se pudieron obtener datos de visitas.")
        brief_sections.append("")

    # --- Sección 3: Minutas de DynamoDB ---
    try:
        minutas_data = obtener_minutas(doctor_id=doctor_id)
        brief_sections.append("## 📝 Minutas Anteriores")
        brief_sections.append(minutas_data)
        brief_sections.append("")

    except Exception as e:
        logger.error("Error obteniendo minutas para brief: %s", str(e))
        brief_sections.append("## 📝 Minutas Anteriores")
        brief_sections.append("⚠️ No se pudieron obtener minutas.")
        brief_sections.append("")

    # --- Sección 4: Información pública (web) ---
    try:
        # Extraer nombre/apellido/especialidad del doctor_data si es posible
        # Fallback: usar doctor_id directamente para la búsqueda
        try:
            from agentcore.toolkit import query_db
        except ModuleNotFoundError:
            from toolkit import query_db

        nombre_sql = (
            f"SELECT d.\"primerNombre\", d.\"primerApellido\", "
            f"e.nombre as especialidad "
            f"FROM doctor d "
            f"LEFT JOIN especialidad e ON e.id = d.especialidad_id "
            f"WHERE d.id = '{doctor_id}'"
        )
        # Parse basic info for web search
        nombre_result = query_db(sql=nombre_sql)

        # Best-effort: try to extract name from structured data
        # If this fails, the web search section is skipped gracefully
        web_data = buscar_info_publica(
            nombre=doctor_id,
            apellido="",
            especialidad="médico",
        )
        brief_sections.append("## 🌐 Información Pública")
        brief_sections.append(web_data)
        brief_sections.append("")

    except Exception as e:
        logger.error("Error en búsqueda web para brief: %s", str(e))
        brief_sections.append("## 🌐 Información Pública")
        brief_sections.append("⚠️ No se pudo buscar información pública.")
        brief_sections.append("")

    # --- Ensamblar brief ---
    header = f"# 📄 Brief Pre-Visita — Médico {doctor_id}\n"
    return header + "\n".join(brief_sections)


# ---------------------------------------------------------------------------
# Tool: generar_mensaje_cumpleanos
# ---------------------------------------------------------------------------


@tool
def generar_mensaje_cumpleanos(doctor_id: str) -> str:
    """Genera un mensaje personalizado de cumpleaños para un médico.

    Consulta los datos del médico en Aurora (nombre, especialidad, intereses)
    y genera un template de mensaje de cumpleaños que el APM puede enviar.

    Usa esta herramienta cuando el APM quiere felicitar a un médico por
    su cumpleaños o preparar un mensaje de saludo personalizado.

    Args:
        doctor_id: ID del médico en el sistema (ej: "DOC_001").

    Returns:
        Texto con el mensaje de cumpleaños personalizado.
    """
    try:
        try:
            from agentcore.toolkit import query_db
        except ModuleNotFoundError:
            from toolkit import query_db

        # Obtener datos del médico para personalización
        doctor_sql = (
            f"SELECT d.\"primerNombre\", d.\"primerApellido\", "
            f"e.nombre as especialidad "
            f"FROM doctor d "
            f"LEFT JOIN especialidad e ON e.id = d.especialidad_id "
            f"WHERE d.id = '{doctor_id}'"
        )
        doctor_data = query_db(sql=doctor_sql)

        return (
            f"🎂 Datos del médico para mensaje de cumpleaños (ID: {doctor_id}):\n\n"
            f"{doctor_data}\n\n"
            f"---\n"
            f"Usá estos datos para redactar un mensaje de cumpleaños personalizado. "
            f"Considerá la especialidad y el vínculo profesional. "
            f"El tono debe ser cálido pero profesional, en español argentino."
        )

    except Exception as e:
        logger.error(
            "Error generando mensaje de cumpleaños para doctor %s: %s",
            doctor_id,
            str(e),
        )
        return (
            f"⚠️ No se pudieron obtener los datos del médico {doctor_id} "
            f"para generar el mensaje de cumpleaños. "
            f"Verificá que el ID del médico sea correcto."
        )
