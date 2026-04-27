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
    """Handle sendMessage route — forward to AgentCore and stream back."""
    apigw = boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=f"https://{domain}/{stage}",
    )
    start_time = time.time()
    apm_id = ""
    session_id = ""

    try:
        body = json.loads(event.get("body", "{}"))
        data = body.get("data", {})
        prompt = data.get("prompt", "")
        session_id = data.get("session_id", connection_id)

        # Extract apm_id — WebSocket API GW does NOT inject JWT claims
        # into sendMessage events, so we read it from the client payload.
        apm_id = data.get("apm_id", "")

        # Fallback: try authorizer context (in case future WS authorizer support)
        if not apm_id:
            claims = event.get("requestContext", {}).get("authorizer", {})
            apm_id = claims.get("custom:apm_id", "")

        # Fallback: re-validate token from query params
        if not apm_id:
            token = (event.get("queryStringParameters") or {}).get("token", "")
            if token:
                jwt_claims = _validate_cognito_jwt(token)
                if jwt_claims:
                    apm_id = jwt_claims.get("custom:apm_id", "")

        if not prompt:
            _post(apigw, connection_id, {"type": "error", "message": "El mensaje está vacío."})
            return {"statusCode": 400}

        if not apm_id:
            _post(apigw, connection_id, {
                "type": "error",
                "message": "No se pudo identificar al APM. Recargá la página e intentá de nuevo.",
            })
            return {"statusCode": 400}

        if not AGENTCORE_ARN:
            _post(apigw, connection_id, {
                "type": "error",
                "message": "El asistente no está configurado.",
            })
            return {"statusCode": 500}

        # Invoke AgentCore Runtime
        payload = json.dumps({
            "prompt": prompt,
            "apm_id": apm_id,
        }).encode("utf-8")

        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=AGENTCORE_ARN,
            runtimeSessionId=session_id,
            payload=payload,
        )

        # Stream response back to client
        full_response = _stream_response(apigw, connection_id, response)

        # Send completion message
        _post(apigw, connection_id, {"type": "complete", "session_id": session_id})

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
            _post(apigw, connection_id, {
                "type": "error",
                "message": "El asistente no está disponible en este momento.",
            })
        except Exception:
            pass
        return {"statusCode": 500}


def _stream_response(apigw, connection_id: str, response: dict) -> str:
    """Stream AgentCore response chunks back to the WebSocket client.

    Returns the full accumulated response text.
    """
    full_response = ""
    content_type = response.get("contentType", "")
    tools_sent = False

    if "text/event-stream" in content_type:
        # SSE streaming from AgentCore
        for line in response["response"].iter_lines(chunk_size=10):
            if not line:
                continue
            decoded = line.decode("utf-8") if isinstance(line, bytes) else line

            # Detect tool use events and send tools message
            if not tools_sent and _is_tool_event(decoded):
                tool_steps = _extract_tool_steps(decoded)
                if tool_steps:
                    _post(apigw, connection_id, {"type": "tools", "steps": tool_steps})
                    tools_sent = True
                continue

            # Extract text content from SSE data lines
            text = decoded[6:] if decoded.startswith("data: ") else decoded
            if text.strip():
                full_response += text
                _post(apigw, connection_id, {"type": "chunk", "content": text})
    else:
        # JSON response (non-streaming)
        chunks = []
        for chunk in response.get("response", []):
            chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        if chunks:
            body_json = json.loads("".join(chunks))
            full_response = body_json.get("result", str(body_json))
            _post(apigw, connection_id, {"type": "chunk", "content": full_response})

    return full_response


def _is_tool_event(line: str) -> bool:
    """Check if an SSE line indicates tool use."""
    return "tool_use" in line or "toolUse" in line


def _extract_tool_steps(line: str) -> list[str]:
    """Extract human-readable tool step descriptions from a tool event."""
    # Map known tool names to Spanish descriptions
    tool_descriptions = {
        "buscar_medicos_por_apm": "Buscando médicos en el CRM",
        "obtener_visitas_planificadas_hoy": "Consultando agenda de hoy",
        "obtener_historial_visitas": "Revisando historial de visitas",
        "buscar_medico_por_nombre": "Buscando médico por nombre",
        "obtener_perfil_medico": "Consultando perfil del médico",
        "obtener_ventas_por_zona": "Analizando ventas por zona",
        "obtener_ventas_por_producto": "Analizando ventas por producto",
        "generar_brief_medico": "Generando brief del médico",
        "obtener_alertas_sla": "Verificando alertas de SLA",
        "obtener_cumpleanos_proximos": "Consultando cumpleaños próximos",
        "generar_mensaje_cumpleanos": "Generando mensaje de cumpleaños",
        "web_search": "Buscando información en la web",
        "sugerir_proxima_visita": "Calculando sugerencia de próxima visita",
        "obtener_minutas_medico": "Consultando notas de visitas previas",
    }
    steps = []
    for tool_name, description in tool_descriptions.items():
        if tool_name in line:
            steps.append(description)
    return steps if steps else ["Procesando consulta"]
