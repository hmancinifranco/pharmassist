"""
PharmAssist API — FastAPI endpoints.

Provides REST endpoints for the dashboard cards, chat, audio transcription,
and minuta management. All endpoints filter by apm_id for data isolation.
"""

import json as json_mod
import logging
import os
import tempfile
import time
import urllib.request
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

try:
    from backend.agents.assistant import chat as agent_chat
    from backend.models.schemas import ChatRequest, ChatResponse, Medico
    from backend.utils.birthday_utils import filtrar_cumpleanos_proximos
    from backend.utils.sla_utils import obtener_alertas_sla
except ImportError:
    from agents.assistant import chat as agent_chat  # type: ignore[no-redef]
    from models.schemas import ChatRequest, ChatResponse, Medico  # type: ignore[no-redef]
    from utils.birthday_utils import filtrar_cumpleanos_proximos  # type: ignore[no-redef]
    from utils.sla_utils import obtener_alertas_sla  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AgentCore proxy configuration
# ---------------------------------------------------------------------------

_AGENTCORE_AGENT_ARN = os.environ.get("AGENTCORE_AGENT_ARN", "")
_BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-6-v1")


def _generate_text_bedrock(prompt: str) -> str:
    """Generate text using Bedrock invoke_model directly (no agent/tools needed).

    Used for simple text generation tasks like birthday messages where the
    full Strands agent is overkill.
    """
    client = boto3.client("bedrock-runtime", region_name=_REGION)
    body = json_mod.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt}],
    })
    response = client.invoke_model(
        modelId=_BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json_mod.loads(response["body"].read())
    return result["content"][0]["text"]


def _invoke_agentcore(prompt: str, apm_id: str, session_id: str) -> str:
    """Invoke the AgentCore-deployed agent via boto3 bedrock-agentcore client.

    Sends the prompt+apm_id payload and collects the streaming response into
    a single string.  Falls back to raising an exception on failure so the
    caller can decide how to handle it.
    """
    client = boto3.client(
        "bedrock-agentcore",
        region_name=os.environ.get("AGENTCORE_REGION", _REGION),
    )

    payload = json_mod.dumps({"prompt": prompt, "apm_id": apm_id}).encode()

    response = client.invoke_agent_runtime(
        agentRuntimeArn=_AGENTCORE_AGENT_ARN,
        runtimeSessionId=session_id,
        payload=payload,
    )

    content_type = response.get("contentType", "")

    if "text/event-stream" in content_type:
        # Streaming response — collect all data lines
        parts: list[str] = []
        for line in response["response"].iter_lines(chunk_size=10):
            if line:
                decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                if decoded.startswith("data: "):
                    parts.append(decoded[6:])
                else:
                    parts.append(decoded)
        return "".join(parts)

    if content_type == "application/json":
        # Standard JSON response
        chunks: list[str] = []
        for chunk in response.get("response", []):
            chunks.append(
                chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            )
        body = json_mod.loads("".join(chunks))
        return body.get("result", str(body))

    # Fallback — try to read raw response
    raw = response.get("response")
    if raw:
        data = b"".join(
            c if isinstance(c, bytes) else c.encode() for c in raw
        )
        try:
            body = json_mod.loads(data)
            return body.get("result", str(body))
        except (json_mod.JSONDecodeError, ValueError):
            return data.decode("utf-8", errors="replace")

    return ""

# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="PharmAssist API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

_REGION = os.environ.get("AWS_REGION", "us-east-1")
_MEDICOS_TABLE = os.environ.get("MEDICOS_TABLE_NAME", "crm_medicos")
_PLANIFICADAS_TABLE = os.environ.get("PLANIFICADAS_TABLE_NAME", "visitas_planificadas")
_MINUTAS_TABLE = os.environ.get("MINUTAS_TABLE_NAME", "minutas_visitas")


# ---------------------------------------------------------------------------
# JWT claim extraction — apm_id from Cognito authorizer
# ---------------------------------------------------------------------------


def _get_apm_id_from_jwt(request: Request) -> Optional[str]:
    """Extract apm_id from API Gateway JWT authorizer claims.

    When the HTTP API uses a Cognito JWT authorizer, the validated claims are
    injected at ``event.requestContext.authorizer.jwt.claims``.  Mangum stores
    the original Lambda event in the ASGI scope under ``aws.event``.

    Returns the ``custom:apm_id`` claim value, or *None* if not present (e.g.
    running locally without API Gateway).
    """
    try:
        event = request.scope.get("aws.event", {})
        claims = (
            event.get("requestContext", {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})
        )
        return claims.get("custom:apm_id") or None
    except Exception:
        return None


def _resolve_apm_id(
    request: Request,
    apm_id: Optional[str] = Query(None, description="APM identifier (fallback for local dev)"),
) -> str:
    """Resolve apm_id: prefer JWT claim, fall back to query param for local dev."""
    jwt_apm_id = _get_apm_id_from_jwt(request)
    resolved = jwt_apm_id or apm_id
    if not resolved:
        raise HTTPException(
            status_code=401,
            detail="No se pudo identificar al APM. Iniciá sesión nuevamente.",
        )
    return resolved


def _dynamodb():
    return boto3.resource("dynamodb", region_name=_REGION)


def _serialize(item: dict) -> dict:
    """Convert DynamoDB Decimals to int/float for JSON serialization."""
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


def _dynamo_item_to_medico(item: dict) -> Medico:
    """Convert a raw DynamoDB item dict into a Medico Pydantic model."""
    s = _serialize(item)
    return Medico(
        medico_mn=s.get("Medico_MN", 0),
        nombre=s.get("Nombre", ""),
        apellido=s.get("Apellido", ""),
        especialidad_medica=s.get("Especialidad_Medica", ""),
        zona=s.get("Zona", ""),
        apm=s.get("APM", ""),
        cadencia=s.get("Cadencia", ""),
        fecha_nacimiento=s.get("Fecha_Nacimiento") or None,
        fecha_ultima_visita=s.get("Fecha_Ultima_Visita") or None,
        telefono_celular=s.get("Telefono_Celular") or None,
        telefono_consultorio=s.get("Telefono_Consultorio") or None,
        mail=s.get("Mail") or None,
        hobby_intereses=s.get("Hobby_Intereses") or None,
        religion=s.get("Religion") or None,
        hospital=s.get("Hospital") or None,
        facultad=s.get("Facultad") or None,
        anio_egresado=s.get("Anio_Egresado") or None,
        calle=s.get("Calle") or None,
        altura=s.get("Altura") or None,
        barrio=s.get("Barrio") or None,
        latitud=s.get("Latitud") or None,
        longitud=s.get("Longitud") or None,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 1. POST /api/chat
# ---------------------------------------------------------------------------


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, request: Request):
    """Send a message to the Strands agent and return the response.

    Always uses the local Strands agent (which has all tools and DynamoDB access).
    AgentCore is available as a standalone endpoint for direct invocation.
    """
    try:
        session_id = req.session_id or str(uuid.uuid4())

        # Prefer JWT claim for apm_id; fall back to request body for local dev
        apm_id = _get_apm_id_from_jwt(request) or req.apm_id

        response_text = agent_chat(
            message=req.message,
            apm_id=apm_id,
            session_id=session_id,
        )

        return ChatResponse(
            response=response_text,
            sources=[],
            session_id=session_id,
        )
    except Exception as e:
        logger.error(f"Error en /api/chat: {e}")
        # Detect Bedrock / model invocation failures
        err_str = str(e).lower()
        if any(
            kw in err_str
            for kw in ("bedrock", "throttling", "model", "invoke", "serviceexception")
        ):
            raise HTTPException(
                status_code=503,
                detail="El asistente no está disponible en este momento.",
            )
        raise HTTPException(
            status_code=500,
            detail="No se pudo procesar tu consulta. Intentá de nuevo.",
        )


# ---------------------------------------------------------------------------
# 2. GET /api/dashboard/visits-today
# ---------------------------------------------------------------------------


@app.get("/api/dashboard/visits-today")
async def visits_today(apm_id: str = Depends(_resolve_apm_id)):
    """Return planned visits for the current month, enriched with médico data."""
    try:
        hoy = date.today()
        # Query the full current month so the dashboard always has data for demos
        fecha_desde = hoy.replace(day=1).isoformat()
        # Last day of month
        if hoy.month == 12:
            fecha_hasta = hoy.replace(year=hoy.year + 1, month=1, day=1).isoformat()
        else:
            fecha_hasta = hoy.replace(month=hoy.month + 1, day=1).isoformat()

        db = _dynamodb()
        planificadas = db.Table(_PLANIFICADAS_TABLE)
        medicos_table = db.Table(_MEDICOS_TABLE)

        response = planificadas.query(
            IndexName="APM-Fecha-index",
            KeyConditionExpression=(
                Key("APM").eq(apm_id)
                & Key("Fecha_Planificada").between(fecha_desde, fecha_hasta)
            ),
        )
        items = response.get("Items", [])

        enriched: list[dict] = []
        for item in items:
            visit = _serialize(item)
            mn = item.get("Medico_MN")
            if mn is not None:
                try:
                    med_resp = medicos_table.get_item(Key={"Medico_MN": mn})
                    medico = med_resp.get("Item")
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
                    logger.warning(f"No se pudo enriquecer médico MN {mn}: {med_err}")
            enriched.append(visit)

        return {"visits": enriched}
    except Exception as e:
        logger.error(f"Error en /api/dashboard/visits-today: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error al consultar visitas planificadas.",
        )


# ---------------------------------------------------------------------------
# 2b. POST /api/dashboard/visits/complete
# ---------------------------------------------------------------------------


@app.post("/api/dashboard/visits/complete")
async def complete_visit(body: dict, request: Request):
    """Mark a planned visit as completed."""
    try:
        apm_id = _get_apm_id_from_jwt(request) or body.get("apm_id", "")
        fecha = body.get("fecha_planificada", "")
        medico_mn = body.get("medico_mn")

        if not apm_id or not fecha or medico_mn is None:
            raise HTTPException(status_code=400, detail="Faltan campos: apm_id, fecha_planificada, medico_mn")

        db = _dynamodb()
        table = db.Table(_PLANIFICADAS_TABLE)

        table.update_item(
            Key={
                "APM_Fecha": f"{apm_id}#{fecha}",
                "Medico_MN": medico_mn,
            },
            UpdateExpression="SET Estado = :e",
            ExpressionAttributeValues={":e": "Completada"},
        )

        return {"success": True, "message": "Visita marcada como completada"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en /api/dashboard/visits/complete: {e}")
        raise HTTPException(status_code=500, detail="Error al actualizar la visita.")


# ---------------------------------------------------------------------------
# 3. GET /api/dashboard/birthdays
# ---------------------------------------------------------------------------


@app.get("/api/dashboard/birthdays")
async def birthdays(apm_id: str = Depends(_resolve_apm_id)):
    """Return upcoming birthdays (30 days) — no message generation, fast."""
    try:
        db = _dynamodb()
        medicos_table = db.Table(_MEDICOS_TABLE)

        response = medicos_table.query(
            IndexName="APM-index",
            KeyConditionExpression=Key("APM").eq(apm_id),
        )
        items = response.get("Items", [])

        medicos = [_dynamo_item_to_medico(it) for it in items]
        cumples = filtrar_cumpleanos_proximos(medicos)

        results: list[dict] = []
        for entry in cumples:
            medico: Medico = entry["medico"]
            dias_hasta: int = entry["dias_hasta"]

            results.append({
                "medico": {
                    "medico_mn": medico.medico_mn,
                    "nombre": medico.nombre,
                    "apellido": medico.apellido,
                    "especialidad_medica": medico.especialidad_medica,
                    "telefono_celular": medico.telefono_celular,
                    "fecha_nacimiento": (
                        medico.fecha_nacimiento.isoformat()
                        if medico.fecha_nacimiento
                        else None
                    ),
                    "hobby_intereses": medico.hobby_intereses,
                    "hospital": medico.hospital,
                },
                "dias_hasta": dias_hasta,
                "mensaje_cumpleanos": "",
            })

        return {"birthdays": results}
    except Exception as e:
        logger.error(f"Error en /api/dashboard/birthdays: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error al consultar cumpleaños próximos.",
        )


# ---------------------------------------------------------------------------
# 3b. POST /api/dashboard/birthdays/generate-message
# ---------------------------------------------------------------------------


@app.post("/api/dashboard/birthdays/generate-message")
async def generate_birthday_message(body: dict, request: Request):
    """Generate a personalized birthday message for a single médico on demand."""
    try:
        apm_id = _get_apm_id_from_jwt(request) or body.get("apm_id", "")
        medico_mn = body.get("medico_mn")

        if not apm_id or medico_mn is None:
            raise HTTPException(status_code=400, detail="Faltan campos: apm_id, medico_mn")

        db = _dynamodb()
        medicos_table = db.Table(_MEDICOS_TABLE)

        med_resp = medicos_table.get_item(Key={"Medico_MN": medico_mn})
        item = med_resp.get("Item")
        if not item:
            raise HTTPException(status_code=404, detail="Médico no encontrado")

        medico = _dynamo_item_to_medico(item)

        # Verify APM ownership
        if medico.apm != apm_id:
            raise HTTPException(status_code=403, detail="No tenés acceso a este médico")

        # Calculate age
        edad_str = ""
        if medico.fecha_nacimiento:
            hoy = date.today()
            edad = hoy.year - medico.fecha_nacimiento.year
            if (hoy.month, hoy.day) < (medico.fecha_nacimiento.month, medico.fecha_nacimiento.day):
                edad -= 1
            edad_str = f"Cumple {edad + 1} años. "

        prompt = (
            f"Generá un mensaje de cumpleaños personalizado y cálido para "
            f"Dr/a. {medico.nombre} {medico.apellido}, "
            f"especialista en {medico.especialidad_medica}. "
            f"{edad_str}"
        )
        if medico.hobby_intereses:
            prompt += f"Sus hobbies e intereses son: {medico.hobby_intereses}. Mencioná alguno de forma natural. "
        if medico.religion:
            prompt += f"Es de religión {medico.religion}, podés incluir una referencia sutil si es apropiado. "
        if medico.hospital:
            prompt += f"Trabaja en {medico.hospital}. "
        if medico.facultad:
            prompt += f"Se graduó de {medico.facultad}. "
        prompt += (
            "El mensaje debe ser profesional pero cercano, en español argentino (voseo), "
            "y no más de 3-4 oraciones. Que se note que conocés al médico personalmente. "
            "NO uses emojis ni caracteres especiales — solo texto plano. "
            "Solo devolvé el mensaje listo para enviar por WhatsApp, sin explicaciones ni comillas."
        )

        mensaje = _generate_text_bedrock(prompt)

        return {"medico_mn": medico_mn, "mensaje": mensaje}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generando mensaje de cumpleaños: {e}")
        raise HTTPException(status_code=500, detail="No se pudo generar el mensaje.")


# ---------------------------------------------------------------------------
# 4. GET /api/dashboard/sla-alerts
# ---------------------------------------------------------------------------


@app.get("/api/dashboard/sla-alerts")
async def sla_alerts(apm_id: str = Depends(_resolve_apm_id)):
    """Return SLA breach alerts for the APM's médicos."""
    try:
        db = _dynamodb()
        medicos_table = db.Table(_MEDICOS_TABLE)

        response = medicos_table.query(
            IndexName="APM-index",
            KeyConditionExpression=Key("APM").eq(apm_id),
        )
        items = response.get("Items", [])

        medicos = [_dynamo_item_to_medico(it) for it in items]
        alertas = obtener_alertas_sla(medicos)

        results: list[dict] = []
        for alerta in alertas:
            medico: Medico = alerta["medico"]
            results.append({
                "medico_mn": medico.medico_mn,
                "nombre": f"{medico.nombre} {medico.apellido}",
                "especialidad": medico.especialidad_medica,
                "cadencia": alerta["cadencia"],
                "fecha_ultima_visita": alerta["fecha_ultima_visita"],
                "dias_vencido": alerta["dias_vencido"],
                "zona": medico.zona,
            })

        return {"alerts": results}
    except Exception as e:
        logger.error(f"Error en /api/dashboard/sla-alerts: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error al consultar alertas de SLA.",
        )


# ---------------------------------------------------------------------------
# 5a. GET /api/audio/presigned-url — S3 presigned PUT URL for audio upload
# ---------------------------------------------------------------------------

_AUDIO_BUCKET = os.environ.get("AUDIO_BUCKET_NAME", "")


@app.get("/api/audio/presigned-url")
async def audio_presigned_url(
    medico_mn: int = Query(..., description="Médico MN to associate the audio with"),
    apm_id: str = Depends(_resolve_apm_id),
):
    """Generate a presigned PUT URL for uploading audio to S3."""
    if not _AUDIO_BUCKET:
        raise HTTPException(status_code=500, detail="Audio bucket no configurado.")

    audio_key = f"audio/{medico_mn}/{uuid.uuid4()}.webm"
    s3_client = boto3.client("s3", region_name=_REGION)

    # S3 metadata only accepts ASCII — URL-encode non-ASCII values
    from urllib.parse import quote
    presigned_url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": _AUDIO_BUCKET,
            "Key": audio_key,
            "ContentType": "audio/webm",
            "Metadata": {
                "apm_id": quote(apm_id),
                "medico_mn": str(medico_mn),
            },
        },
        ExpiresIn=300,
    )

    return {"upload_url": presigned_url, "audio_key": audio_key}


