"""
Integration tests for error scenarios end-to-end.

Tests validate error handling at:
1. Lambda proxy level — JWT invalid → 401 + AUTH redirect (covered by test_ws_handler.py)
2. Agent level — complex query timeout → user-friendly error
3. Agent level — unknown table → retry + graceful error

Key assertions:
- Error responses NEVER contain sensitive infrastructure info (hostnames, IPs, ARNs)
- Agent always returns structured {result, success, retries} even on failure
- User-facing messages are in Spanish and helpful

Requirements: 8.5, 20.1, 20.3, 20.4
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

# ---------------------------------------------------------------------------
# Markers and skip logic
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration

# Sensitive patterns that must NEVER appear in user-facing responses
SENSITIVE_PATTERNS = [
    "rds.amazonaws.com",
    "10.0.",
    "172.16.",
    "192.168.",
    "postgresql://",
    "postgres://",
    "arn:aws:",
    "SQLSTATE",
    "psycopg2",
    "sqlalchemy",
    "Traceback (most recent call last)",
    'File "/',
]


def _agentcore_available() -> bool:
    """Check if agentcore CLI is installed and agent is deployed."""
    if not shutil.which("agentcore"):
        return False
    try:
        result = subprocess.run(
            ["agentcore", "status"],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            timeout=30,
        )
        # If status returns 0 and mentions an active/running runtime, agent is deployed
        return result.returncode == 0 and "ACTIVE" in result.stdout.upper()
    except (subprocess.TimeoutExpired, OSError):
        return False


skip_no_agent = pytest.mark.skipif(
    not _agentcore_available(),
    reason="AgentCore agent not deployed (agentcore status not ACTIVE)",
)


def _assert_no_sensitive_data(response_text: str) -> None:
    """Assert that response text contains no sensitive infrastructure details."""
    lower_text = response_text.lower()
    for pattern in SENSITIVE_PATTERNS:
        assert pattern.lower() not in lower_text, (
            f"Response contains sensitive data matching '{pattern}': "
            f"{response_text[:200]}..."
        )


def _invoke_agent(prompt: str, apm_id: str = "Peccy") -> dict:
    """Invoke the deployed agent via agentcore CLI and return parsed response.

    Args:
        prompt: The user prompt to send.
        apm_id: APM identifier for data isolation.

    Returns:
        Parsed JSON response dict from the agent.

    Raises:
        subprocess.TimeoutExpired: If agent takes more than 120s.
        json.JSONDecodeError: If response is not valid JSON.
    """
    payload = json.dumps({"prompt": prompt, "apm_id": apm_id})
    result = subprocess.run(
        ["agentcore", "invoke", payload],
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        timeout=120,
    )

    if result.returncode != 0:
        pytest.fail(
            f"agentcore invoke failed (rc={result.returncode}):\n"
            f"stdout: {result.stdout[:500]}\n"
            f"stderr: {result.stderr[:500]}"
        )

    # Parse the JSON response from stdout
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # Some agentcore versions wrap the response — try to extract JSON
        lines = result.stdout.strip().splitlines()
        for line in reversed(lines):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        pytest.fail(f"Could not parse agent response as JSON:\n{result.stdout[:500]}")


# ---------------------------------------------------------------------------
# Test 1: Invalid JWT → 401 + AUTH error (Lambda proxy level)
# ---------------------------------------------------------------------------


class TestJWTErrorsStillPass:
    """Verify that existing JWT validation tests in ws_handler still pass.

    This is a meta-test that runs the ws_handler test suite to confirm
    JWT error handling is intact. Requirement 8.5.
    """

    def test_ws_handler_jwt_tests_pass(self):
        """Run the ws_handler JWT tests and verify they pass."""
        ws_test_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "backend", "ws_proxy", "test_ws_handler.py"
        )
        if not os.path.exists(ws_test_path):
            pytest.skip("backend/ws_proxy/test_ws_handler.py not found")

        result = subprocess.run(
            [sys.executable, "-m", "pytest", ws_test_path, "-v",
             "-k", "TestJWTValidation or test_expired_token_returns_401 or test_no_token_returns_401"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            pytest.fail(
                f"JWT validation tests failed:\n"
                f"stdout: {result.stdout[-1000:]}\n"
                f"stderr: {result.stderr[-500:]}"
            )


# ---------------------------------------------------------------------------
# Test 2: Complex query timeout → user-friendly error
# ---------------------------------------------------------------------------


@skip_no_agent
class TestTimeoutProducesUserFriendlyError:
    """Agent handles complex query timeout gracefully.

    Validates:
    - Requirements 20.3 (Bedrock throttled / timeout → friendly message)
    - Requirements 20.4 (no unhandled exceptions)
    - Property 4 (no sensitive data leakage)
    """

    def test_timeout_produces_user_friendly_error(self):
        """A deliberately complex query should return a structured error,
        never exposing hostnames, IPs, or internal error messages."""
        response = _invoke_agent(
            "Dame un cross join de todas las tablas sin filtros"
        )

        # Response must always be structured
        assert "result" in response, "Response missing 'result' key"
        assert "success" in response, "Response missing 'success' key"

        # Whether it succeeds or fails, must not contain sensitive data
        _assert_no_sensitive_data(response["result"])

        # If it failed (expected for a massive cross join), verify error structure
        if not response.get("success", True):
            assert isinstance(response["result"], str)
            assert len(response["result"]) > 0
            # Retries should be within bounds
            assert response.get("retries", 0) in {0, 1, 2}

    def test_timeout_response_never_exposes_hostnames(self):
        """Even if the query times out, no RDS hostnames in response."""
        response = _invoke_agent(
            "Hacé un SELECT * de cartera_medica CROSS JOIN prescripciones "
            "CROSS JOIN visitas sin WHERE ni LIMIT"
        )

        assert "result" in response
        result_text = response["result"]
        assert "rds.amazonaws.com" not in result_text
        assert "10.0." not in result_text
        assert "172.16." not in result_text

    def test_timeout_response_is_in_spanish(self):
        """Error messages should be user-friendly and in Spanish."""
        response = _invoke_agent(
            "Generá un producto cartesiano de todas las tablas de la base"
        )

        if not response.get("success", True):
            result_text = response["result"]
            # Should not contain English technical error messages
            assert "connection" not in result_text.lower()
            assert "exception" not in result_text.lower()
            assert "stack trace" not in result_text.lower()


# ---------------------------------------------------------------------------
# Test 3: Unknown table → retry with self-correction
# ---------------------------------------------------------------------------


@skip_no_agent
class TestUnknownTableHandledGracefully:
    """Agent retries when SQL references non-existent table.

    Validates:
    - Requirement 3.1 (retry with corrected SQL including error in context)
    - Requirement 3.3 (user-friendly error in Spanish if all retries fail)
    - Requirement 20.4 (no unhandled exceptions)
    - Property 4 (no sensitive data leakage)
    """

    def test_agent_handles_unknown_table_gracefully(self):
        """Agent retries when SQL references non-existent table."""
        response = _invoke_agent(
            "Hacé un SELECT de la tabla 'medicos_fantasma'"
        )

        assert "result" in response
        assert "success" in response

        result_text = response["result"]

        # Should not expose raw SQL error with internal table details
        assert "does not exist" not in result_text.lower()
        assert "relation" not in result_text.lower() or "relación" in result_text.lower()

        # No sensitive infrastructure info
        _assert_no_sensitive_data(result_text)

        # Response should acknowledge the issue helpfully
        assert isinstance(result_text, str)
        assert len(result_text) > 0

    def test_unknown_table_retries_within_bounds(self):
        """Retry count should be 0, 1, or 2 (max 2 retries)."""
        response = _invoke_agent(
            "Consultá la tabla 'tabla_que_no_existe' y dame los primeros 5 registros"
        )

        assert "retries" in response
        assert response["retries"] in {0, 1, 2}

    def test_unknown_table_no_raw_sql_errors_exposed(self):
        """Raw PostgreSQL errors like 'relation does not exist' must not reach user."""
        response = _invoke_agent(
            "SELECT * FROM schema_inexistente.tabla_inventada LIMIT 10"
        )

        assert "result" in response
        result_text = response["result"]

        # PostgreSQL-specific error messages that must never reach the user
        pg_error_patterns = [
            "does not exist",
            "psycopg2.errors",
            "UndefinedTable",
            "ProgrammingError",
            "relation \"",
            "schema \"",
        ]
        for pattern in pg_error_patterns:
            assert pattern not in result_text, (
                f"Raw PostgreSQL error leaked to user: '{pattern}' found in response"
            )


# ---------------------------------------------------------------------------
# Test 4: Generic error response validation
# ---------------------------------------------------------------------------


@skip_no_agent
class TestErrorResponseStructure:
    """All error responses maintain the expected contract.

    Validates: Property 5 (graceful degradation)
    """

    def test_empty_prompt_returns_structured_error(self):
        """Empty prompt should still return a structured response."""
        response = _invoke_agent("")

        # Agent should handle gracefully
        assert "result" in response
        assert isinstance(response["result"], str)

    def test_very_long_prompt_does_not_crash(self):
        """Extremely long prompt is handled without crash."""
        long_prompt = "Dame información sobre " + "muchos datos " * 500
        response = _invoke_agent(long_prompt)

        assert "result" in response
        _assert_no_sensitive_data(response["result"])

    def test_response_always_has_success_field(self):
        """Every response must include the 'success' boolean field."""
        response = _invoke_agent(
            "¿Cuántos médicos tengo con cadencia inexistente tipo 'Lunar'?"
        )

        assert "success" in response
        assert isinstance(response["success"], bool)
