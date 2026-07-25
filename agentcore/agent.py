"""
Unified Agent — AgentCore entry point for PharmAssist.

Este módulo define el entry point del runtime AgentCore unificado que reemplaza
7 tools CSV/DynamoDB por un único agente con 5 tools (query_db, buscar_info_publica,
generar_brief, obtener_minutas, generar_mensaje_cumpleanos).

Payload esperado:
    {
        "prompt": str,           # Pregunta del APM en lenguaje natural
        "apm_id": str,           # ID del APM autenticado (ej: "APM_001")
        "session_id": str,       # ID de sesión WebSocket
        "mode": "text" | "voice" # Opcional, default "text"
    }

Respuesta:
    {
        "result": str,           # Respuesta en Markdown
        "structured": {          # Metadata para rendering frontend (solo mode=text)
            "table": {"columns": [...], "rows": [...]},
            "sql": str,
            "chart": {"type": str, "data": [...]},
            "suggestions": [str, ...]
        },
        "success": bool,
        "retries": int
    }

Configuración via env vars:
    - BEDROCK_MODEL_ID: Inference profile ID (default: us.anthropic.claude-sonnet-5)
    - AWS_REGION: Región AWS (default: us-east-1)
    - DB_SECRET_ARN: ARN de Secrets Manager con credenciales Aurora PostgreSQL
    - MINUTAS_TABLE_NAME: Tabla DynamoDB para minutas de visitas
    - AGENTCORE_MEMORY_ID: ID del recurso AgentCore Memory

Inicialización lazy: el Agent se crea en la primera invocación, no al cargar el módulo.
Esto permite que el container arranque rápido y pase health checks.

Requirements: 1.1, 18.1, 18.2
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Ensure the agentcore directory is on sys.path so that local packages
# (tools/, models/, data/, agents/, utils/) resolve correctly.
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from bedrock_agentcore import BedrockAgentCoreApp  # noqa: E402

# Dual-path imports: support both local development (from agentcore.X)
# and AgentCore runtime (from X directly, since /var/task is the root)
try:
    from agentcore.response_formatter import ResponseFormatter  # noqa: E402
    from agentcore.observability import (  # noqa: E402
        RequestTracer,
        emit_error_metric,
        emit_metric,
        timed_operation,
    )
except ModuleNotFoundError:
    from response_formatter import ResponseFormatter  # noqa: E402
    from observability import (  # noqa: E402
        RequestTracer,
        emit_error_metric,
        emit_metric,
        timed_operation,
    )

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class UnifiedAgentConfig:
    """Configuración del Unified Agent cargada desde variables de entorno.

    Attributes:
        model_id: Bedrock inference profile ID para el modelo LLM.
        region: Región AWS donde se ejecuta el agente.
        db_secret_arn: ARN de Secrets Manager con credenciales de Aurora PostgreSQL.
        minutas_table_name: Nombre de la tabla DynamoDB para minutas.
        memory_id: ID del recurso AgentCore Memory para STM y semantic memory.
    """

    model_id: str = field(default_factory=lambda: os.environ.get(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-5"
    ))
    region: str = field(default_factory=lambda: os.environ.get(
        "AWS_REGION", "us-east-1"
    ))
    db_secret_arn: str = field(default_factory=lambda: os.environ.get(
        "DB_SECRET_ARN", ""
    ))
    minutas_table_name: str = field(default_factory=lambda: os.environ.get(
        "MINUTAS_TABLE_NAME", ""
    ))
    memory_id: str = field(default_factory=lambda: os.environ.get(
        "AGENTCORE_MEMORY_ID", ""
    ))


# ---------------------------------------------------------------------------
# Lazy Agent Initialization
# ---------------------------------------------------------------------------

# Module-level cache for the agent instance (created on first invocation)
_agent_instance: Optional[Any] = None
_agent_config: Optional[UnifiedAgentConfig] = None

# Module-level variables for current request context.
# Updated per-request so the agent's system prompt reflects the authenticated APM.
_current_apm_id: Optional[str] = None
_current_ciclo: Optional[str] = None


def _get_config() -> UnifiedAgentConfig:
    """Return the singleton config, creating it on first access."""
    global _agent_config
    if _agent_config is None:
        _agent_config = UnifiedAgentConfig()
        logger.info(
            "UnifiedAgentConfig loaded: model_id=%s, region=%s",
            _agent_config.model_id,
            _agent_config.region,
        )
    return _agent_config


def _get_or_create_agent():
    """Return the cached Strands Agent, creating it lazily on first call.

    Lazy initialization ensures the container starts quickly and passes
    health checks before loading heavy dependencies (model, tools, prompt).

    Returns:
        A configured strands Agent instance.
    """
    global _agent_instance

    if _agent_instance is not None:
        return _agent_instance

    config = _get_config()

    from strands import Agent
    from strands.models import BedrockModel

    try:
        from agentcore.toolkit import query_db
        from agentcore.utils_tools import (
            buscar_info_publica,
            generar_brief,
            generar_mensaje_cumpleanos,
            obtener_minutas,
        )
        from agentcore.prompts import build_system_prompt
    except ModuleNotFoundError:
        from toolkit import query_db
        from utils_tools import (
            buscar_info_publica,
            generar_brief,
            generar_mensaje_cumpleanos,
            obtener_minutas,
        )
        from prompts import build_system_prompt

    # Nota: Claude Sonnet 5 (y otros modelos de razonamiento nuevos) deprecaron
    # el parámetro `temperature`. Se omite para ser compatible con esos modelos;
    # los modelos que lo soportan usan su valor por defecto.
    model = BedrockModel(
        model_id=config.model_id,
        region_name=config.region,
        max_tokens=4096,
    )

    # 5 tools: query_db + 4 utility tools
    tools: list = [
        query_db,
        buscar_info_publica,
        generar_brief,
        obtener_minutas,
        generar_mensaje_cumpleanos,
    ]

    # Build system prompt with current APM context.
    # On first init, use placeholder values. The prompt is rebuilt per-request
    # via _build_prompt_for_request() when apm_id is known.
    system_prompt = build_system_prompt(
        apm_id=_current_apm_id or "SYSTEM",
        ciclo_actual=_current_ciclo or "CICLO_ACTUAL",
    )

    _agent_instance = Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
    )

    logger.info("Unified Agent initialized (model=%s, tools=%d)", config.model_id, len(tools))
    return _agent_instance


# ---------------------------------------------------------------------------
# AgentCore Application
# ---------------------------------------------------------------------------

MAX_RETRIES = 2

app = BedrockAgentCoreApp()


@app.entrypoint
def handle_invoke(payload: dict, context: Any = None) -> dict:
    """Entry point principal del Unified Agent para AgentCore.

    Recibe el payload del Lambda Proxy (validado por AgentCore Identity),
    ejecuta el agente con retry logic, y retorna la respuesta estructurada.

    Args:
        payload: Dict con prompt, apm_id, session_id, y mode opcionales.
        context: Contexto AgentCore runtime (reservado para uso futuro).

    Returns:
        Dict con result, structured, success, y retries.
    """
    prompt = payload.get("prompt", "")
    apm_id = payload.get("apm_id", "")
    session_id = payload.get("session_id", "")
    mode = payload.get("mode", "text")

    # Validación de mode
    if mode not in ("text", "voice"):
        mode = "text"

    # Validación de campos requeridos
    if not prompt:
        return _error_response(
            "No se recibió ningún mensaje. Enviá un prompt para consultar.",
            retries=0,
        )

    if not apm_id:
        return _error_response(
            "Falta el identificador del APM (apm_id).",
            retries=0,
        )

    # Usar session_id del payload o generar uno basado en apm_id
    if not session_id:
        session_id = f"agentcore-{apm_id}"

    # Start request tracing (end-to-end latency + span)
    request_tracer = RequestTracer(apm_id=apm_id, session_id=session_id)
    request_tracer.start()

    # Ejecutar con retry logic
    result = _invoke_with_retries(
        prompt=prompt,
        apm_id=apm_id,
        session_id=session_id,
        mode=mode,
    )

    # Complete tracing with outcome
    if result.get("success", False):
        request_tracer.complete(success=True, retries=result.get("retries", 0))
    else:
        # Create a synthetic exception for the tracer from the error message
        request_tracer.fail(
            error=RuntimeError(result.get("result", "Unknown error")),
            retries=result.get("retries", 0),
        )

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _invoke_with_retries(
    prompt: str,
    apm_id: str,
    session_id: str,
    mode: str,
) -> dict:
    """Invoke the agent with retry logic using centralized ErrorHandler.

    Uses ErrorHandler.is_retryable() to determine retry eligibility and
    ErrorHandler.handle() for user-facing error responses. This ensures:
    - Consistent error classification across the application
    - No sensitive info leaks in user messages
    - Full error detail logged to CloudWatch
    - Memory errors trigger graceful degradation (proceed without memory)

    Implements intelligent retry behavior:
    - Non-retryable errors (ValueError, Aurora down) -> immediate failure
    - Retryable errors (throttling, timeout, SQL syntax) -> retry with context
    - Memory errors -> proceed without memory, no retry needed

    Attempts up to MAX_RETRIES additional tries for retryable errors.
    On each retry, appends a sanitized error hint to the prompt so the LLM
    can self-correct.

    Args:
        prompt: Natural language question from the APM.
        apm_id: Authenticated APM identifier.
        session_id: Session identifier for memory context.
        mode: "text" (full structured response) or "voice" (simplified).

    Returns:
        Response dict with result, structured, success, retries.

    Requirements: 3.1, 3.2, 3.3, 3.4, 20.1, 20.2, 20.3, 20.4, 20.5
    """
    global _current_apm_id, _current_ciclo

    try:
        from agentcore.error_handler import ErrorHandler
    except ModuleNotFoundError:
        from error_handler import ErrorHandler

    # Update module-level context for system prompt scoping
    _current_apm_id = apm_id
    _current_ciclo = os.environ.get("CICLO_ACTUAL", "CICLO_ACTUAL")

    # Rebuild agent system prompt with current APM context
    agent = _get_or_create_agent()

    try:
        from agentcore.prompts import build_system_prompt
    except ModuleNotFoundError:
        from prompts import build_system_prompt
    agent.system_prompt = build_system_prompt(
        apm_id=apm_id,
        ciclo_actual=_current_ciclo,
    )

    current_prompt = prompt
    last_error = None

    try:
        from agentcore.toolkit import reset_captured_queries, get_captured_queries
    except ModuleNotFoundError:
        from toolkit import reset_captured_queries, get_captured_queries

    for attempt in range(MAX_RETRIES + 1):
        try:
            # Clear any queries captured by a previous (failed) attempt so we
            # only surface the data from the successful run.
            reset_captured_queries()

            response = agent(current_prompt)
            response_text = str(response)

            # The LLM's final text does not include the <!--STRUCTURED:--> marker
            # emitted by query_db. Re-append the last executed query's marker so
            # ResponseFormatter can populate structured.sql / table / chart with
            # the exact data that was queried (deterministic data provenance).
            captured = get_captured_queries()
            if captured and "<!--STRUCTURED:" not in response_text:
                import json as _json
                last = captured[-1]
                marker = _json.dumps(last, ensure_ascii=False, default=str)
                response_text = f"{response_text}\n\n<!--STRUCTURED:{marker}-->"

            # Build response based on mode
            if mode == "voice":
                try:
                    from agentcore.voice_filter import strip_for_voice
                except ModuleNotFoundError:
                    from voice_filter import strip_for_voice
                clean_text = strip_for_voice(response_text)
                return {
                    "result": clean_text,
                    "success": True,
                    "retries": attempt,
                }
            else:
                formatted = ResponseFormatter.format_response(response_text, prompt)
                return {
                    "result": formatted["result"],
                    "structured": formatted["structured"],
                    "success": True,
                    "retries": attempt,
                }

        except Exception as e:
            last_error = e

            # Memory errors: proceed without memory (graceful degradation)
            if ErrorHandler.is_memory_error(e):
                logger.warning(
                    "Memory unavailable for APM %s (attempt %d): %s. "
                    "Proceeding without memory context.",
                    apm_id,
                    attempt + 1,
                    str(e),
                )
                # Continue to next attempt without memory
                continue

            # Non-retryable errors: fail immediately with user-friendly message
            if not ErrorHandler.is_retryable(e):
                error_response = ErrorHandler.handle(e, context=f"invoke_apm_{apm_id}")
                error_response["retries"] = attempt
                return error_response

            # Retryable: log and prepare for next attempt
            logger.warning(
                "Intento %d/%d error para APM %s [%s]: %s",
                attempt + 1,
                MAX_RETRIES + 1,
                apm_id,
                type(e).__name__,
                str(e),
            )

            # If retries remain, augment prompt with sanitized error context
            if attempt < MAX_RETRIES:
                sanitized_hint = ErrorHandler.sanitize_message(str(e))

                if isinstance(e, TimeoutError):
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"[NOTA: La query anterior excedió el timeout de 5 segundos. "
                        f"Error: {sanitized_hint}. "
                        f"Simplificá la query: usá filtros más restrictivos, "
                        f"evitá JOINs innecesarios, o limitá los resultados con LIMIT.]"
                    )
                elif isinstance(e, RuntimeError):
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"[NOTA: La query SQL generada falló con: {sanitized_hint}. "
                        f"Corregí la query SQL y reintentá. Verificá nombres de columnas "
                        f"y tablas, y la sintaxis SQL.]"
                    )
                else:
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"[NOTA: El intento anterior falló con: {sanitized_hint}. "
                        f"Por favor corregí y reintentá.]"
                    )

    # All retries exhausted — use ErrorHandler for the final error message
    if last_error:
        error_response = ErrorHandler.handle(last_error, context=f"retries_exhausted_apm_{apm_id}")
        error_response["retries"] = MAX_RETRIES
        return error_response

    return _error_response(
        "No pude procesar tu consulta después de varios intentos. "
        "Por favor reformulá la pregunta o intentá de nuevo en unos minutos.",
        retries=MAX_RETRIES,
    )


def _error_response(message: str, retries: int = 0) -> dict:
    """Build a standardized error response.

    Never exposes internal details — only user-friendly messages in Spanish.

    Args:
        message: User-facing error message in Spanish.
        retries: Number of retries attempted.

    Returns:
        Response dict with success=False.
    """
    return {
        "result": message,
        "structured": {},
        "success": False,
        "retries": retries,
    }


# ---------------------------------------------------------------------------
# Main — standalone execution or AgentCore deploy
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run()
