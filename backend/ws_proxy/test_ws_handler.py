"""Unit tests for ws_handler — JWT validation and identity flow (task 6.1)."""

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

# Mock boto3 before importing the handler
import sys
sys.modules.setdefault("boto3", MagicMock())


def _make_jwt(claims: dict, header: dict | None = None) -> str:
    """Create a fake JWT token with given claims (no signature verification)."""
    if header is None:
        header = {"alg": "RS256", "kid": "test-kid-1"}

    def _b64url(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{_b64url(header)}.{_b64url(claims)}.fake-signature"


def _valid_claims(apm_id: str = "Valentina Pérez", exp_offset: int = 3600) -> dict:
    """Return valid JWT claims for testing."""
    return {
        "sub": "user-123",
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TestPool",
        "token_use": "id",
        "exp": int(time.time()) + exp_offset,
        "custom:apm_id": apm_id,
    }


def _expired_claims(apm_id: str = "Valentina Pérez") -> dict:
    """Return expired JWT claims."""
    return _valid_claims(apm_id, exp_offset=-3600)


def _ws_event(route: str, connection_id: str = "conn-abc123",
              body: dict | None = None, query_params: dict | None = None) -> dict:
    """Build a WebSocket API Gateway event."""
    event = {
        "requestContext": {
            "routeKey": route,
            "connectionId": connection_id,
            "domainName": "ws.example.com",
            "stage": "prod",
        },
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if query_params is not None:
        event["queryStringParameters"] = query_params
    return event


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    """Set required env vars for the handler."""
    monkeypatch.setenv("AGENTCORE_AGENT_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test")
    monkeypatch.setenv("AGENTCORE_REGION", "us-east-1")
    monkeypatch.setenv("USER_POOL_ID", "us-east-1_TestPool")
    monkeypatch.setenv("USER_POOL_REGION", "us-east-1")


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch):
    """Mock JWKS fetch to return our test kid."""
    fake_jwks = {"keys": [{"kid": "test-kid-1", "kty": "RSA"}]}
    monkeypatch.setattr("backend.ws_proxy.ws_handler._jwks_cache", fake_jwks)


@pytest.fixture
def mock_apigw():
    """Mock API Gateway Management client."""
    with patch("backend.ws_proxy.ws_handler.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_agentcore():
    """Mock AgentCore client for invoke."""
    with patch("backend.ws_proxy.ws_handler.agentcore_client") as mock_client:
        mock_client.invoke_agent_runtime.return_value = {
            "contentType": "application/json",
            "response": [json.dumps({"result": "Hola, soy el asistente."}).encode()],
        }
        yield mock_client


class TestJWTValidation:
    """Tests for _validate_cognito_jwt."""

    def test_valid_token_returns_claims(self):
        from backend.ws_proxy.ws_handler import _validate_cognito_jwt
        token = _make_jwt(_valid_claims())
        claims = _validate_cognito_jwt(token)
        assert claims is not None
        assert claims["custom:apm_id"] == "Valentina Pérez"

    def test_expired_token_returns_none(self):
        from backend.ws_proxy.ws_handler import _validate_cognito_jwt
        token = _make_jwt(_expired_claims())
        claims = _validate_cognito_jwt(token)
        assert claims is None

    def test_empty_token_returns_none(self):
        from backend.ws_proxy.ws_handler import _validate_cognito_jwt
        assert _validate_cognito_jwt("") is None

    def test_malformed_token_returns_none(self):
        from backend.ws_proxy.ws_handler import _validate_cognito_jwt
        assert _validate_cognito_jwt("not.a.valid.jwt") is None
        assert _validate_cognito_jwt("garbage") is None

    def test_wrong_issuer_returns_none(self):
        from backend.ws_proxy.ws_handler import _validate_cognito_jwt
        claims = _valid_claims()
        claims["iss"] = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_Wrong"
        token = _make_jwt(claims)
        assert _validate_cognito_jwt(token) is None

    def test_wrong_kid_returns_none(self):
        from backend.ws_proxy.ws_handler import _validate_cognito_jwt
        token = _make_jwt(_valid_claims(), header={"alg": "RS256", "kid": "unknown-kid"})
        assert _validate_cognito_jwt(token) is None


class TestHandleMessageIdentity:
    """Tests for _handle_message — JWT validation and apm_id extraction."""

    def test_valid_token_extracts_apm_id_and_passes_to_agent(self, mock_apigw, mock_agentcore):
        """Valid JWT → apm_id extracted from claims, passed to AgentCore."""
        from backend.ws_proxy.ws_handler import handler

        token = _make_jwt(_valid_claims("Demo APM"))
        event = _ws_event(
            "sendMessage",
            body={"data": {"prompt": "Hola", "token": token}},
        )

        result = handler(event, None)

        assert result["statusCode"] == 200
        # Verify AgentCore was invoked with apm_id from JWT claims
        call_args = mock_agentcore.invoke_agent_runtime.call_args
        payload = json.loads(call_args.kwargs["payload"])
        assert payload["apm_id"] == "Demo APM"
        assert payload["session_id"] == "conn-abc123"  # connectionId
        assert payload["prompt"] == "Hola"

    def test_expired_token_returns_401_with_auth_error(self, mock_apigw, mock_agentcore):
        """Expired JWT → 401 + AUTH error via WebSocket."""
        from backend.ws_proxy.ws_handler import handler

        token = _make_jwt(_expired_claims())
        event = _ws_event(
            "sendMessage",
            body={"data": {"prompt": "Hola", "token": token}},
        )

        result = handler(event, None)

        assert result["statusCode"] == 401
        # Verify error message sent via WS
        post_call = mock_apigw.post_to_connection.call_args
        msg = json.loads(post_call.kwargs["Data"])
        assert msg["type"] == "error"
        assert msg["code"] == "AUTH"
        assert "Sesión expirada" in msg["message"]
        # Agent should NOT be invoked
        mock_agentcore.invoke_agent_runtime.assert_not_called()

    def test_no_token_returns_401(self, mock_apigw, mock_agentcore):
        """No token in payload or query params → 401."""
        from backend.ws_proxy.ws_handler import handler

        event = _ws_event(
            "sendMessage",
            body={"data": {"prompt": "Hola"}},
        )

        result = handler(event, None)

        assert result["statusCode"] == 401
        mock_agentcore.invoke_agent_runtime.assert_not_called()

    def test_token_without_apm_id_claim_returns_401(self, mock_apigw, mock_agentcore):
        """Valid token but missing custom:apm_id → 401."""
        from backend.ws_proxy.ws_handler import handler

        claims = _valid_claims()
        del claims["custom:apm_id"]
        token = _make_jwt(claims)
        event = _ws_event(
            "sendMessage",
            body={"data": {"prompt": "Hola", "token": token}},
        )

        result = handler(event, None)

        assert result["statusCode"] == 401
        post_call = mock_apigw.post_to_connection.call_args
        msg = json.loads(post_call.kwargs["Data"])
        assert msg["code"] == "AUTH"
        mock_agentcore.invoke_agent_runtime.assert_not_called()

    def test_client_sent_apm_id_is_ignored(self, mock_apigw, mock_agentcore):
        """Client-sent apm_id in data payload is IGNORED — JWT claims are source of truth."""
        from backend.ws_proxy.ws_handler import handler

        token = _make_jwt(_valid_claims("Real APM"))
        event = _ws_event(
            "sendMessage",
            body={"data": {
                "prompt": "Hola",
                "token": token,
                "apm_id": "Spoofed APM",  # This should be ignored
            }},
        )

        result = handler(event, None)

        assert result["statusCode"] == 200
        call_args = mock_agentcore.invoke_agent_runtime.call_args
        payload = json.loads(call_args.kwargs["payload"])
        # Must use JWT claim, NOT client-sent value
        assert payload["apm_id"] == "Real APM"

    def test_session_id_is_connection_id(self, mock_apigw, mock_agentcore):
        """session_id in agent payload is always the WebSocket connectionId."""
        from backend.ws_proxy.ws_handler import handler

        token = _make_jwt(_valid_claims())
        event = _ws_event(
            "sendMessage",
            connection_id="ws-connection-xyz",
            body={"data": {"prompt": "Hola", "token": token}},
        )

        result = handler(event, None)

        assert result["statusCode"] == 200
        call_args = mock_agentcore.invoke_agent_runtime.call_args
        payload = json.loads(call_args.kwargs["payload"])
        assert payload["session_id"] == "ws-connection-xyz"

    def test_fallback_to_query_param_token(self, mock_apigw, mock_agentcore):
        """If no token in data payload, try query params (from $connect)."""
        from backend.ws_proxy.ws_handler import handler

        token = _make_jwt(_valid_claims("Fallback APM"))
        event = _ws_event(
            "sendMessage",
            body={"data": {"prompt": "Hola"}},
            query_params={"token": token},
        )

        result = handler(event, None)

        assert result["statusCode"] == 200
        call_args = mock_agentcore.invoke_agent_runtime.call_args
        payload = json.loads(call_args.kwargs["payload"])
        assert payload["apm_id"] == "Fallback APM"


class TestHandleConnect:
    """Tests for $connect route — JWT validation at connection time."""

    def test_valid_token_connects(self):
        from backend.ws_proxy.ws_handler import handler

        token = _make_jwt(_valid_claims())
        event = _ws_event("$connect", query_params={"token": token})

        result = handler(event, None)
        assert result["statusCode"] == 200

    def test_expired_token_rejects_connect(self):
        from backend.ws_proxy.ws_handler import handler

        token = _make_jwt(_expired_claims())
        event = _ws_event("$connect", query_params={"token": token})

        result = handler(event, None)
        assert result["statusCode"] == 401

    def test_no_token_rejects_connect(self):
        from backend.ws_proxy.ws_handler import handler

        event = _ws_event("$connect", query_params={})
        result = handler(event, None)
        assert result["statusCode"] == 401


class TestStreamingProtocol:
    """Tests for structured response streaming protocol (task 9.1).

    Validates that the Lambda proxy sends:
    - type: "chunk" with "text" field (not "content")
    - type: "tool_step" with "tool" and "label" fields
    - type: "complete" with full AgentResponsePayload
    - type: "error" with "message" and "code"
    """

    def test_chunk_uses_text_field(self, mock_apigw, mock_agentcore):
        """Streaming chunks use {"type": "chunk", "text": "..."} format."""
        from backend.ws_proxy.ws_handler import handler

        mock_agentcore.invoke_agent_runtime.return_value = {
            "contentType": "application/json",
            "response": [json.dumps({"result": "Los resultados muestran..."}).encode()],
        }

        token = _make_jwt(_valid_claims())
        event = _ws_event("sendMessage", body={"data": {"prompt": "Hola", "token": token}})
        handler(event, None)

        # Find chunk messages sent via post_to_connection
        calls = mock_apigw.post_to_connection.call_args_list
        chunk_msgs = [
            json.loads(c.kwargs["Data"])
            for c in calls
            if json.loads(c.kwargs["Data"]).get("type") == "chunk"
        ]
        assert len(chunk_msgs) > 0
        for msg in chunk_msgs:
            assert "text" in msg, "Chunk must use 'text' field"
            assert "content" not in msg, "Chunk must NOT use old 'content' field"

    def test_complete_includes_payload(self, mock_apigw, mock_agentcore):
        """Complete message includes full AgentResponsePayload."""
        from backend.ws_proxy.ws_handler import handler

        agent_response = {
            "result": "Los resultados muestran tendencia positiva.",
            "structured": {"sql": "SELECT * FROM ventas", "suggestions": ["Ver por zona"]},
            "success": True,
            "retries": 0,
        }
        mock_agentcore.invoke_agent_runtime.return_value = {
            "contentType": "application/json",
            "response": [json.dumps(agent_response).encode()],
        }

        token = _make_jwt(_valid_claims())
        event = _ws_event("sendMessage", body={"data": {"prompt": "Ventas", "token": token}})
        handler(event, None)

        calls = mock_apigw.post_to_connection.call_args_list
        complete_msgs = [
            json.loads(c.kwargs["Data"])
            for c in calls
            if json.loads(c.kwargs["Data"]).get("type") == "complete"
        ]
        assert len(complete_msgs) == 1
        payload = complete_msgs[0]["payload"]
        assert payload["result"] == "Los resultados muestran tendencia positiva."
        assert payload["success"] is True
        assert payload["retries"] == 0
        assert payload["structured"]["sql"] == "SELECT * FROM ventas"
        assert payload["structured"]["suggestions"] == ["Ver por zona"]

    def test_complete_fallback_for_plain_text(self, mock_apigw, mock_agentcore):
        """Non-JSON agent response → complete with plain text result."""
        from backend.ws_proxy.ws_handler import handler

        mock_agentcore.invoke_agent_runtime.return_value = {
            "contentType": "application/json",
            "response": [b"Just plain text without JSON structure"],
        }

        token = _make_jwt(_valid_claims())
        event = _ws_event("sendMessage", body={"data": {"prompt": "Hola", "token": token}})
        handler(event, None)

        calls = mock_apigw.post_to_connection.call_args_list
        complete_msgs = [
            json.loads(c.kwargs["Data"])
            for c in calls
            if json.loads(c.kwargs["Data"]).get("type") == "complete"
        ]
        assert len(complete_msgs) == 1
        payload = complete_msgs[0]["payload"]
        assert payload["result"] == "Just plain text without JSON structure"
        assert payload["success"] is True
        assert payload["retries"] == 0
        assert payload["structured"] is None

    def test_error_messages_include_code(self, mock_apigw, mock_agentcore):
        """Error messages always include a 'code' field."""
        from backend.ws_proxy.ws_handler import handler

        token = _make_jwt(_valid_claims())
        # Empty prompt → VALIDATION error
        event = _ws_event("sendMessage", body={"data": {"prompt": "", "token": token}})
        handler(event, None)

        calls = mock_apigw.post_to_connection.call_args_list
        error_msgs = [
            json.loads(c.kwargs["Data"])
            for c in calls
            if json.loads(c.kwargs["Data"]).get("type") == "error"
        ]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == "VALIDATION"
        assert "vacío" in error_msgs[0]["message"]

    def test_exception_error_includes_code(self, mock_apigw, mock_agentcore):
        """Exceptions send error with TIMEOUT or INTERNAL code."""
        from backend.ws_proxy.ws_handler import handler

        mock_agentcore.invoke_agent_runtime.side_effect = Exception("Connection timeout")
        token = _make_jwt(_valid_claims())
        event = _ws_event("sendMessage", body={"data": {"prompt": "Test", "token": token}})
        handler(event, None)

        calls = mock_apigw.post_to_connection.call_args_list
        error_msgs = [
            json.loads(c.kwargs["Data"])
            for c in calls
            if json.loads(c.kwargs["Data"]).get("type") == "error"
        ]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == "TIMEOUT"

    def test_exception_internal_code(self, mock_apigw, mock_agentcore):
        """Non-timeout exceptions get INTERNAL code."""
        from backend.ws_proxy.ws_handler import handler

        mock_agentcore.invoke_agent_runtime.side_effect = RuntimeError("Something broke")
        token = _make_jwt(_valid_claims())
        event = _ws_event("sendMessage", body={"data": {"prompt": "Test", "token": token}})
        handler(event, None)

        calls = mock_apigw.post_to_connection.call_args_list
        error_msgs = [
            json.loads(c.kwargs["Data"])
            for c in calls
            if json.loads(c.kwargs["Data"]).get("type") == "error"
        ]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == "INTERNAL"


class TestToolStepMessages:
    """Tests for tool_step message generation."""

    def test_tool_labels_mapping(self):
        """Verify all expected tools have Spanish labels."""
        from backend.ws_proxy.ws_handler import TOOL_LABELS, _get_tool_label

        assert _get_tool_label("query_db") == "Consultando base de datos..."
        assert _get_tool_label("buscar_info_publica") == "Buscando información pública..."
        assert _get_tool_label("generar_brief") == "Generando brief pre-visita..."
        assert _get_tool_label("obtener_minutas") == "Consultando minutas de visitas previas..."
        assert _get_tool_label("generar_mensaje_cumpleanos") == "Generando mensaje de cumpleaños..."
        # Unknown tool gets fallback
        assert _get_tool_label("unknown_tool") == "Procesando consulta..."

    def test_extract_tool_name_from_json(self):
        """Extracts tool name from JSON tool_use event."""
        from backend.ws_proxy.ws_handler import _extract_tool_name

        # Shape: {"type": "tool_use", "name": "query_db"}
        line = 'data: {"type": "tool_use", "name": "query_db", "input": {}}'
        assert _extract_tool_name(line) == "query_db"

        # Shape: {"toolUse": {"name": "obtener_minutas"}}
        line = 'data: {"toolUse": {"name": "obtener_minutas", "toolUseId": "123"}}'
        assert _extract_tool_name(line) == "obtener_minutas"

    def test_extract_tool_name_fallback(self):
        """Falls back to string matching for non-JSON lines."""
        from backend.ws_proxy.ws_handler import _extract_tool_name

        line = "event: tool_use query_db starting"
        assert _extract_tool_name(line) == "query_db"

        line = "event: tool_use generar_brief starting"
        assert _extract_tool_name(line) == "generar_brief"

    def test_extract_tool_name_unknown(self):
        """Returns None for lines without recognized tool names."""
        from backend.ws_proxy.ws_handler import _extract_tool_name

        line = "data: some random text"
        assert _extract_tool_name(line) is None

    def test_is_tool_event(self):
        """Detects tool events in SSE lines."""
        from backend.ws_proxy.ws_handler import _is_tool_event

        assert _is_tool_event('data: {"type": "tool_use", "name": "query_db"}') is True
        assert _is_tool_event('data: {"toolUse": {"name": "x"}}') is True
        assert _is_tool_event('data: {"type": "text", "content": "hello"}') is False


class TestParseAgentResponse:
    """Tests for _parse_agent_response."""

    def test_valid_json_response(self):
        """Parses valid AgentResponsePayload JSON."""
        from backend.ws_proxy.ws_handler import _parse_agent_response

        raw = json.dumps({
            "result": "Tenés 42 médicos.",
            "structured": {"table": {"columns": ["nombre"], "rows": []}},
            "success": True,
            "retries": 1,
        })
        parsed = _parse_agent_response(raw)
        assert parsed["result"] == "Tenés 42 médicos."
        assert parsed["success"] is True
        assert parsed["retries"] == 1
        assert parsed["structured"]["table"]["columns"] == ["nombre"]

    def test_plain_text_fallback(self):
        """Non-JSON text → plain text result with defaults."""
        from backend.ws_proxy.ws_handler import _parse_agent_response

        parsed = _parse_agent_response("Hola, soy el asistente.")
        assert parsed["result"] == "Hola, soy el asistente."
        assert parsed["success"] is True
        assert parsed["retries"] == 0
        assert parsed["structured"] is None

    def test_json_without_result_key(self):
        """JSON without 'result' key → fallback to plain text."""
        from backend.ws_proxy.ws_handler import _parse_agent_response

        raw = json.dumps({"answer": "something", "status": "ok"})
        parsed = _parse_agent_response(raw)
        # Falls back to treating full JSON string as text
        assert parsed["result"] == raw
        assert parsed["success"] is True
