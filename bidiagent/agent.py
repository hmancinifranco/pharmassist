"""
BidiAgent entrypoint for PharmAssist Voice Agent.

Uses FastAPI + Strands BidiAgent for deployment in Amazon Bedrock AgentCore
with container deployment + WebSocket protocol.

Based on the official AWS sample:
https://github.com/aws-samples/sample-nova-sonic-websocket-agentcore

The BidiAgent uses Nova Sonic for bidirectional speech-to-speech and
delegates data queries to the existing Text Agent via the
``consultarAsistente`` tool.
"""

import os
import logging
import json
import re
from datetime import datetime

import boto3
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from strands import tool
from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.models import BidiNovaSonicModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Configuration from environment variables
# ---------------------------------------------------------------------------

TEXT_AGENT_ARN = os.environ.get("TEXT_AGENT_ARN", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0")

SYSTEM_PROMPT = (
    "Sos el asistente de voz de PharmAssist para Agentes de Propaganda Médica "
    "(APMs) de una farmacéutica argentina. Respondé en español argentino.\n\n"
    "REGLAS ESTRICTAS PARA RESPUESTAS DE VOZ:\n"
    "- Máximo 2 a 3 oraciones por respuesta. Sé breve y directo.\n"
    "- NUNCA uses markdown, tablas, listas con viñetas, asteriscos ni emojis.\n"
    "- NUNCA leas datos en formato tabla. Resumí: 'Tenés 4 visitas hoy' en vez "
    "de listar cada una.\n"
    "- Si hay muchos datos, mencioná los más relevantes y ofrecé dar más detalle.\n"
    "- Usá la herramienta consultarAsistente para cualquier consulta de datos.\n"
    "- Las respuestas se escuchan, no se leen. Optimizá para audio."
)

# ---------------------------------------------------------------------------
# Module-level apm_id — set per WebSocket session
# ---------------------------------------------------------------------------

_current_apm_id: str = ""

# ---------------------------------------------------------------------------
# AWS client for invoking the Text Agent
# ---------------------------------------------------------------------------

agentcore_client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def extract_agent_id(arn: str) -> str:
    """Extract the agent ID from a Bedrock AgentCore ARN."""
    match = re.search(r"/([^/]+)$", arn)
    if match:
        return match.group(1)
    return arn


def build_payload(pregunta: str, apm_id: str) -> str:
    """Build the JSON payload for the Text Agent invocation."""
    return json.dumps({
        "prompt": pregunta,
        "apm_id": apm_id,
        "mode": "voice",
    })


def validate_apm_id(apm_id: str) -> bool:
    """Return True if *apm_id* is non-empty with at least one non-whitespace char."""
    return bool(apm_id and apm_id.strip())


# ---------------------------------------------------------------------------
# Tool: consultarAsistente
# ---------------------------------------------------------------------------


@tool
def consultarAsistente(pregunta: str) -> str:
    """Consulta al asistente PharmAssist para obtener datos de médicos,
    visitas, ventas, minutas, sugerencias de próxima visita y más.
    Usá esta herramienta siempre que el APM pregunte algo que requiera
    datos del sistema.

    Args:
        pregunta: La pregunta del APM en lenguaje natural
    """
    global _current_apm_id
    apm_id = _current_apm_id

    if not validate_apm_id(apm_id):
        logger.warning("apm_id vacío o inválido, no se invoca Text Agent")
        return "No se pudo identificar al usuario. Intentá reconectarte."

    try:
        payload = build_payload(pregunta, apm_id)

        # runtimeSessionId must be >= 33 chars and match [0-9a-zA-Z._:-]+
        import uuid
        safe_session = f"voice-{uuid.uuid4()}"

        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=TEXT_AGENT_ARN,
            runtimeSessionId=safe_session,
            payload=payload.encode("utf-8"),
        )

        # Read streaming response
        result = ""
        content_type = response.get("contentType", "")
        if "text/event-stream" in content_type:
            for line in response["response"].iter_lines(chunk_size=10):
                if not line:
                    continue
                text = line.decode("utf-8") if isinstance(line, bytes) else line
                if text.startswith("data:"):
                    try:
                        chunk_data = json.loads(text[5:].strip())
                        if "text" in chunk_data:
                            result += chunk_data["text"]
                    except json.JSONDecodeError:
                        result += text[5:].strip()
                elif not text.startswith(":"):
                    result += text
        else:
            body = response.get("response", b"")
            if hasattr(body, "read"):
                body = body.read()
            if isinstance(body, bytes):
                body = body.decode("utf-8")
            try:
                parsed = json.loads(body)
                result = parsed.get("result", str(parsed))
            except (json.JSONDecodeError, TypeError):
                result = str(body)

        return result or "No obtuve respuesta del asistente."
    except Exception as e:
        logger.error(f"Error invocando Text Agent: {e}")
        return "Lo siento, no pude obtener la información en este momento."


