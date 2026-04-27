"""
Herramientas Strands para consultas de Visitas.

Cada función decorada con @tool es invocada por el agente Strands
cuando el APM hace consultas sobre historial de visitas, visitas
planificadas y agenda del día.
Todas las consultas aplican aislamiento de datos por APM.
"""

import logging
import os
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key
from strands import tool

logger = logging.getLogger(__name__)

_VISITAS_TABLE_NAME = os.environ.get("VISITAS_TABLE_NAME", "apm_visitas")
_PLANIFICADAS_TABLE_NAME = os.environ.get("PLANIFICADAS_TABLE_NAME", "visitas_planificadas")
_MEDICOS_TABLE_NAME = os.environ.get("MEDICOS_TABLE_NAME", "crm_medicos")
_MINUTAS_TABLE_NAME = os.environ.get("MINUTAS_TABLE_NAME", "minutas_visitas")
_VENTAS_TABLE_NAME = os.environ.get("VENTAS_TABLE_NAME", "ventas_reportadas")
_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _get_dynamodb():
    """Obtiene el recurso DynamoDB."""
    return boto3.resource("dynamodb", region_name=_REGION)


def _get_visitas_table():
    """Obtiene la referencia a la tabla DynamoDB de visitas."""
    return _get_dynamodb().Table(_VISITAS_TABLE_NAME)


def _get_planificadas_table():
    """Obtiene la referencia a la tabla DynamoDB de visitas planificadas."""
    return _get_dynamodb().Table(_PLANIFICADAS_TABLE_NAME)


def _get_medicos_table():
    """Obtiene la referencia a la tabla DynamoDB de médicos."""
    return _get_dynamodb().Table(_MEDICOS_TABLE_NAME)


def _get_minutas_table():
    """Obtiene la referencia a la tabla DynamoDB de minutas de visitas."""
    return _get_dynamodb().Table(_MINUTAS_TABLE_NAME)


def _get_ventas_table():
    """Obtiene la referencia a la tabla DynamoDB de ventas."""
    return _get_dynamodb().Table(_VENTAS_TABLE_NAME)


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
    """Calcula estadísticas resumen del historial de visitas.

    Replica la lógica de backend/utils/visitas_utils.py pero opera
    directamente sobre dicts de DynamoDB (sin Pydantic).

    Returns:
        Dict con total_visitas, fecha_ultima_visita, productos_presentados,
        distribucion_tipo_visita.
    """
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
def obtener_visitas_por_medico(medico_mn: int, apm_id: str) -> dict[str, Any]:
    """
    Obtiene el historial de visitas realizadas a un médico específico.

    Usa esta herramienta cuando el APM pregunta por las visitas a un médico,
    por ejemplo: "¿Cuándo fue la última visita al Dr. Herrera?" o
    "Mostrame el historial de visitas al MN 770487".

    Devuelve la lista de visitas ordenadas por fecha descendente y un
    resumen con estadísticas (total, última visita, productos presentados,
    distribución por tipo).

    Solo devuelve visitas realizadas por el APM solicitante.

    Args:
        medico_mn: Matrícula Nacional del médico (número entero).
        apm_id: Identificador del APM que realiza la consulta.

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_visitas_table()
        response = table.query(
            IndexName="Medico-Fecha-index",
            KeyConditionExpression=Key("Medico_MN").eq(medico_mn),
            ScanIndexForward=False,  # descendente por fecha
        )
        items = response.get("Items", [])

        # Filtrar por APM para aislamiento de datos
        items = [it for it in items if it.get("APM") == apm_id]

        if not items:
            return {
                "success": False,
                "message": "No se encontraron visitas a ese médico en tu historial.",
                "data": None,
            }

        serialized = [_serialize_item(it) for it in items]
        resumen = _compute_visit_summary(items)

        return {
            "success": True,
            "message": (
                f"✅ Se encontraron {resumen['total_visitas']} visitas al MN {medico_mn}. "
                f"Última visita: {resumen['fecha_ultima_visita']}."
            ),
            "data": {
                "visitas": serialized,
                "resumen": resumen,
            },
        }

    except Exception as e:
        logger.error(f"Error al obtener visitas del médico {medico_mn}: {e}")
        return {
            "success": False,
            "message": "❌ Error al consultar historial de visitas. Intentá de nuevo.",
            "data": None,
        }


@tool
def obtener_visitas_planificadas_hoy(apm_id: str) -> dict[str, Any]:
    """
    Obtiene las visitas planificadas para el día de hoy del APM.

    Usa esta herramienta cuando el APM pregunta por su agenda del día,
    por ejemplo: "¿Cuáles son mis visitas planificadas para hoy?" o
    "¿A quién tengo que visitar hoy?".

    Devuelve la lista de visitas planificadas con datos del médico
    enriquecidos (nombre, dirección, especialidad).

    Args:
        apm_id: Identificador del APM que realiza la consulta.

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        hoy = date.today().isoformat()

        table = _get_planificadas_table()
        response = table.query(
            IndexName="APM-Fecha-index",
            KeyConditionExpression=(
                Key("APM").eq(apm_id) & Key("Fecha_Planificada").eq(hoy)
            ),
        )
        items = response.get("Items", [])

        if not items:
            return {
                "success": True,
                "message": "No tenés visitas planificadas para hoy.",
                "data": [],
            }

        # Enriquecer con datos del médico (nombre, dirección, especialidad)
        medicos_table = _get_medicos_table()
        enriched = []
        for item in items:
            visit = _serialize_item(item)
            mn = item.get("Medico_MN")
            if mn is not None:
                try:
                    med_response = medicos_table.get_item(Key={"Medico_MN": mn})
                    medico = med_response.get("Item")
                    if medico:
                        visit["Medico_Nombre"] = medico.get("Nombre", "")
                        visit["Medico_Apellido"] = medico.get("Apellido", "")
                        visit["Especialidad_Medica"] = medico.get("Especialidad_Medica", "")
                        visit["Calle"] = medico.get("Calle", "")
                        visit["Altura"] = medico.get("Altura", "")
                        visit["Barrio"] = medico.get("Barrio", "")
                        visit["Latitud"] = (
                            float(medico["Latitud"])
                            if isinstance(medico.get("Latitud"), Decimal)
                            else medico.get("Latitud")
                        )
                        visit["Longitud"] = (
                            float(medico["Longitud"])
                            if isinstance(medico.get("Longitud"), Decimal)
                            else medico.get("Longitud")
                        )
                except Exception as med_err:
                    logger.warning(
                        f"No se pudo enriquecer datos del médico MN {mn}: {med_err}"
                    )
            enriched.append(visit)

        return {
            "success": True,
            "message": f"✅ Tenés {len(enriched)} visitas planificadas para hoy.",
            "data": enriched,
        }

    except Exception as e:
        logger.error(f"Error al obtener visitas planificadas: {e}")
        return {
            "success": False,
            "message": "❌ Error al consultar visitas planificadas. Intentá de nuevo.",
            "data": None,
        }


