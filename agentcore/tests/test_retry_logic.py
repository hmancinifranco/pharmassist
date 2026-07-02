"""
Unit tests for retry logic in agent.py — _invoke_with_retries.

Tests the differentiated error handling:
- ValueError (non-retryable) → immediate failure
- TimeoutError (retryable) → retry with simplification hint
- RuntimeError (retryable) → retry with SQL error context
- Generic Exception (retryable) → retry with generic context
- Successful response → returns with retry count

Validates: Requirements 3.1, 3.2, 3.3, 3.4
"""

from unittest.mock import MagicMock, patch

import pytest

from agentcore.agent import (
    MAX_RETRIES,
    _error_response,
    _invoke_with_retries,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing retry logic."""
    with patch("agentcore.agent._get_or_create_agent") as mock_get:
        agent = MagicMock()
        mock_get.return_value = agent
        yield agent


# ---------------------------------------------------------------------------
# Success Cases
# ---------------------------------------------------------------------------


class TestRetrySuccess:
    """Test successful invocations."""

    def test_first_attempt_success_text_mode(self, mock_agent):
        mock_agent.return_value = "Resultado exitoso"

        result = _invoke_with_retries(
            prompt="¿Cuántos médicos tengo?",
            apm_id="APM_001",
            session_id="sess-1",
            mode="text",
        )

        assert result["success"] is True
        assert result["result"] == "Resultado exitoso"
        assert result["retries"] == 0
        assert "structured" in result

    def test_first_attempt_success_voice_mode(self, mock_agent):
        mock_agent.return_value = "Tenés 42 médicos"

        result = _invoke_with_retries(
            prompt="¿Cuántos médicos tengo?",
            apm_id="APM_001",
            session_id="sess-1",
            mode="voice",
        )

        assert result["success"] is True
        assert result["result"] == "Tenés 42 médicos"
        assert result["retries"] == 0
        assert "structured" not in result


# ---------------------------------------------------------------------------
# Non-Retryable Errors (ValueError)
# ---------------------------------------------------------------------------


class TestNonRetryableErrors:
    """Test that ValueError (validation rejection) fails immediately."""

    def test_value_error_no_retry(self, mock_agent):
        mock_agent.side_effect = ValueError(
            "Operación 'INSERT' no permitida. Solo se permiten queries SELECT o WITH."
        )

        result = _invoke_with_retries(
            prompt="Insertá un médico nuevo",
            apm_id="APM_001",
            session_id="sess-1",
            mode="text",
        )

        assert result["success"] is False
        assert result["retries"] == 0
        assert "Solo tengo acceso de lectura" in result["result"]
        # Agent should only be called ONCE (no retry)
        assert mock_agent.call_count == 1

    def test_value_error_on_second_attempt_returns_immediately(self, mock_agent):
        """If a retryable error is followed by a ValueError, stop immediately."""
        mock_agent.side_effect = [
            RuntimeError("column 'foo' does not exist"),
            ValueError("Operación 'DELETE' no permitida."),
        ]

        result = _invoke_with_retries(
            prompt="Borrá mis datos",
            apm_id="APM_001",
            session_id="sess-1",
            mode="text",
        )

        assert result["success"] is False
        assert result["retries"] == 1
        assert "Solo tengo acceso de lectura" in result["result"]
        assert mock_agent.call_count == 2


# ---------------------------------------------------------------------------
# Retryable Errors — TimeoutError
# ---------------------------------------------------------------------------


class TestTimeoutRetry:
    """Test timeout errors are retried with simplification hint."""

    def test_timeout_retries_and_succeeds(self, mock_agent):
        mock_agent.side_effect = [
            TimeoutError("La query excedió el tiempo límite de 5 segundos."),
            "Resultado simplificado",
        ]

        result = _invoke_with_retries(
            prompt="Dame todas las ventas",
            apm_id="APM_001",
            session_id="sess-1",
            mode="text",
        )

        assert result["success"] is True
        assert result["retries"] == 1
        assert result["result"] == "Resultado simplificado"
        assert mock_agent.call_count == 2

        # Verify the retry prompt includes simplification hint
        retry_call_args = mock_agent.call_args_list[1][0][0]
        assert "Simplificá la query" in retry_call_args
        assert "timeout" in retry_call_args.lower()

    def test_timeout_all_retries_exhausted(self, mock_agent):
        mock_agent.side_effect = TimeoutError("timeout") 

        result = _invoke_with_retries(
            prompt="Query compleja",
            apm_id="APM_001",
            session_id="sess-1",
            mode="text",
        )

        assert result["success"] is False
        assert result["retries"] == MAX_RETRIES
        # ErrorHandler classifies TimeoutError as SQL timeout message
        assert "demasiado compleja" in result["result"] or "error" in result["result"].lower()
        assert mock_agent.call_count == MAX_RETRIES + 1


# ---------------------------------------------------------------------------
# Retryable Errors — RuntimeError (SQL execution)
# ---------------------------------------------------------------------------


class TestRuntimeErrorRetry:
    """Test SQL execution errors are retried with error context."""

    def test_runtime_error_retries_and_succeeds(self, mock_agent):
        mock_agent.side_effect = [
            RuntimeError("Error al ejecutar la query: column 'nombre_completo' does not exist"),
            "Dr. García - Cardiólogo",
        ]

        result = _invoke_with_retries(
            prompt="Buscá al Dr. García",
            apm_id="APM_001",
            session_id="sess-1",
            mode="text",
        )

        assert result["success"] is True
        assert result["retries"] == 1
        assert mock_agent.call_count == 2

        # Verify retry prompt includes SQL correction context
        retry_call_args = mock_agent.call_args_list[1][0][0]
        assert "Corregí la query SQL" in retry_call_args
        assert "nombre_completo" in retry_call_args

    def test_runtime_error_all_retries_exhausted(self, mock_agent):
        mock_agent.side_effect = RuntimeError("invalid syntax near 'FROM'")

        result = _invoke_with_retries(
            prompt="Mostrame datos",
            apm_id="APM_001",
            session_id="sess-1",
            mode="text",
        )

        assert result["success"] is False
        assert result["retries"] == MAX_RETRIES
        # ErrorHandler classifies exhausted RuntimeError with generic message
        assert "error" in result["result"].lower() or "Intentá" in result["result"]
        assert mock_agent.call_count == MAX_RETRIES + 1


# ---------------------------------------------------------------------------
# Retryable Errors — Generic Exception
# ---------------------------------------------------------------------------


class TestGenericErrorRetry:
    """Test generic exceptions are retried with error context."""

    def test_generic_exception_retries_and_succeeds(self, mock_agent):
        mock_agent.side_effect = [
            Exception("Unexpected network issue"),
            "Respuesta exitosa",
        ]

        result = _invoke_with_retries(
            prompt="¿Cuántas visitas hice?",
            apm_id="APM_001",
            session_id="sess-1",
            mode="text",
        )

        assert result["success"] is True
        assert result["retries"] == 1

    def test_generic_exception_all_retries_exhausted(self, mock_agent):
        mock_agent.side_effect = Exception("persistent failure")

        result = _invoke_with_retries(
            prompt="Pregunta",
            apm_id="APM_001",
            session_id="sess-1",
            mode="text",
        )

        assert result["success"] is False
        assert result["retries"] == MAX_RETRIES
        assert mock_agent.call_count == MAX_RETRIES + 1


# ---------------------------------------------------------------------------
# Retry Count (Req 3.4)
# ---------------------------------------------------------------------------


class TestRetryCount:
    """Test retry count in response metadata."""

    def test_retry_count_zero_on_first_success(self, mock_agent):
        mock_agent.return_value = "ok"
        result = _invoke_with_retries("q", "apm", "sess", "text")
        assert result["retries"] == 0

    def test_retry_count_one_after_one_failure(self, mock_agent):
        mock_agent.side_effect = [RuntimeError("err"), "ok"]
        result = _invoke_with_retries("q", "apm", "sess", "text")
        assert result["retries"] == 1

    def test_retry_count_two_after_two_failures(self, mock_agent):
        mock_agent.side_effect = [
            RuntimeError("err1"),
            RuntimeError("err2"),
            "ok",
        ]
        result = _invoke_with_retries("q", "apm", "sess", "text")
        assert result["retries"] == 2

    def test_retry_count_max_when_all_fail(self, mock_agent):
        mock_agent.side_effect = RuntimeError("persistent")
        result = _invoke_with_retries("q", "apm", "sess", "text")
        assert result["retries"] == MAX_RETRIES

    def test_retry_count_is_always_in_valid_range(self, mock_agent):
        """Retry count must always be in {0, 1, 2}."""
        mock_agent.side_effect = RuntimeError("fail forever")
        result = _invoke_with_retries("q", "apm", "sess", "text")
        assert result["retries"] in {0, 1, 2}


# ---------------------------------------------------------------------------
# Error Response Helper
# ---------------------------------------------------------------------------


class TestErrorResponse:
    """Test _error_response helper."""

    def test_error_response_structure(self):
        result = _error_response("Algo salió mal", retries=1)
        assert result == {
            "result": "Algo salió mal",
            "structured": {},
            "success": False,
            "retries": 1,
        }

    def test_error_response_defaults(self):
        result = _error_response("Error")
        assert result["retries"] == 0
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Prompt Context on Retry
# ---------------------------------------------------------------------------


class TestRetryPromptContext:
    """Test that retry prompts include helpful error context."""

    def test_timeout_retry_includes_simplification_hint(self, mock_agent):
        mock_agent.side_effect = [
            TimeoutError("query too slow"),
            "ok",
        ]
        _invoke_with_retries("original", "apm", "sess", "text")

        retry_prompt = mock_agent.call_args_list[1][0][0]
        assert "original" in retry_prompt
        assert "Simplificá" in retry_prompt
        assert "LIMIT" in retry_prompt

    def test_runtime_error_retry_includes_sql_fix_hint(self, mock_agent):
        mock_agent.side_effect = [
            RuntimeError("Error: column 'x' not found"),
            "ok",
        ]
        _invoke_with_retries("original", "apm", "sess", "text")

        retry_prompt = mock_agent.call_args_list[1][0][0]
        assert "original" in retry_prompt
        assert "Corregí la query SQL" in retry_prompt
        assert "column 'x' not found" in retry_prompt

    def test_retry_prompt_always_includes_original_prompt(self, mock_agent):
        """The original prompt must be included in every retry so context isn't lost."""
        mock_agent.side_effect = [
            RuntimeError("err"),
            TimeoutError("timeout"),
            "ok",
        ]
        _invoke_with_retries("mi pregunta original", "apm", "sess", "text")

        for call in mock_agent.call_args_list[1:]:
            assert "mi pregunta original" in call[0][0]