# ---------------------------------------------------------------------------
# 5b. POST /api/audio/upload — Legacy direct upload (fallback)
# ---------------------------------------------------------------------------


@app.post("/api/audio/upload")
async def audio_upload(
    audio: UploadFile = File(...),
    medico_mn: int = Form(...),
):
    """Transcribe audio via Amazon Transcribe and generate a minuta draft."""
    tmp_path = None
    try:
        # Save audio to temp file
        suffix = ".webm"
        if audio.filename:
            suffix = os.path.splitext(audio.filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await audio.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Upload to S3 for Transcribe
        s3 = boto3.client("s3", region_name=_REGION)
        bucket = os.environ.get("AUDIO_BUCKET_NAME", "")
        s3_key = f"audio/{uuid.uuid4()}{suffix}"
        s3.upload_file(tmp_path, bucket, s3_key)
        media_uri = f"s3://{bucket}/{s3_key}"

        # Start transcription job
        transcribe = boto3.client("transcribe", region_name=_REGION)
        job_name = f"pharmassist-{uuid.uuid4()}"
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": media_uri},
            MediaFormat=suffix.lstrip("."),
            LanguageCode="es-ES",
        )

        # Poll for completion (simplified for demo)
        for _ in range(60):
            status = transcribe.get_transcription_job(
                TranscriptionJobName=job_name
            )
            job_status = status["TranscriptionJob"]["TranscriptionJobStatus"]
            if job_status == "COMPLETED":
                break
            if job_status == "FAILED":
                raise HTTPException(
                    status_code=500,
                    detail="No se pudo transcribir el audio. Intentá de nuevo.",
                )
            time.sleep(2)
        else:
            raise HTTPException(
                status_code=504,
                detail="La transcripción tardó demasiado. Intentá de nuevo.",
            )

        # Get transcription text
        transcript_uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
        with urllib.request.urlopen(transcript_uri) as resp:
            transcript_data = json_mod.loads(resp.read().decode())
        transcription = transcript_data["results"]["transcripts"][0]["transcript"]

        # Generate minuta via Bedrock Nova Lite 2 (fast, no agent overhead)
        prompt = (
            "A partir de la siguiente transcripción de una visita médica de un "
            "visitador médico (APM) a un doctor, generá una minuta estructurada.\n\n"
            "Respondé SOLO con un JSON válido (sin markdown, sin explicaciones) "
            "con estos campos:\n"
            '{"resumen": "párrafo resumen", '
            '"productos_discutidos": ["PROD1", "PROD2"], '
            '"compromisos": "compromisos acordados", '
            '"proximos_pasos": "próximos pasos"}\n\n'
            f"Transcripción:\n{transcription}"
        )
        bedrock_rt = boto3.client("bedrock-runtime", region_name=_REGION)
        nova_response = bedrock_rt.invoke_model(
            modelId="us.amazon.nova-2-lite-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json_mod.dumps({
                "inferenceConfig": {"maxTokens": 2048, "temperature": 0.3},
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
            }),
        )
        nova_result = json_mod.loads(nova_response["body"].read().decode("utf-8"))
        raw_response = nova_result.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")

        # Parse structured response; fallback to raw text as resumen
        minuta_draft: dict
        try:
            # Strip potential markdown code fences
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[: cleaned.rfind("```")]
            minuta_draft = json_mod.loads(cleaned.strip())
        except (json_mod.JSONDecodeError, ValueError):
            minuta_draft = {
                "resumen": raw_response,
                "productos_discutidos": [],
                "compromisos": "",
                "proximos_pasos": "",
            }

        return {
            "transcription": transcription,
            "minuta_draft": {
                "minuta_id": "",
                "medico_mn": medico_mn,
                "fecha_creacion": datetime.utcnow().isoformat(),
                "transcripcion": transcription,
                "resumen": minuta_draft.get("resumen", raw_response),
                "productos_discutidos": minuta_draft.get("productos_discutidos", []),
                "compromisos": minuta_draft.get("compromisos", ""),
                "proximos_pasos": minuta_draft.get("proximos_pasos", ""),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en /api/audio/upload: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar el audio. Intentá de nuevo.",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 6. POST /api/minutas
# ---------------------------------------------------------------------------


@app.post("/api/minutas")
async def save_minuta(body: dict, request: Request):
    """Save a minuta to the minutas_visitas DynamoDB table."""
    try:
        # Accept either flat body or nested minuta object
        minuta_data = body.get("minuta", body)
        apm_id = (
            _get_apm_id_from_jwt(request)
            or body.get("apm_id", minuta_data.get("apm_id", ""))
        )
        medico_mn_val = body.get("medico_mn", minuta_data.get("medico_mn"))

        if not apm_id or medico_mn_val is None:
            raise HTTPException(
                status_code=400,
                detail="Faltan campos requeridos: apm_id, medico_mn",
            )

        minuta_id = str(uuid.uuid4())
        fecha_creacion = datetime.utcnow().isoformat()

        db = _dynamodb()
        table = db.Table(_MINUTAS_TABLE)

        productos = minuta_data.get("productos_discutidos", [])
        if isinstance(productos, list):
            productos = "|".join(productos)

        item = {
            "Minuta_ID": minuta_id,
            "APM": apm_id,
            "Medico_MN": medico_mn_val,
            "Fecha_Creacion": fecha_creacion,
            "Transcripcion": minuta_data.get("transcripcion", ""),
            "Resumen": minuta_data.get("resumen", ""),
            "Productos_Discutidos": productos,
            "Compromisos": minuta_data.get("compromisos", ""),
            "Proximos_Pasos": minuta_data.get("proximos_pasos", ""),
        }

        table.put_item(Item=item)

        return {"minuta_id": minuta_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en POST /api/minutas: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error al guardar la minuta.",
        )


# ---------------------------------------------------------------------------
# 7. GET /api/minutas
# ---------------------------------------------------------------------------


@app.get("/api/minutas")
async def list_minutas(
    apm_id: str = Depends(_resolve_apm_id),
    medico_mn: Optional[int] = Query(None, description="Médico MN filter"),
):
    """List minutas, optionally filtered by médico."""
    try:
        db = _dynamodb()
        table = db.Table(_MINUTAS_TABLE)

        if medico_mn is not None:
            # Query by Medico-Fecha-index, then filter by APM
            response = table.query(
                IndexName="Medico-Fecha-index",
                KeyConditionExpression=Key("Medico_MN").eq(medico_mn),
                ScanIndexForward=False,
            )
            items = [
                it for it in response.get("Items", [])
                if it.get("APM") == apm_id
            ]
        else:
            # Query by APM-Fecha-index
            response = table.query(
                IndexName="APM-Fecha-index",
                KeyConditionExpression=Key("APM").eq(apm_id),
                ScanIndexForward=False,
            )
            items = response.get("Items", [])

        minutas = [_serialize(it) for it in items]
        return {"minutas": minutas}
    except Exception as e:
        logger.error(f"Error en GET /api/minutas: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error al consultar minutas.",
        )
