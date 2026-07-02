"""Tests for ResponseFormatter — validates structured data extraction and formatting.

Requirements tested: 21.1, 21.2, 21.3, 21.4, 21.5
"""

import json
import pytest

from agentcore.response_formatter import ResponseFormatter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_structured_marker(columns, rows, total_rows=None, truncated=False):
    """Build a <!--STRUCTURED:...--> marker string."""
    data = {
        "columns": columns,
        "rows": rows,
        "total_rows": total_rows or len(rows),
        "truncated": truncated,
    }
    return f"<!--STRUCTURED:{json.dumps(data, ensure_ascii=False)}-->"


# ---------------------------------------------------------------------------
# Test: Marker extraction and clean text
# ---------------------------------------------------------------------------

class TestMarkerExtraction:
    def test_removes_structured_markers_from_result(self):
        marker = _make_structured_marker(["a"], [{"a": 1}])
        text = f"Resultado:\n\n{marker}"
        result = ResponseFormatter.format_response(text, "test")
        assert "<!--STRUCTURED" not in result["result"]
        assert "Resultado:" in result["result"]

    def test_handles_no_markers(self):
        text = "Simple text response without any data"
        result = ResponseFormatter.format_response(text, "test")
        assert result["result"] == text
        assert result["structured"]["table"] is None
        assert result["structured"]["chart"] is None

    def test_uses_last_marker_when_multiple(self):
        marker1 = _make_structured_marker(["x"], [{"x": 1}])
        marker2 = _make_structured_marker(["y", "z"], [{"y": 1, "z": 2}, {"y": 3, "z": 4}, {"y": 5, "z": 6}])
        text = f"First result\n{marker1}\nSecond result\n{marker2}"
        result = ResponseFormatter.format_response(text, "ventas por zona")
        # Table should come from the second marker (has 3 rows > 2)
        assert result["structured"]["table"] is not None
        assert result["structured"]["table"]["columns"] == ["y", "z"]

    def test_handles_malformed_json_gracefully(self):
        text = "Some text\n\n<!--STRUCTURED:not valid json-->"
        result = ResponseFormatter.format_response(text, "test")
        assert result["structured"]["table"] is None
        assert "<!--STRUCTURED" not in result["result"]


# ---------------------------------------------------------------------------
# Test: Table rendering threshold (Requirement 21.1, 21.5)
# ---------------------------------------------------------------------------

class TestTableRendering:
    def test_no_table_when_2_or_fewer_rows(self):
        rows = [{"col1": "a", "col2": 1}, {"col1": "b", "col2": 2}]
        marker = _make_structured_marker(["col1", "col2"], rows)
        text = f"Data:\n{marker}"
        result = ResponseFormatter.format_response(text, "test")
        assert result["structured"]["table"] is None

    def test_table_present_when_more_than_2_rows(self):
        rows = [{"col1": "a"}, {"col1": "b"}, {"col1": "c"}]
        marker = _make_structured_marker(["col1"], rows)
        text = f"Data:\n{marker}"
        result = ResponseFormatter.format_response(text, "test")
        assert result["structured"]["table"] is not None
        assert len(result["structured"]["table"]["rows"]) == 3

    def test_table_capped_at_100_rows(self):
        rows = [{"col1": i} for i in range(150)]
        marker = _make_structured_marker(["col1"], rows, total_rows=150, truncated=True)
        text = f"Data:\n{marker}"
        result = ResponseFormatter.format_response(text, "test")
        assert result["structured"]["table"] is not None
        assert len(result["structured"]["table"]["rows"]) == 100


# ---------------------------------------------------------------------------
# Test: SQL extraction (Requirement 21.3)
# ---------------------------------------------------------------------------

class TestSqlExtraction:
    def test_extracts_sql_from_code_block(self):
        text = "Ejecuté la siguiente query:\n\n```sql\nSELECT * FROM medicos WHERE zona = 'Belgrano'\n```\n\nResultado..."
        result = ResponseFormatter.format_response(text, "test")
        assert result["structured"]["sql"] is not None
        assert "SELECT * FROM medicos" in result["structured"]["sql"]

    def test_extracts_sql_from_inline_pattern(self):
        text = "Query ejecutada: SELECT count(*) FROM visitas\n\nLos resultados son..."
        result = ResponseFormatter.format_response(text, "test")
        assert result["structured"]["sql"] is not None
        assert "SELECT count(*)" in result["structured"]["sql"]

    def test_no_sql_when_not_present(self):
        text = "No hay datos de ventas en tu cartera."
        result = ResponseFormatter.format_response(text, "test")
        assert result["structured"]["sql"] is None

    def test_uses_last_sql_code_block(self):
        text = "```sql\nSELECT 1\n```\nReintentando...\n```sql\nSELECT 2\n```"
        result = ResponseFormatter.format_response(text, "test")
        assert result["structured"]["sql"] == "SELECT 2"


