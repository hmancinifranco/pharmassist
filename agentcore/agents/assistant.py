"""
Agente Strands para el Asistente APM (PharmAssist).

Single Agent con tools especializados por dominio (CRM, visitas, ventas,
web search, generación IA). El LLM (Claude Opus 4.6) selecciona el tool
correcto basándose en docstrings descriptivos.
"""

import logging
import os

from strands import Agent
from strands.models import BedrockModel

# --- Tool imports (dual-path: backend vs agentcore) ---
try:
    from backend.tools.medicos_tools import (
        buscar_medico_por_nombre,
        buscar_medicos_por_apm,
        buscar_medicos_por_zona,
        obtener_perfil_medico,
    )
except ImportError:
    from tools.medicos_tools import (
        buscar_medico_por_nombre,
        buscar_medicos_por_apm,
        buscar_medicos_por_zona,
        obtener_perfil_medico,
    )

try:
    from backend.tools.visitas_tools import (
        obtener_historial_visitas_apm,
        obtener_minutas_medico,
        obtener_visitas_planificadas_hoy,
        obtener_visitas_por_medico,
        sugerir_proxima_visita,
    )
except ImportError:
    from tools.visitas_tools import (
        obtener_historial_visitas_apm,
        obtener_minutas_medico,
        obtener_visitas_planificadas_hoy,
        obtener_visitas_por_medico,
        sugerir_proxima_visita,
    )

try:
    from backend.tools.ventas_tools import (
        obtener_ventas_declinando,
        obtener_ventas_por_producto,
        obtener_ventas_por_zona,
    )
except ImportError:
    from tools.ventas_tools import (
        obtener_ventas_declinando,
        obtener_ventas_por_producto,
        obtener_ventas_por_zona,
    )

try:
    from backend.tools.web_search_tools import buscar_info_publica_medico
except ImportError:
    from tools.web_search_tools import buscar_info_publica_medico

try:
    from backend.tools.generacion_tools import (
        generar_brief_medico,
        generar_mensaje_cumpleanos,
    )
