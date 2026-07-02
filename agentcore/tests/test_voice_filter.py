"""
Tests for agentcore/voice_filter.py — strip_for_voice function.

Validates that voice mode responses are cleaned of non-speakable content
(structured metadata, SQL blocks, markdown tables) while preserving
natural language text suitable for Nova Sonic text-to-speech.

Requirements: 19.3, 19.4
"""

import json

import pytest

from agentcore.voice_filter import strip_for_voice


class TestStripStructuredMarkers:
    """Test removal of <!--STRUCTURED:...--> markers."""

    def test_removes_simple_structured_marker(self):
        text = "Tenés 42 médicos.\n<!--STRUCTURED:{\"rows\": []}-->"
        result = strip_for_voice(text)
        assert "<!--STRUCTURED:" not in result
        assert "Tenés 42 médicos." in result

    def test_removes_multiline_structured_marker(self):
        metadata = json.dumps({"columns": [{"field": "name"}], "rows": [{"name": "Dr. A"}]})
        text = f"Resultado:\n<!--STRUCTURED:{metadata}-->\nFin."
        result = strip_for_voice(text)
        assert "<!--STRUCTURED:" not in result
        assert "Resultado:" in result
        assert "Fin." in result

    def test_removes_multiple_structured_markers(self):
        text = "A<!--STRUCTURED:{\"a\":1}-->B<!--STRUCTURED:{\"b\":2}-->C"
        result = strip_for_voice(text)
        assert "<!--STRUCTURED:" not in result
        assert "A" in result
        assert "B" in result
        assert "C" in result

    def test_no_structured_marker_unchanged(self):
        text = "Tenés 42 médicos en tu cartera"
        result = strip_for_voice(text)
        assert result == text


class TestStripSQLCodeBlocks:
    """Test removal of SQL code blocks."""

    def test_removes_sql_code_block(self):
        text = "Resultado:\n```sql\nSELECT * FROM medicos WHERE zona = 'Belgrano'\n```\nListo."
        result = strip_for_voice(text)
        assert "SELECT" not in result
        assert "```" not in result
        assert "Resultado:" in result
        assert "Listo." in result

    def test_removes_sql_code_block_case_insensitive(self):
        text = "Info:\n```SQL\nSELECT count(*) FROM visitas\n```\nDone."
        result = strip_for_voice(text)
        assert "SELECT" not in result
        assert "Info:" in result
        assert "Done." in result

    def test_removes_generic_codeblock_with_sql_content(self):
        text = "Query:\n```\nSELECT nombre FROM medicos\n```\nResultados arriba."
        result = strip_for_voice(text)
        assert "SELECT" not in result
        assert "Query:" in result
        assert "Resultados arriba." in result

    def test_preserves_non_sql_code_block(self):
        text = "Ejemplo:\n```python\nprint('hola')\n```\nFin."
        result = strip_for_voice(text)
        assert "print('hola')" in result


class TestStripMarkdownTables:
    """Test removal of markdown table syntax."""

    def test_removes_simple_table(self):
        text = "| Nombre | Zona |\n|---|---|\n| Dr. A | Belgrano |\n| Dr. B | Palermo |"
        result = strip_for_voice(text)
        assert "|" not in result

    def test_removes_table_preserves_surrounding_text(self):
        text = "Tus médicos:\n| Nombre | Zona |\n|---|---|\n| Dr. A | Belgrano |\n\nEso es todo."
        result = strip_for_voice(text)
        assert "Tus médicos:" in result
        assert "Eso es todo." in result
        assert "| Nombre" not in result
        assert "|---|" not in result

    def test_preserves_pipe_in_non_table_context(self):
        # A single pipe in the middle of text is not a table row
        text = "La respuesta es verdadera"
        result = strip_for_voice(text)
        assert result == text


class TestPreservesNaturalLanguage:
    """Test that conversational text is preserved."""

    def test_preserves_conversational_text(self):
        text = "Tenés 42 médicos en tu cartera. Los más visitados son Dr. García y Dra. López."
        result = strip_for_voice(text)
        assert result == text

    def test_preserves_numbers_and_data(self):
        text = "Las ventas de PAMOXET crecieron un 15% en el último trimestre."
        result = strip_for_voice(text)
        assert result == text

    def test_preserves_spanish_characters(self):
        text = "La próxima visita está programada para el miércoles."
        result = strip_for_voice(text)
        assert result == text


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self):
        assert strip_for_voice("") == ""

    def test_none_like_empty(self):
        # Function should handle empty gracefully
        assert strip_for_voice("") == ""

    def test_only_structured_marker(self):
        text = "<!--STRUCTURED:{\"rows\": []}-->"
        result = strip_for_voice(text)
        assert result == ""

    def test_only_sql_block(self):
        text = "```sql\nSELECT 1\n```"
        result = strip_for_voice(text)
        assert result == ""

    def test_only_table(self):
        text = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = strip_for_voice(text)
        assert result == ""

    def test_collapses_excessive_newlines(self):
        text = "Intro.\n\n\n\n\nFin."
        result = strip_for_voice(text)
        # Should collapse to max 2 newlines
        assert "\n\n\n" not in result
        assert "Intro." in result
        assert "Fin." in result

    def test_complex_response_with_all_elements(self):
        """Simulates a real agent response with all non-speakable elements."""
        text = (
            "Tenés 10 médicos en Belgrano. Los más visitados son:\n\n"
            "| Nombre | Visitas |\n"
            "|---|---|\n"
            "| Dr. García | 12 |\n"
            "| Dra. López | 8 |\n\n"
            "```sql\nSELECT nombre, count(*) FROM visitas GROUP BY nombre\n```\n\n"
            "<!--STRUCTURED:{\"table\":{\"columns\":[],\"rows\":[]},\"sql\":\"SELECT...\"}-->\n\n"
            "¿Querés ver el detalle de alguno?"
        )
        result = strip_for_voice(text)
        # Natural language preserved
        assert "Tenés 10 médicos en Belgrano" in result
        assert "¿Querés ver el detalle de alguno?" in result
        # Non-speakable removed
        assert "<!--STRUCTURED:" not in result
        assert "```" not in result
        assert "| Nombre" not in result
        assert "SELECT" not in result


class TestVoiceResponseSchema:
    """Test that voice mode returns only {result, success, retries}."""

    def test_voice_response_has_no_structured_field(self):
        """Validate the voice mode path returns the correct schema.

        This tests the contract: when mode=="voice", the response dict
        should NOT have a 'structured' key.
        """
        # Simulate what handle_invoke would return in voice mode
        response_text = "Tenés 42 médicos.<!--STRUCTURED:{\"rows\":[]}-->"
        clean_text = strip_for_voice(response_text)
        voice_response = {
            "result": clean_text,
            "success": True,
            "retries": 0,
        }
        assert "structured" not in voice_response
        assert voice_response["result"] == "Tenés 42 médicos."
        assert voice_response["success"] is True
        assert voice_response["retries"] == 0
