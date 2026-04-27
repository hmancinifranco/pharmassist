"""
AgentCore entrypoint for PharmAssist Strands Agent.

Wraps the existing Strands agent with BedrockAgentCoreApp so it can be
deployed and invoked via Amazon Bedrock AgentCore.

Payload format:
    {"prompt": "¿Cuáles son mis visitas de hoy?", "apm_id": "Demo APM"}
    {"prompt": "...", "apm_id": "...", "mode": "voice"}

Response format:
    {"result": "Tenés 4 visitas planificadas para hoy..."}

The ``mode`` field (``"text"`` default, ``"voice"``) controls response format.
Voice mode produces plain-text, concise responses optimised for speech output.
"""

import logging
import os
import sys

# ---------------------------------------------------------------------------
# Ensure the agentcore directory is on sys.path so that symlinked packages
# (tools/, models/, data/, agents/) resolve correctly with the dual-path
# imports already present in assistant.py and the tool modules.
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from bedrock_agentcore import BedrockAgentCoreApp  # noqa: E402

# Import the chat function from the shared agent module (symlinked)
from agents.assistant import chat  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# AgentCore application
# ---------------------------------------------------------------------------

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict, context: dict) -> dict:
    """Handle an AgentCore invocation.

    Args:
        payload: Must contain ``prompt`` (str) and ``apm_id`` (str).
        context: AgentCore runtime context (unused for now).

    Returns:
        ``{"result": "<agent response text>"}``
    """
    prompt = payload.get("prompt", "")
    apm_id = payload.get("apm_id", "")
    mode = payload.get("mode", "text")

    if mode not in ("text", "voice"):
        mode = "text"

    if not prompt:
        return {"result": "No se recibió ningún mensaje. Enviá un prompt para consultar."}

    if not apm_id:
        return {"result": "Falta el identificador del APM (apm_id). Incluilo en el payload."}

    # Use a deterministic session id per APM so context is preserved across
    # invocations within the same AgentCore session.
    session_id = f"agentcore-{apm_id}"

    try:
        response_text = chat(
            message=prompt,
            apm_id=apm_id,
            session_id=session_id,
            mode=mode,
        )
        return {"result": response_text}
    except Exception as e:
        logger.error(f"AgentCore invoke error: {e}", exc_info=True)
        return {
            "result": (
                "El asistente no está disponible en este momento. "
                "Intentá de nuevo en unos minutos."
            )
        }


if __name__ == "__main__":
    app.run()