# ---------------------------------------------------------------------------
# Test: Chart detection (Requirement 21.2)
# ---------------------------------------------------------------------------

class TestChartDetection:
    def test_detects_chart_with_temporal_and_numeric(self):
        rows = [
            {"mes": "Enero", "unidades": 100, "valor": 5000},
            {"mes": "Febrero", "unidades": 120, "valor": 6000},
            {"mes": "Marzo", "unidades": 110, "valor": 5500},
        ]
        marker = _make_structured_marker(["mes", "unidades", "valor"], rows)
        text = f"Evolución:\n{marker}"
        result = ResponseFormatter.format_response(text, "ventas por mes")
        chart = result["structured"]["chart"]
        assert chart is not None
        assert chart["type"] == "bar"  # mes → bar
        assert chart["xAxis"] == "mes"
        assert len(chart["series"]) == 2
        assert chart["series"][0]["dataKey"] == "unidades"

    def test_line_chart_for_fecha_column(self):
        rows = [
            {"fecha": "2024-01-01", "total": 100},
            {"fecha": "2024-02-01", "total": 120},
            {"fecha": "2024-03-01", "total": 130},
        ]
        marker = _make_structured_marker(["fecha", "total"], rows)
        text = f"Tendencia:\n{marker}"
        result = ResponseFormatter.format_response(text, "evolución")
        chart = result["structured"]["chart"]
        assert chart is not None
        assert chart["type"] == "line"
        assert chart["xAxis"] == "fecha"

    def test_no_chart_without_temporal_column(self):
        rows = [
            {"zona": "Belgrano", "total": 100},
            {"zona": "Palermo", "total": 200},
            {"zona": "Recoleta", "total": 150},
        ]
        marker = _make_structured_marker(["zona", "total"], rows)
        text = f"Por zona:\n{marker}"
        result = ResponseFormatter.format_response(text, "ventas por zona")
        assert result["structured"]["chart"] is None

    def test_no_chart_without_numeric_columns(self):
        rows = [
            {"fecha": "2024-01", "estado": "activo"},
            {"fecha": "2024-02", "estado": "inactivo"},
            {"fecha": "2024-03", "estado": "activo"},
        ]
        marker = _make_structured_marker(["fecha", "estado"], rows)
        text = f"Estados:\n{marker}"
        result = ResponseFormatter.format_response(text, "estados")
        assert result["structured"]["chart"] is None

    def test_no_chart_with_2_or_fewer_rows(self):
        rows = [
            {"fecha": "2024-01", "total": 100},
            {"fecha": "2024-02", "total": 200},
        ]
        marker = _make_structured_marker(["fecha", "total"], rows)
        text = f"Datos:\n{marker}"
        result = ResponseFormatter.format_response(text, "tendencia")
        assert result["structured"]["chart"] is None


# ---------------------------------------------------------------------------
# Test: Suggestions generation (Requirement 21.4)
# ---------------------------------------------------------------------------

class TestSuggestions:
    def test_generates_2_to_3_suggestions(self):
        text = "Los resultados de ventas son..."
        result = ResponseFormatter.format_response(text, "¿Cuáles son mis ventas del mes?")
        suggestions = result["structured"]["suggestions"]
        assert 2 <= len(suggestions) <= 3

    def test_ventas_topic_suggestions(self):
        text = "Top 10 productos..."
        result = ResponseFormatter.format_response(text, "¿Cuáles son los top 10 productos en ventas?")
        suggestions = result["structured"]["suggestions"]
        assert len(suggestions) >= 2
        # Should contain relevant follow-ups for ventas + top
        assert any("menor" in s.lower() or "zona" in s.lower() or "tendencia" in s.lower() for s in suggestions)

    def test_medicos_topic_suggestions(self):
        text = "El Dr. Pérez es cardiólogo..."
        result = ResponseFormatter.format_response(text, "¿Qué información tenés del Dr. Pérez?")
        suggestions = result["structured"]["suggestions"]
        assert len(suggestions) >= 2

    def test_generic_fallback_suggestions(self):
        text = "Información general del sistema."
        result = ResponseFormatter.format_response(text, "hola")
        suggestions = result["structured"]["suggestions"]
        assert 2 <= len(suggestions) <= 3

    def test_suggestions_are_strings(self):
        text = "Resultados"
        result = ResponseFormatter.format_response(text, "¿Cuáles son mis visitas?")
        for s in result["structured"]["suggestions"]:
            assert isinstance(s, str)
            assert len(s) > 0
