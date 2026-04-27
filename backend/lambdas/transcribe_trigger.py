"""TranscribeLambda — Triggered by S3 ObjectCreated on the audio bucket.

Starts an Amazon Transcribe batch job for each uploaded audio file.
The Transcribe job completion triggers SummarizeLambda via EventBridge.
"""

import json
import logging
import os
import urllib.parse

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_REGION = os.environ.get("AWS_REGION", "us-east-1")
_AUDIO_BUCKET = os.environ.get("AUDIO_BUCKET_NAME", "")
_OUTPUT_BUCKET = os.environ.get("AUDIO_BUCKET_NAME", "")

transcribe_client = boto3.client("transcribe", region_name=_REGION)


def handler(event, context):
    """Process S3 ObjectCreated events and start Transcribe jobs."""
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        # Only process files under audio/ prefix
        if not key.startswith("audio/"):
            logger.info(f"Skipping non-audio key: {key}")
            continue

        media_uri = f"s3://{bucket}/{key}"
        # Use the S3 key as a unique job name (sanitized)
        job_name = f"pharmassist-{key.replace('/', '-').replace('.', '-')}"
        # Truncate to 200 chars (Transcribe limit)
        job_name = job_name[:200]

        # Detect media format from extension
        ext = key.rsplit(".", 1)[-1].lower() if "." in key else "webm"
        format_map = {
            "webm": "webm",
            "mp3": "mp3",
            "mp4": "mp4",
            "wav": "wav",
            "flac": "flac",
            "ogg": "ogg",
            "m4a": "mp4",
        }
        media_format = format_map.get(ext, "webm")

        logger.info(json.dumps({
            "action": "start_transcription",
            "bucket": bucket,
            "key": key,
            "job_name": job_name,
            "media_format": media_format,
        }))

        try:
            transcribe_client.start_transcription_job(
                TranscriptionJobName=job_name,
                Media={"MediaFileUri": media_uri},
                MediaFormat=media_format,
                LanguageCode="es-ES",
                OutputBucketName=_OUTPUT_BUCKET,
                OutputKey=f"transcripts/{job_name}.json",
                Settings={
                    "ShowSpeakerLabels": False,
                },
            )
            logger.info(f"Started transcription job: {job_name}")
        except transcribe_client.exceptions.ConflictException:
            logger.warning(f"Transcription job already exists: {job_name}")
        except Exception as e:
            logger.error(f"Failed to start transcription job: {e}", exc_info=True)
            raise

    return {"statusCode": 200}