except ImportError:
    from tools.generacion_tools import (
        generar_brief_medico,
        generar_mensaje_cumpleanos,
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — español argentino, voseo, dominio farmacéutico
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Sos el asistente inteligente de PharmAssist, la plataforma \
para Agentes de Propaganda Médica (APMs / visitadores médicos) de una farmacéutica argentina.

Tu rol es ayudar al APM a gestionar su día a día: consultar su cartera de médicos, \
revisar historial de visitas, analizar ventas por zona y producto, preparar briefs \
para visitas y generar mensajes de cumpleaños personalizados.

## Reglas de comunicación
- Respondé siempre en español argentino, usando "vos" (nunca "tú" ni "usted").
- Sé conciso, profesional y cálido. Usá un tono de compañero de trabajo.
- Citá datos concretos: fechas, nombres completos, números, porcentajes. \
  No des respuestas vagas.
- Si una herramienta devuelve datos, presentalos de forma clara y organizada. \
  Usá tablas markdown para datos tabulares.
- Si no encontrás datos, respondé de forma útil sugiriendo consultas alternativas.
- Nunca expongas errores técnicos crudos al usuario.
- NO uses emojis en las respuestas.

## Velocidad — MUY IMPORTANTE
- Respondé lo más rápido posible. Minimizá la cantidad de tool calls redundantes.
- Para un brief, usá generar_brief_medico que hace todo en un solo call (CRM + web + visitas).
- No hagas tool calls innecesarios. Si ya tenés la info, respondé directo.

## Herramientas disponibles por dominio

### CRM / Médicos
- buscar_medico_por_nombre: Buscar médicos por nombre o apellido.
- buscar_medicos_por_zona: Listar médicos de una zona.
- buscar_medicos_por_apm: Listar toda la cartera del APM.
- obtener_perfil_medico: Perfil completo por matrícula nacional (MN).

### Visitas
- obtener_visitas_por_medico: Historial de visitas a un médico.
- obtener_visitas_planificadas_hoy: Visitas planificadas para hoy.
- obtener_historial_visitas_apm: Historial por rango de fechas.
- obtener_minutas_medico: Últimas minutas/notas de visitas a un médico.
- sugerir_proxima_visita: Ranking de médicos priorizados para visitar (SLA + ventas + planificadas).

### Ventas
- obtener_ventas_por_zona: Ventas de una zona en un período.
- obtener_ventas_declinando: Productos con caída YoY en zonas del APM (top 15).
- obtener_ventas_por_producto: Detalle de un producto en una zona.

### Búsqueda web y generación
- buscar_info_publica_medico: Info pública de un médico (publicaciones, hospital).
- generar_brief_medico: Brief completo (CRM + web + visitas) en un solo call.

## Contexto del APM
El APM tiene un apm_id que se pasa en cada mensaje. Usalo en todas las herramientas \
para garantizar aislamiento de datos.

## Importante
- Siempre usá las herramientas para obtener datos reales. No inventes información.
- La fecha actual se incluye en cada mensaje del usuario. Usala para consultas temporales.
- Para consultas de ventas, primero identificá las zonas del APM si no las mencionó.
- Cuando el APM pregunte "¿a quién puedo visitar?", "se me liberó un hueco" o variantes, \
  usá sugerir_proxima_visita que calcula un ranking inteligente.
- Cuando el APM pida un brief, incluí minutas de visitas previas si existen \
  (obtener_minutas_medico).
"""

# ---------------------------------------------------------------------------
# All tools registered for the single agent
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    # CRM / Médicos
    buscar_medico_por_nombre,
    buscar_medicos_por_zona,
    buscar_medicos_por_apm,
    obtener_perfil_medico,
    # Visitas
    obtener_visitas_por_medico,
    obtener_visitas_planificadas_hoy,
    obtener_historial_visitas_apm,
    obtener_minutas_medico,
    sugerir_proxima_visita,
    # Ventas
    obtener_ventas_por_zona,
    obtener_ventas_declinando,
    obtener_ventas_por_producto,
    # Web Search
    buscar_info_publica_medico,
    # Generación
    generar_brief_medico,
    generar_mensaje_cumpleanos,
]

# ---------------------------------------------------------------------------
# Bedrock model configuration
# ---------------------------------------------------------------------------


def _build_model() -> BedrockModel:
    """Construye la instancia de BedrockModel desde variables de entorno."""
    return BedrockModel(
        model_id=os.environ.get(
            "BEDROCK_MODEL_ID",
            "us.anthropic.claude-opus-4-6-v1",
        ),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        temperature=0.3,
        max_tokens=4096,
    )


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

_sessions: dict[str, Agent] = {}


def get_or_create_session(session_id: str) -> Agent:
    """Devuelve un Agent existente para la sesión o crea uno nuevo.

    Cada sesión mantiene su propio contexto de conversación para que
    el APM pueda hacer preguntas de seguimiento.
    """
    if session_id not in _sessions:
        _sessions[session_id] = Agent(
            model=_build_model(),
            tools=ALL_TOOLS,
            system_prompt=SYSTEM_PROMPT,
        )
    return _sessions[session_id]


def chat(message: str, apm_id: str, session_id: str, mode: str = "text") -> str:
    """Envía un mensaje al agente y devuelve la respuesta como texto.

    Args:
        message: Mensaje del APM.
        apm_id: Identificador del APM.
        session_id: ID de sesión para mantener contexto.
        mode: ``"text"`` (default) o ``"voice"``. En modo voz la respuesta
              se optimiza para ser escuchada (sin markdown, tablas ni emojis).
    """
    from datetime import date as _date

    agent = get_or_create_session(session_id)

    hoy = _date.today().isoformat()
    prompt = (
        f"[Contexto: APM apm_id=\"{apm_id}\", fecha_actual=\"{hoy}\"]\n\n"
        f"{message}"
    )

    # En modo voz, agregar instrucciones para respuesta hablada
    if mode == "voice":
        prompt += (
            "\n\n[MODO VOZ — La respuesta será leída en voz alta. "
            "Respondé en texto plano, sin markdown, sin tablas, sin listas con viñetas, "
            "sin emojis ni caracteres especiales. Sé conciso: máximo 2-3 oraciones. "
            "Resumí datos tabulares de forma narrativa. "
            "Optimizá para ser escuchado naturalmente.]"
        )

    # Capture tool calls via a custom callback handler
    tool_steps: list[str] = []
    _FRIENDLY = {
        "buscar_medico_por_nombre": "Buscando médico en CRM",
        "buscar_medicos_por_apm": "Consultando cartera del APM",
        "buscar_medicos_por_zona": "Buscando médicos por zona",
        "obtener_perfil_medico": "Obteniendo perfil completo del médico",
        "obtener_visitas_por_medico": "Consultando historial de visitas",
        "obtener_visitas_planificadas_hoy": "Consultando agenda de hoy",
        "obtener_historial_visitas_apm": "Consultando historial de visitas del APM",
        "obtener_minutas_medico": "Consultando minutas de visitas previas",
        "sugerir_proxima_visita": "Calculando sugerencia de próxima visita",
        "obtener_ventas_por_zona": "Consultando ventas por zona",
        "obtener_ventas_declinando": "Analizando productos con ventas en declive",
        "obtener_ventas_por_producto": "Consultando ventas del producto",
        "buscar_info_publica_medico": "Buscando información pública en internet",
        "generar_brief_medico": "Generando brief (CRM + búsqueda web + historial visitas)",
        "generar_mensaje_cumpleanos": "Generando mensaje de cumpleaños con IA",
    }

    original_cb = agent.callback_handler

    def _tracker(**kwargs):
        event = kwargs.get("event")
        if isinstance(event, dict):
            start = event.get("contentBlockStart", {}).get("start", {})
            tu = start.get("toolUse", {})
            if tu and tu.get("name"):
                label = _FRIENDLY.get(tu["name"], tu["name"])
                tool_steps.append(label)

    agent.callback_handler = _tracker

    try:
        response = agent(prompt)
        response_text = str(response)

        if tool_steps:
            steps_md = "\n".join(f"- {s}" for s in tool_steps)
            response_text = (
                f"<details open>\n"
                f"<summary>Proceso del agente ({len(tool_steps)} herramientas)</summary>\n\n"
                f"{steps_md}\n\n</details>\n\n{response_text}"
            )

        return response_text
    except Exception as e:
        logger.error(f"Error en chat (session={session_id}): {e}")
        err_str = str(e).lower()
        if any(kw in err_str for kw in ("bedrock", "throttling", "model", "serviceexception")):
            return "El asistente no está disponible en este momento. Intentá de nuevo en unos minutos."
        return "Disculpá, no pude procesar tu consulta. ¿Querés intentar de nuevo?"
    finally:
        agent.callback_handler = original_cb
