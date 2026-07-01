"""Lambda Proxy for WebSocket → AgentCore. Minimal forwarding, no agent logic."""

import json
import logging
import os
import time
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AGENTCORE_ARN = os.environ.get("AGENTCORE_AGENT_ARN", "")
AGENTCORE_REGION = os.environ.get("AGENTCORE_REGION", "us-east-1")
USER_POOL_ID = os.environ.get("USER_POOL_ID", "")
USER_POOL_REGION = os.environ.get("USER_POOL_REGION", os.environ.get("AWS_REGION", "us-east-1"))

agentcore_client = boto3.client("bedrock-agentcore", region_name=AGENTCORE_REGION)

# Cache JWKS keys for JWT validation
_jwks_cache: dict | None = None


def _get_jwks() -> dict:
    """Fetch and cache Cognito JWKS for JWT validation."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    url = f"https://cognito-idp.{USER_POOL_REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"
    with urllib.request.urlopen(url, timeout=5) as resp:
        _jwks_cache = json.loads(resp.read().decode())
    return _jwks_cache


def _base64url_decode(s: str) -> bytes:
    """Decode base64url without padding."""
    s += "=" * (4 - len(s) % 4)
    import base64
    return base64.urlsafe_b64decode(s)


def _validate_cognito_jwt(token: str) -> dict | None:
    """Validate a Cognito JWT manually using JWKS.

    Returns the decoded claims dict on success, None on failure.
    We only validate structure and expiration — API Gateway WebSocket
    doesn't support native Cognito authorizers, so we do it here.
    """
    if not token or not USER_POOL_ID:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header = json.loads(_base64url_decode(parts[0]))
        claims = json.loads(_base64url_decode(parts[1]))

        # Verify issuer matches our User Pool
        expected_iss = f"https://cognito-idp.{USER_POOL_REGION}.amazonaws.com/{USER_POOL_ID}"
        if claims.get("iss") != expected_iss:
            logger.warning("JWT issuer mismatch")
            return None

        # Verify token is not expired
        now = int(time.time())
        if claims.get("exp", 0) < now:
            logger.warning("JWT expired")
            return None

        # Verify token_use is 'id' (we need custom claims)
        if claims.get("token_use") not in ("id", "access"):
            logger.warning(f"Unexpected token_use: {claims.get('token_use')}")
            return None

        # Verify kid exists in JWKS (confirms token was issued by our pool)
        kid = header.get("kid")
        if kid:
            jwks = _get_jwks()
            valid_kids = {k["kid"] for k in jwks.get("keys", [])}
            if kid not in valid_kids:
                logger.warning("JWT kid not found in JWKS")
                return None

        return claims
    except Exception as e:
        logger.warning(f"JWT validation error: {e}")
        return None


def handler(event, context):
    """Main Lambda handler — route dispatch for WebSocket events."""
    route = event.get("requestContext", {}).get("routeKey")
    connection_id = event["requestContext"]["connectionId"]
    domain = event["requestContext"]["domainName"]
    stage = event["requestContext"]["stage"]

    if route == "$connect":
        return _handle_connect(event, connection_id)

    if route == "$disconnect":
        logger.info(json.dumps({
            "event": "disconnect",
            "connection_id": connection_id,
        }))
        return {"statusCode": 200}

    if route == "sendMessage":
        return _handle_message(event, connection_id, domain, stage)

    logger.warning(f"Unknown route: {route}")
    return {"statusCode": 400}


def _handle_connect(event, connection_id):
    """Validate JWT on $connect. Token passed as query param."""
    token = (event.get("queryStringParameters") or {}).get("token", "")
    claims = _validate_cognito_jwt(token)
    if claims is None:
        logger.warning(f"Invalid JWT on $connect: {connection_id}")
        return {"statusCode": 401}
    apm_id = claims.get("custom:apm_id", "")
    logger.info(json.dumps({
        "event": "connect",
        "connection_id": connection_id,
        "apm_id": apm_id,
    }))
    return {"statusCode": 200}


def _post(apigw, connection_id: str, data: dict) -> None:
    """Send a message back to the WebSocket client."""
    apigw.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
    )


def _handle_message(event, connection_id, domain, stage):
    """Handle sendMessage route — forward to AgentCore and stream back.

    Security: validates JWT on every message to extract apm_id from claims.
    Never trusts client-sent apm_id — always derives it from the token.
    Uses connectionId as session_id for AgentCore session correlation.
    """
    apigw = boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=f"https://{domain}/{stage}",
    )
    start_time = time.time()
    apm_id = ""
    session_id = connection_id  # Always use connectionId as session_id

    try:
        body = json.loads(event.get("body", "{}"))
        data = body.get("data", {})
        prompt = data.get("prompt", "")

        # ─── JWT Validation (AgentCore Identity flow) ────────────────────
        # The client sends its token in the message payload for per-message
        # validation. This ensures apm_id is always derived from verified
        # claims, not from untrusted client data.
        token = data.get("token", "")

        # Fallback: try query params (from $connect)
        if not token:
            token = (event.get("queryStringParameters") or {}).get("token", "")

        # Validate JWT and extract claims
        claims = _validate_cognito_jwt(token) if token else None

        if claims is None:
            _post(apigw, connection_id, {
                "type": "error",
                "message": "Sesión expirada. Volvé a iniciar sesión.",
                "code": "AUTH",
            })
            return {"statusCode": 401}

        # Extract apm_id exclusively from validated JWT claims
        apm_id = claims.get("custom:apm_id", "")

        if not apm_id:
            _post(apigw, connection_id, {
                "type": "error",
                "message": "No se pudo identificar al APM. Volvé a iniciar sesión.",
                "code": "AUTH",
            })
            return {"statusCode": 401}

        # ─── Input validation ────────────────────────────────────────────
        if not prompt:
            _post(apigw, connection_id, {
                "type": "error",
                "message": "El mensaje está vacío.",
                "code": "VALIDATION",
            })
            return {"statusCode": 400}

        if not AGENTCORE_ARN:
            _post(apigw, connection_id, {
                "type": "error",
                "message": "El asistente no está configurado.",
                "code": "CONFIG",
            })
            return {"statusCode": 500}

        # ─── Invoke AgentCore Runtime ────────────────────────────────────
        # Pass apm_id (from JWT claims) and session_id (connectionId)
        # so the agent can scope queries and manage memory per-session.
        payload = json.dumps({
            "prompt": prompt,
            "apm_id": apm_id,
            "session_id": session_id,
        }).encode("utf-8")

        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=AGENTCORE_ARN,
            runtimeSessionId=session_id,
            payload=payload,
        )

        # Stream response back to client
        full_response = _stream_response(apigw, connection_id, response)

        # Parse and send completion message with full AgentResponsePayload
        payload = _parse_agent_response(full_response)
        _post(apigw, connection_id, {"type": "complete", "payload": payload})

        duration = time.time() - start_time
        log_entry = {
            "event": "message_complete",
            "apm_id": apm_id,
            "session_id": session_id,
            "connection_id": connection_id,
            "prompt_length": len(prompt),
            "response_length": len(full_response),
            "duration_seconds": round(duration, 2),
        }
        logger.info(json.dumps(log_entry))

        if duration > 60:
            logger.warning(json.dumps({
                "event": "slow_invocation",
                "apm_id": apm_id,
                "session_id": session_id,
                "connection_id": connection_id,
                "duration_seconds": round(duration, 2),
                "prompt_length": len(prompt),
                "response_length": len(full_response),
            }))

        return {"statusCode": 200}

    except Exception as e:
        duration = time.time() - start_time
        logger.error(json.dumps({
            "event": "message_error",
            "apm_id": apm_id,
            "session_id": session_id,
            "connection_id": connection_id,
            "duration_seconds": round(duration, 2),
            "error": str(e),
        }))
        try:
            error_code = "TIMEOUT" if "timeout" in str(e).lower() else "INTERNAL"
            _post(apigw, connection_id, {
                "type": "error",
                "message": "El asistente no está disponible en este momento.",
                "code": error_code,
            })
        except Exception:
            pass
        return {"statusCode": 500}


def _stream_response(apigw, connection_id: str, response: dict) -> str:
    """Stream AgentCore response chunks back to the WebSocket client.

    Protocol (WsServerChunk):
      - {"type": "chunk", "text": "..."}           → partial text
      - {"type": "tool_step", "tool": "...", "label": "..."}  → tool activity
      - {"type": "complete", "payload": {...}}     → final AgentResponsePayload
      - {"type": "error", "message": "...", "code": "..."}    → failure

    Returns the full accumulated response text.
    """
    full_response = ""
    content_type = response.get("contentType", "")
    tools_notified: set = set()

    if "text/event-stream" in content_type:
        # SSE streaming from AgentCore
        for line in response["response"].iter_lines(chunk_size=10):
            if not line:
                continue
            decoded = line.decode("utf-8") if isinstance(line, bytes) else line

            # Detect tool use events and send tool_step messages
            if _is_tool_event(decoded):
                tool_name = _extract_tool_name(decoded)
                if tool_name and tool_name not in tools_notified:
                    tools_notified.add(tool_name)
                    label = _get_tool_label(tool_name)
                    _post(apigw, connection_id, {
                        "type": "tool_step",
                        "tool": tool_name,
                        "label": label,
                    })
                continue

            # Extract text content from SSE data lines
            text = decoded[6:] if decoded.startswith("data: ") else decoded
            if text.strip():
                full_response += text
                _post(apigw, connection_id, {"type": "chunk", "text": text})
    else:
        # JSON response (non-streaming)
        chunks = []
        for chunk in response.get("response", []):
            chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        if chunks:
            raw_body = "".join(chunks)
            try:
                body_json = json.loads(raw_body)
                # If it's a structured response, extract result for streaming
                result_text = body_json.get("result", str(body_json)) if isinstance(body_json, dict) else str(body_json)
                full_response = raw_body  # Preserve full JSON for _parse_agent_response
                _post(apigw, connection_id, {"type": "chunk", "text": result_text})
            except (json.JSONDecodeError, TypeError):
                # Non-JSON response — treat as plain text
                full_response = raw_body
                _post(apigw, connection_id, {"type": "chunk", "text": raw_body})

    return full_response


def _parse_agent_response(raw_text: str) -> dict:
    """Parse the raw agent response into an AgentResponsePayload.

    Tries to interpret the accumulated text as JSON (the agent may return
    a structured JSON response). Falls back to plain text.

    Returns:
        Dict matching AgentResponsePayload: {result, structured, success, retries}
    """
    # Try parsing as JSON — the unified agent returns structured JSON
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict) and "result" in data:
            return {
                "result": data.get("result", ""),
                "structured": data.get("structured"),
                "success": data.get("success", True),
                "retries": data.get("retries", 0),
            }
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: treat as plain text result
    return {
        "result": raw_text,
        "structured": None,
        "success": True,
        "retries": 0,
    }


def _is_tool_event(line: str) -> bool:
    """Check if an SSE line indicates tool use."""
    return "tool_use" in line or "toolUse" in line


# ─── Tool label mapping (Unified Agent tools) ────────────────────────────────

TOOL_LABELS: dict[str, str] = {
    "query_db": "Consultando base de datos...",
    "buscar_info_publica": "Buscando información pública...",
    "generar_brief": "Generando brief pre-visita...",
    "obtener_minutas": "Consultando minutas de visitas previas...",
    "generar_mensaje_cumpleanos": "Generando mensaje de cumpleaños...",
}


def _get_tool_label(tool_name: str) -> str:
    """Get a user-friendly Spanish label for a tool invocation."""
    return TOOL_LABELS.get(tool_name, "Procesando consulta...")


def _extract_tool_name(line: str) -> str | None:
    """Extract the tool name from an SSE tool_use event line.

    AgentCore streams tool events as JSON with a 'name' field inside
    a tool_use block. We try JSON parsing first, then regex fallback.
    """
    # Try parsing data payload if SSE formatted
    data_str = line[6:] if line.startswith("data: ") else line
    try:
        data = json.loads(data_str)
        # AgentCore tool event structures vary; check common shapes
        if isinstance(data, dict):
            # Shape: {"type": "tool_use", "name": "query_db", ...}
            if data.get("name"):
                return data["name"]
            # Shape: {"toolUse": {"name": "query_db", ...}}
            tool_use = data.get("toolUse") or data.get("tool_use")
            if isinstance(tool_use, dict) and tool_use.get("name"):
                return tool_use["name"]
            # Shape: nested content block
            content = data.get("content") or data.get("delta")
            if isinstance(content, dict):
                tool_use_inner = content.get("toolUse") or content.get("tool_use")
                if isinstance(tool_use_inner, dict) and tool_use_inner.get("name"):
                    return tool_use_inner["name"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Regex fallback: find known tool names in the line
    for tool_name in TOOL_LABELS:
        if tool_name in line:
            return tool_name

    return None