@tool
def obtener_historial_visitas_apm(
    apm_id: str, fecha_desde: str, fecha_hasta: str
) -> dict[str, Any]:
    """
    Obtiene el historial de visitas del APM en un rango de fechas.

    Usa esta herramienta cuando el APM pregunta por sus visitas en un
    período, por ejemplo: "¿Qué visitas hice en enero?" o
    "Mostrame mis visitas de los últimos 3 meses".

    Las fechas deben estar en formato ISO (YYYY-MM-DD).

    Args:
        apm_id: Identificador del APM que realiza la consulta.
        fecha_desde: Fecha de inicio del rango (YYYY-MM-DD).
        fecha_hasta: Fecha de fin del rango (YYYY-MM-DD).

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_visitas_table()
        response = table.query(
            IndexName="APM-Fecha-index",
            KeyConditionExpression=(
                Key("APM").eq(apm_id)
                & Key("Fecha_Visita").between(fecha_desde, fecha_hasta)
            ),
            ScanIndexForward=False,  # descendente por fecha
        )
        items = response.get("Items", [])

        if not items:
            return {
                "success": True,
                "message": (
                    f"No se encontraron visitas entre {fecha_desde} y {fecha_hasta}."
                ),
                "data": [],
            }

        serialized = [_serialize_item(it) for it in items]

        return {
            "success": True,
            "message": (
                f"✅ Se encontraron {len(serialized)} visitas entre "
                f"{fecha_desde} y {fecha_hasta}."
            ),
            "data": serialized,
        }

    except Exception as e:
        logger.error(
            f"Error al obtener historial de visitas del APM {apm_id}: {e}"
        )
        return {
            "success": False,
            "message": "❌ Error al consultar historial de visitas. Intentá de nuevo.",
            "data": None,
        }


@tool
def obtener_minutas_medico(medico_mn: int, apm_id: str) -> dict[str, Any]:
    """
    Obtiene las últimas minutas de visitas a un médico.

    Usa esta herramienta cuando el APM pide contexto de visitas previas,
    un brief con notas, o cuando sugerir_proxima_visita necesita contexto.
    Por ejemplo: "¿Qué hablamos en las últimas visitas al Dr. Herrera?"
    o "Mostrame las notas de visitas al MN 770487".

    Devuelve las últimas 3 minutas ordenadas por fecha descendente,
    con resumen, productos discutidos y compromisos.

    Solo devuelve minutas del APM solicitante.

    Args:
        medico_mn: Matrícula Nacional del médico (número entero).
        apm_id: Identificador del APM que realiza la consulta.

    Returns:
        Diccionario con {success, message, data}.
    """
    try:
        table = _get_minutas_table()
        response = table.query(
            IndexName="Medico-Fecha-index",
            KeyConditionExpression=Key("Medico_MN").eq(medico_mn),
            ScanIndexForward=False,  # descendente por fecha
        )
        items = response.get("Items", [])

        # Filtrar por APM para aislamiento de datos
        items = [it for it in items if it.get("APM") == apm_id]

        # Limitar a las últimas 3
        items = items[:3]

        if not items:
            return {
                "success": True,
                "message": "No se encontraron minutas de visitas a ese médico.",
                "data": [],
            }

        minutas = []
        for it in items:
            s = _serialize_item(it)
            minutas.append({
                "fecha": s.get("Fecha_Creacion", ""),
                "resumen": s.get("Resumen", ""),
                "productos_discutidos": s.get("Productos_Discutidos", ""),
                "compromisos": s.get("Compromisos", ""),
            })

        return {
            "success": True,
            "message": (
                f"Se encontraron {len(minutas)} minutas de visitas "
                f"al MN {medico_mn}."
            ),
            "data": minutas,
        }

    except Exception as e:
        logger.error(f"Error al obtener minutas del médico {medico_mn}: {e}")
        return {
            "success": False,
            "message": "Error al consultar minutas de visitas. Intenta de nuevo.",
            "data": None,
        }


@tool
def sugerir_proxima_visita(apm_id: str) -> dict[str, Any]:
    """
    Sugiere los próximos médicos a visitar priorizados por urgencia.

    Usa esta herramienta cuando el APM pregunta a quién visitar,
    por ejemplo: "¿A quién puedo visitar?", "Se me liberó un hueco",
    "¿Qué médico debería visitar primero?" o variantes similares.

    Combina: (a) días de SLA vencido (mayor peso), (b) productos con
    caída de ventas en la zona del médico, (c) visitas planificadas
    pendientes. Incluye contexto de la última minuta si existe.

    Retorna los top 5 médicos más prioritarios con motivo y productos
    recomendados.

    Args:
        apm_id: Identificador del APM que realiza la consulta.

    Returns:
        Diccionario con {success, message, data} con ranking de médicos.
    """
    try:
        from datetime import date as _date

        try:
            from backend.data.product_catalog import CADENCIA_DIAS, ESPECIALIDAD_PRODUCTOS
        except ImportError:
            from data.product_catalog import CADENCIA_DIAS, ESPECIALIDAD_PRODUCTOS

        hoy = _date.today()

        # 1. Obtener médicos del APM
        medicos_table = _get_medicos_table()
        med_response = medicos_table.query(
            IndexName="APM-index",
            KeyConditionExpression=Key("APM").eq(apm_id),
        )
        medicos = med_response.get("Items", [])

        if not medicos:
            return {
                "success": True,
                "message": "No se encontraron médicos en tu cartera.",
                "data": [],
            }

        # 2. Obtener zonas del APM y ventas declinando por zona
        zonas = {m.get("Zona") for m in medicos if m.get("Zona")}
        ventas_table = _get_ventas_table()
        ventas_caida: dict[str, list[dict]] = {}  # zona -> [{Producto, Crecimiento_YoY_Pct}]
        for zona in zonas:
            try:
                v_response = ventas_table.query(
                    IndexName="Zona-index",
                    KeyConditionExpression=Key("Zona").eq(zona),
                )
                for item in v_response.get("Items", []):
                    s = _serialize_item(item)
                    crec = s.get("Crecimiento_YoY_Pct")
                    if crec is not None and crec < 0:
                        ventas_caida.setdefault(zona, []).append({
                            "Producto": s.get("Producto", ""),
                            "Crecimiento_YoY_Pct": crec,
                        })
            except Exception:
                logger.warning(f"No se pudieron obtener ventas de zona {zona}")

        # 3. Obtener visitas planificadas pendientes (hoy y esta semana)
        planificadas_table = _get_planificadas_table()
        hoy_str = hoy.isoformat()
        # Buscar pendientes de hoy en adelante (próximos 7 días)
        from datetime import timedelta
        fin_semana = (hoy + timedelta(days=7)).isoformat()
        try:
            plan_response = planificadas_table.query(
                IndexName="APM-Fecha-index",
                KeyConditionExpression=(
                    Key("APM").eq(apm_id)
                    & Key("Fecha_Planificada").between(hoy_str, fin_semana)
                ),
            )
            pendientes_mn = {
                it.get("Medico_MN") for it in plan_response.get("Items", [])
                if it.get("Estado", "Pendiente") == "Pendiente"
            }
        except Exception:
            pendientes_mn = set()
            logger.warning("No se pudieron obtener visitas planificadas pendientes")

        # 4. Obtener últimas minutas por médico (batch)
        minutas_table = _get_minutas_table()

        # 5. Calcular score por médico
        SLA_WEIGHT = 3
        VENTAS_WEIGHT = 1
        PENDIENTE_BONUS = 20

        candidates = []
        for med in medicos:
            s = _serialize_item(med)
            mn = s.get("Medico_MN")
            cadencia = s.get("Cadencia", "")
            fecha_ultima = s.get("Fecha_Ultima_Visita")
            zona = s.get("Zona", "")

            # Calcular días de SLA vencido
            intervalo = CADENCIA_DIAS.get(cadencia)
            if intervalo is None:
                continue  # cadencia desconocida, skip

            if fecha_ultima:
                try:
                    if isinstance(fecha_ultima, str):
                        parts = fecha_ultima.split("-")
                        fecha_obj = _date(int(parts[0]), int(parts[1]), int(parts[2]))
                    else:
                        fecha_obj = fecha_ultima
                    dias_desde = (hoy - fecha_obj).days
                except (ValueError, TypeError):
                    dias_desde = intervalo + 1
            else:
                dias_desde = intervalo + 1  # nunca visitado

            dias_vencido = dias_desde - intervalo
            if dias_vencido <= 0:
                continue  # al día, no sugerir

            # Score base por SLA
            score = SLA_WEIGHT * dias_vencido

            # Bonus por ventas declinando en la zona
            motivos = [f"SLA vencido hace {dias_vencido} días"]
            productos_rec = []
            zona_caidas = ventas_caida.get(zona, [])
            if zona_caidas:
                # Ordenar por caída más severa
                zona_caidas_sorted = sorted(
                    zona_caidas, key=lambda x: x.get("Crecimiento_YoY_Pct", 0)
                )
                peor = zona_caidas_sorted[0]
                score += VENTAS_WEIGHT * abs(peor.get("Crecimiento_YoY_Pct", 0))
                for vc in zona_caidas_sorted[:3]:
                    prod = vc.get("Producto", "")
                    crec = vc.get("Crecimiento_YoY_Pct", 0)
                    motivos.append(f"{prod} cayó {crec}% en su zona")
                    if prod not in productos_rec:
                        productos_rec.append(prod)

            # Bonus por visita planificada pendiente
            if mn in pendientes_mn:
                score += PENDIENTE_BONUS
                motivos.append("Visita planificada pendiente esta semana")

            # Agregar productos por especialidad si no hay de ventas
            if not productos_rec:
                esp = s.get("Especialidad_Medica", "")
                productos_rec = ESPECIALIDAD_PRODUCTOS.get(esp, [])[:3]

            candidates.append({
                "medico_mn": mn,
                "nombre": f"Dr/a. {s.get('Nombre', '')} {s.get('Apellido', '')}",
                "especialidad": s.get("Especialidad_Medica", ""),
                "zona": zona,
                "direccion": f"{s.get('Calle', '')} {s.get('Altura', '')}, {s.get('Barrio', '')}".strip(", "),
                "motivo": ". ".join(motivos),
                "productos_recomendados": productos_rec,
                "score": round(score),
                "ultima_minuta": None,  # se llena abajo
            })

        # Ordenar por score desc, top 5
        candidates.sort(key=lambda c: c["score"], reverse=True)
        top5 = candidates[:5]

        # 6. Enriquecer top 5 con última minuta
        for cand in top5:
            mn = cand["medico_mn"]
            try:
                min_response = minutas_table.query(
                    IndexName="Medico-Fecha-index",
                    KeyConditionExpression=Key("Medico_MN").eq(mn),
                    ScanIndexForward=False,
                    Limit=1,
                )
                min_items = min_response.get("Items", [])
                min_items = [it for it in min_items if it.get("APM") == apm_id]
                if min_items:
                    m = _serialize_item(min_items[0])
                    cand["ultima_minuta"] = {
                        "fecha": m.get("Fecha_Creacion", ""),
                        "resumen": m.get("Resumen", ""),
                        "compromisos": m.get("Compromisos", ""),
                    }
            except Exception:
                logger.warning(f"No se pudo obtener minuta del MN {mn}")

        if not top5:
            return {
                "success": True,
                "message": "Todos tus médicos están al día con sus visitas.",
                "data": [],
            }

        return {
            "success": True,
            "message": f"Top {len(top5)} médicos sugeridos para visitar",
            "data": top5,
        }

    except Exception as e:
        logger.error(f"Error al sugerir próxima visita para APM {apm_id}: {e}")
        return {
            "success": False,
            "message": "Error al generar sugerencias de visita. Intenta de nuevo.",
            "data": None,
        }
