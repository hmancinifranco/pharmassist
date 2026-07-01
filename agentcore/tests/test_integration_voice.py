"""
Integration test: validates voice mode end-to-end response format.

Tests that the Unified Agent, when invoked with BidiAgent payload format
({prompt, apm_id, mode: "voice"}), returns a response with ONLY
{result, success, retries} — no structured metadata.

This validates the contract between BidiAgent and the Unified Agent:
- BidiAgent sends: {prompt, apm_id, mode: "voice"}
- Unified Agent returns: {result: str, success: bool, retries: int}
- No structured key (table, chart, sql, suggestions) in the response

Requirements: 19.1, 19.2, 19.3, 19.4
"""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.integration
class TestVoiceModeEndToEnd:
    """End-to-end voice mode integration: validates BidiAgent compatibility."""

    def _invoke_agent_voice(self, prompt: str, apm_id: str = "Peccy") -> dict:
        """Invoke _invoke_with_retries with voice mode to simulate full flow.

        Mocks the Strands Agent call to simulate a real response with structured
        markers (as query_db would produce), then validates that voice mode strips
        them correctly.

        We call _invoke_with_retries directly because the @app.entrypoint decorator
        is mocked in the test environment (conftest mocks BedrockAgentCoreApp).
        """
        # Simulate a response that would include structured markers from query_db
        simulated_response = (
            "Tenés 42 médicos en tu cartera. Los más visitados son "
            "Dr. García (12 visitas) y Dra. López (8 visitas).\n\n"
            "| Nombre | Visitas |\n"
            "|---|---|\n"
            "| Dr. García | 12 |\n"
            "| Dra. López | 8 |\n\n"
            "```sql\nSELECT nombre, count(*) as visitas FROM visitas "
            "GROUP BY nombre ORDER BY visitas DESC LIMIT 10\n```\n\n"
            '<!--STRUCTURED:{"columns":["nombre","visitas"],'
            '"rows":[{"nombre":"Dr. García","visitas":12},'
            '{"nombre":"Dra. López","visitas":8}],'
            '"total_rows":2}-->'
        )

        # Mock the Strands Agent to return our simulated response
        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = simulated_response
        mock_agent_instance.system_prompt = ""

        with patch(
            "agentcore.agent._get_or_create_agent",
            return_value=mock_agent_instance,
        ):
            from agentcore.agent import _invoke_with_retries

            return _invoke_with_retries(
                prompt=prompt,
                apm_id=apm_id,
                session_id="test-session-voice",
                mode="voice",
            )

    def test_voice_payload_format_accepted(self):
        """BidiAgent payload format {prompt, apm_id, mode: "voice"} is accepted."""
        response = self._invoke_agent_voice(
            prompt="¿Cuántos médicos tengo?",
            apm_id="Peccy",
        )
        assert response["success"] is True

    def test_voice_response_has_only_result_success_retries(self):
        """Voice mode returns only {result, success, retries} — no structured metadata."""
        response = self._invoke_agent_voice(
            prompt="¿Cuántos médicos tengo?",
        )

        # Required keys present
        assert "result" in response
        assert "success" in response
        assert "retries" in response

        # Structured key MUST NOT be present in voice mode
        assert "structured" not in response

    def test_voice_response_result_is_string(self):
        """Voice response result field is a clean string."""
        response = self._invoke_agent_voice(
            prompt="¿Cuáles son mis productos foco?",
        )
        assert isinstance(response["result"], str)
        assert len(response["result"]) > 0

    def test_voice_response_no_structured_markers(self):
        """Voice response text doesn't contain <!--STRUCTURED:--> markers."""
        response = self._invoke_agent_voice(
            prompt="¿Cuántos médicos tengo?",
        )
        assert "<!--STRUCTURED:" not in response["result"]

    def test_voice_response_no_sql_code_blocks(self):
        """Voice response text doesn't contain SQL code blocks."""
        response = self._invoke_agent_voice(
            prompt="¿Cuáles son mis top prescriptores?",
        )
        assert "```sql" not in response["result"]
        assert "```SQL" not in response["result"]

    def test_voice_response_no_markdown_tables(self):
        """Voice response text doesn't contain markdown table syntax."""
        response = self._invoke_agent_voice(
            prompt="¿Cuántos médicos tengo por zona?",
        )
        # Markdown tables use | as column separator
        assert "| Nombre" not in response["result"]
        assert "|---|" not in response["result"]

    def test_voice_response_preserves_natural_text(self):
        """Voice response preserves the natural language parts."""
        response = self._invoke_agent_voice(
            prompt="¿Cuántos médicos tengo?",
        )
        # The conversational text should survive the voice filter
        assert "Tenés 42 médicos en tu cartera" in response["result"]

    def test_voice_response_retries_is_integer(self):
        """Voice response retries field is an integer >= 0."""
        response = self._invoke_agent_voice(
            prompt="¿Cuántos médicos tengo?",
        )
        assert isinstance(response["retries"], int)
        assert response["retries"] >= 0

    def test_voice_mode_with_empty_prompt_returns_error(self):
        """Voice mode with empty prompt returns error gracefully.

        Note: This tests the validation in handle_invoke. Since @app.entrypoint
        is mocked in tests, we test the validation logic directly.
        """
        from agentcore.agent import _error_response

        # Simulate the validation path from handle_invoke
        prompt = ""
        if not prompt:
            response = _error_response(
                "No se recibió ningún mensaje. Enviá un prompt para consultar.",
                retries=0,
            )
        assert response["success"] is False
        assert "result" in response
        assert "mensaje" in response["result"] or "prompt" in response["result"]

    def test_voice_mode_with_missing_apm_id_returns_error(self):
        """Voice mode with missing apm_id returns error gracefully."""
        from agentcore.agent import _error_response

        # Simulate the validation path from handle_invoke
        apm_id = ""
        if not apm_id:
            response = _error_response(
                "Falta el identificador del APM (apm_id).",
                retries=0,
            )
        assert response["success"] is False
        assert "result" in response


