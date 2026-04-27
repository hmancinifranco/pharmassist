"""SummarizeLambda — Triggered by EventBridge when Transcribe job completes.

Fetches the transcript, invokes Bedrock Claude to generate a structured minuta,
and writes the result to the minutas_visitas DynamoDB table.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_REGION = os.environ.get("AWS_REGION_NAME", os.environ.get("AWS_REGION", "us-east-1"))
_AUDIO_BUCKET = os.environ.get("AUDIO_BUCKET_NAME", "")
_MINUTAS_TABLE = os.environ.get("MINUTAS_TABLE_NAME", "minutas_visitas")
_MODEL_ID = os.environ.get("SUMMARIZE_MODEL_ID", os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-2-lite-v1:0"))

transcribe_client = boto3.client("transcribe", region_name=_REGION)
s3_client = boto3.client("s3", region_name=_REGION)
bedrock_client = boto3.client("bedrock-runtime", region_name=_REGION)
dynamodb = boto3.resource("dynamodb", region_name=_REGION)


def handler(event, context):
    """Process Transcribe job completion events from EventBridge."""
    detail = event.get("detail", {})
    job_name = detail.get("TranscriptionJobName", "")
    job_status = detail.get("TranscriptionJobStatus", "")

    if not job_name.startswith("pharmassist-"):
        logger.info(f"Ignoring non-PharmAssist job: {job_name}")
        return {"statusCode": 200}

    if job_status != "COMPLETED":
        logger.warning(f"Job {job_name} status is {job_status}, skipping")
        return {"statusCode": 200}

    logger.info(f"Processing completed transcription job: {job_name}")

    try:
        # 1. Get transcription job details
        job_response = transcribe_client.get_transcription_job(
            TranscriptionJobName=job_name
        )
        job = job_response["TranscriptionJob"]
        media_uri = job["Media"]["MediaFileUri"]

        # Extract audio S3 key from media URI
        # Format: s3://bucket/audio/apm_id/medico_mn/uuid.webm
        audio_s3_key = media_uri.split(f"s3://{_AUDIO_BUCKET}/")[-1] if _AUDIO_BUCKET in media_uri else ""

        # Extract apm_id and medico_mn from S3 object metadata
        apm_id = ""
        medico_mn = 0
        if audio_s3_key and _AUDIO_BUCKET:
            try:
                head = s3_client.head_object(Bucket=_AUDIO_BUCKET, Key=audio_s3_key)
                metadata = head.get("Metadata", {})
                from urllib.parse import unquote
                apm_id = unquote(metadata.get("apm_id", ""))
                medico_mn = int(metadata.get("medico_mn", "0"))
            except Exception as meta_err:
                logger.warning(f"Could not read S3 metadata: {meta_err}")

        # Fallback: extract medico_mn from path
        if not medico_mn:
            parts = audio_s3_key.split("/")
            if len(parts) >= 3:
                try:
                    medico_mn = int(parts[1])
                except (ValueError, IndexError):
                    pass

        # 2. Get transcript text from output
        transcript_uri = job.get("Transcript", {}).get("TranscriptFileUri", "")
        transcription = _get_transcript_text(job_name, transcript_uri)

        if not transcription:
            logger.error(f"Empty transcription for job {job_name}")
            _write_minuta_error(apm_id, medico_mn, audio_s3_key, "Transcripción vacía")
            return {"statusCode": 200}

        # 3. Generate structured minuta via Bedrock
        minuta_data = _generate_minuta(transcription)

        # 4. Write to DynamoDB
        minuta_id = str(uuid.uuid4())
        fecha = datetime.now(timezone.utc).isoformat()

        table = dynamodb.Table(_MINUTAS_TABLE)
        item = {
            "Minuta_ID": minuta_id,
            "APM": apm_id,
            "Medico_MN": medico_mn,
            "Fecha_Creacion": fecha,
            "Transcripcion": transcription,
            "Resumen": minuta_data.get("resumen", ""),
            "Productos_Discutidos": minuta_data.get("productos_discutidos", ""),
            "Compromisos": minuta_data.get("compromisos", ""),
            "Proximos_Pasos": minuta_data.get("proximos_pasos", ""),
            "Audio_S3_Key": audio_s3_key,
            "Estado": "listo",
        }
        table.put_item(Item=item)

        logger.info(json.dumps({
            "action": "minuta_saved",
            "minuta_id": minuta_id,
            "apm_id": apm_id,
            "medico_mn": medico_mn,
            "job_name": job_name,
        }))

        return {"statusCode": 200}

    except Exception as e:
        logger.error(f"Error processing job {job_name}: {e}", exc_info=True)
        raise


def _get_transcript_text(job_name: str, transcript_uri: str) -> str:
    """Fetch transcript text from the S3 output or URI."""
    try:
        # Try reading from our output bucket first
        output_key = f"transcripts/{job_name}.json"
        response = s3_client.get_object(Bucket=_AUDIO_BUCKET, Key=output_key)
        transcript_data = json.loads(response["Body"].read().decode("utf-8"))
        return transcript_data["results"]["transcripts"][0]["transcript"]
    except Exception:
        logger.warning(f"Could not read transcript from S3 output, trying URI: {transcript_uri}")

    # Fallback: fetch from the Transcribe-provided URI
    if transcript_uri:
        import urllib.request
        try:
            with urllib.request.urlopen(transcript_uri) as resp:
                transcript_data = json.loads(resp.read().decode("utf-8"))
            return transcript_data["results"]["transcripts"][0]["transcript"]
        except Exception as e:
            logger.error(f"Failed to fetch transcript from URI: {e}")

    return ""


def _generate_minuta(transcription: str) -> dict:
    """Invoke Bedrock Claude to generate a structured minuta from transcription."""
    prompt = (
        "A partir de la siguiente transcripción de una visita médica de un "
        "visitador médico (APM) a un doctor, generá una minuta estructurada.\n\n"
        "Respondé SOLO con un JSON válido (sin markdown, sin explicaciones) "
        "con estos campos:\n"
        '{"resumen": "párrafo resumen de la visita", '
        '"productos_discutidos": "PRODUCTO1|PRODUCTO2", '
        '"compromisos": "compromisos acordados", '
        '"proximos_pasos": "próximos pasos"}\n\n'
        "Si no hay productos discutidos, usá string vacío. "
        "Los productos deben estar separados por pipe (|).\n\n"
        f"Transcripción:\n{transcription}"
    )

    try:
        # Build request body — Nova models use Messages API without anthropic_version
        body: dict = {
            "inferenceConfig": {"maxTokens": 2048, "temperature": 0.3},
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
        }
        if "anthropic" in _MODEL_ID:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2048,
                "temperature": 0.3,
                "messages": [{"role": "user", "content": prompt}],
            }

        response = bedrock_client.invoke_model(
            modelId=_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        result = json.loads(response["body"].read().decode("utf-8"))

        # Extract text — Nova uses output.message.content[0].text, Anthropic uses content[0].text
        if "output" in result:
            text = result["output"]["message"]["content"][0]["text"]
        else:
            text = result.get("content", [{}])[0].get("text", "")

        # Strip markdown fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]

        return json.loads(cleaned.strip())
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse Bedrock response as JSON: {e}")
        return {
            "resumen": text if "text" in dir() else "",
            "productos_discutidos": "",
            "compromisos": "",
            "proximos_pasos": "",
        }
    except Exception as e:
        logger.error(f"Bedrock invocation failed: {e}", exc_info=True)
        return {
            "resumen": "",
            "productos_discutidos": "",
            "compromisos": "",
            "proximos_pasos": "",
        }


def _write_minuta_error(apm_id: str, medico_mn: int, audio_s3_key: str, error_msg: str):
    """Write an error-state minuta to DynamoDB for tracking."""
    try:
        table = dynamodb.Table(_MINUTAS_TABLE)
        table.put_item(Item={
            "Minuta_ID": str(uuid.uuid4()),
            "APM": apm_id,
            "Medico_MN": medico_mn,
            "Fecha_Creacion": datetime.now(timezone.utc).isoformat(),
            "Transcripcion": "",
            "Resumen": f"Error: {error_msg}",
            "Productos_Discutidos": "",
            "Compromisos": "",
            "Proximos_Pasos": "",
            "Audio_S3_Key": audio_s3_key,
            "Estado": "error",
        })
    except Exception as e:
        logger.error(f"Failed to write error minuta: {e}")