# ---------------------------------------------------------------------------
# Nova Sonic model
# ---------------------------------------------------------------------------

sonic_model = BidiNovaSonicModel(
    model_id=BEDROCK_MODEL_ID,
    provider_config={
        "audio": {
            "voice": "lupe",
            "input_rate": 16000,
            "output_rate": 16000,
            "channels": 1,
            "format": "pcm",
        },
        "inference": {},
    },
    client_config={
        "region": BEDROCK_REGION,
    },
)

# ---------------------------------------------------------------------------
# FastAPI app (matches the official AWS sample pattern)
# ---------------------------------------------------------------------------

app = FastAPI()


@app.get("/ping")
async def ping():
    """Health check endpoint required by AgentCore Runtime."""
    return {"status": "Healthy", "time_of_last_update": int(datetime.now().timestamp())}


@app.websocket("/ws")
async def voice_chat(websocket: WebSocket) -> None:
    """WebSocket endpoint for bidirectional voice streaming."""
    global _current_apm_id

    voice_agent = BidiAgent(
        model=sonic_model,
        tools=[consultarAsistente],
        system_prompt=SYSTEM_PROMPT,
    )

    try:
        await websocket.accept()
        logger.info("WebSocket connection accepted")

        # The first message from the client is an init event with apm_id.
        # Capture it before handing off to BidiAgent.
        first_msg = await websocket.receive_json()
        if isinstance(first_msg, dict) and first_msg.get("type") == "init":
            _current_apm_id = first_msg.get("apm_id", "")
            logger.info(f"Voice session apm_id: {_current_apm_id[:30] if _current_apm_id else '(empty)'}")
        else:
            # Not an init message — could be audio already. Set empty apm_id
            # and push the message back by wrapping receive_json.
            _current_apm_id = ""
            logger.warning("First message was not init event, apm_id unknown")

            # Create a wrapper that yields the first message then continues
            first_yielded = False

            async def patched_receive():
                nonlocal first_yielded
                if not first_yielded:
                    first_yielded = True
                    return first_msg
                return await websocket.receive_json()

            await voice_agent.run(
                inputs=[patched_receive],
                outputs=[websocket.send_json],
            )
            return

        await voice_agent.run(
            inputs=[websocket.receive_json],
            outputs=[websocket.send_json],
        )
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Error in voice chat: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await websocket.close()
            await voice_agent.stop()
        except Exception as cleanup_error:
            logger.debug(f"Error during cleanup: {cleanup_error}")


# ---------------------------------------------------------------------------
# Local development / AgentCore container entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting voice agent on port 8080...")
    logger.info(f"Model: {BEDROCK_MODEL_ID}")
    logger.info(f"Region: {AWS_REGION}, Bedrock Region: {BEDROCK_REGION}")

    host = "0.0.0.0" if os.getenv("CONTAINER_ENV") else "127.0.0.1"
    uvicorn.run(app, host=host, port=8080)