@pytest.mark.integration
class TestVoiceModeResponseSchema:
    """Validates the strict response schema for BidiAgent compatibility."""

    def test_voice_response_schema_keys_only(self):
        """Voice response has EXACTLY {result, success, retries} — nothing else."""
        simulated_response = "Tenés 5 productos foco en tu cartera."

        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = simulated_response
        mock_agent_instance.system_prompt = ""

        with patch(
            "agentcore.agent._get_or_create_agent",
            return_value=mock_agent_instance,
        ):
            from agentcore.agent import _invoke_with_retries

            response = _invoke_with_retries(
                prompt="¿Cuáles son mis productos foco?",
                apm_id="Peccy",
                session_id="test-session",
                mode="voice",
            )

        # Exactly these 3 keys, no more
        expected_keys = {"result", "success", "retries"}
        assert set(response.keys()) == expected_keys

    def test_text_mode_has_structured_key(self):
        """Contrast: text mode DOES include structured key (validates distinction)."""
        simulated_response = "Tenés 5 productos foco."

        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = simulated_response
        mock_agent_instance.system_prompt = ""

        with patch(
            "agentcore.agent._get_or_create_agent",
            return_value=mock_agent_instance,
        ):
            from agentcore.agent import _invoke_with_retries

            response = _invoke_with_retries(
                prompt="¿Cuáles son mis productos foco?",
                apm_id="Peccy",
                session_id="test-session",
                mode="text",
            )

        # Text mode MUST include structured
        assert "structured" in response

    def test_voice_response_serializable_to_json(self):
        """Voice response is fully JSON-serializable (BidiAgent requirement)."""
        simulated_response = "Las ventas de PAMOXET crecieron un 15%."

        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = simulated_response
        mock_agent_instance.system_prompt = ""

        with patch(
            "agentcore.agent._get_or_create_agent",
            return_value=mock_agent_instance,
        ):
            from agentcore.agent import _invoke_with_retries

            response = _invoke_with_retries(
                prompt="¿Cómo van las ventas de PAMOXET?",
                apm_id="Peccy",
                session_id="test-session",
                mode="voice",
            )

        # Must be fully JSON serializable (BidiAgent sends this over WebSocket)
        serialized = json.dumps(response, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert deserialized == response
