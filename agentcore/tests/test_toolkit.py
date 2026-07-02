"""
Unit tests for PharmaToolkit — SQL validation and output formatting.

Tests the core logic of query_db without requiring a real database connection.
Validates: Requirements 2.1, 2.2, 2.6, 4.1, 16.1, 16.2, 16.3
"""

import json

import pandas as pd
import pytest

from agentcore.toolkit import PharmaToolkit, _MAX_STRUCTURED_ROWS, _MAX_TEXT_ROWS


# ---------------------------------------------------------------------------
# Fixture: PharmaToolkit instance (without engine — for validation tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def toolkit():
    """Create a PharmaToolkit instance without connecting to a database."""
    return PharmaToolkit(db_secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:test")


# ---------------------------------------------------------------------------
# SQL Validation Tests
# ---------------------------------------------------------------------------


class TestSQLValidation:
    """Test SQL validation logic (Req 2.1, 2.2, 16.1)."""

    def test_accepts_select(self, toolkit):
        result = toolkit._validate_sql("SELECT * FROM medicos")
        assert result == "SELECT * FROM medicos"

    def test_accepts_select_case_insensitive(self, toolkit):
        result = toolkit._validate_sql("select id from ciclo")
        assert result == "select id from ciclo"

    def test_accepts_select_with_leading_whitespace(self, toolkit):
        result = toolkit._validate_sql("   SELECT * FROM medicos")
        assert result == "SELECT * FROM medicos"

    def test_accepts_with_cte(self, toolkit):
        sql = "WITH top_docs AS (SELECT * FROM medicos) SELECT * FROM top_docs"
        result = toolkit._validate_sql(sql)
        assert result == sql

    def test_accepts_with_case_insensitive(self, toolkit):
        sql = "with cte as (select 1) select * from cte"
        result = toolkit._validate_sql(sql)
        assert result == sql

    def test_rejects_insert(self, toolkit):
        with pytest.raises(ValueError, match="INSERT.*no permitida"):
            toolkit._validate_sql("INSERT INTO medicos VALUES (1, 'test')")

    def test_rejects_update(self, toolkit):
        with pytest.raises(ValueError, match="UPDATE.*no permitida"):
            toolkit._validate_sql("UPDATE medicos SET nombre = 'x'")

    def test_rejects_delete(self, toolkit):
        with pytest.raises(ValueError, match="DELETE.*no permitida"):
            toolkit._validate_sql("DELETE FROM medicos")

    def test_rejects_drop(self, toolkit):
        with pytest.raises(ValueError, match="DROP.*no permitida"):
            toolkit._validate_sql("DROP TABLE medicos")

    def test_rejects_alter(self, toolkit):
        with pytest.raises(ValueError, match="ALTER.*no permitida"):
            toolkit._validate_sql("ALTER TABLE medicos ADD COLUMN x INT")

    def test_rejects_create(self, toolkit):
        with pytest.raises(ValueError, match="CREATE.*no permitida"):
            toolkit._validate_sql("CREATE TABLE evil (id int)")

    def test_rejects_truncate(self, toolkit):
        with pytest.raises(ValueError, match="TRUNCATE.*no permitida"):
            toolkit._validate_sql("TRUNCATE medicos")

    def test_rejects_grant(self, toolkit):
        with pytest.raises(ValueError, match="GRANT.*no permitida"):
            toolkit._validate_sql("GRANT ALL ON medicos TO public")

    def test_rejects_revoke(self, toolkit):
        with pytest.raises(ValueError, match="REVOKE.*no permitida"):
            toolkit._validate_sql("REVOKE ALL ON medicos FROM public")

    def test_rejects_empty_string(self, toolkit):
        with pytest.raises(ValueError, match="vacía"):
            toolkit._validate_sql("")

    def test_rejects_whitespace_only(self, toolkit):
        with pytest.raises(ValueError, match="vacía"):
            toolkit._validate_sql("   ")

    def test_rejects_multi_statement_semicolon(self, toolkit):
        with pytest.raises(ValueError, match="múltiples sentencias"):
            toolkit._validate_sql("SELECT 1; DROP TABLE medicos")

    def test_allows_trailing_semicolon(self, toolkit):
        result = toolkit._validate_sql("SELECT * FROM medicos;")
        assert result == "SELECT * FROM medicos;"

    def test_rejects_unknown_statement(self, toolkit):
        with pytest.raises(ValueError, match="Solo se permiten queries SELECT o WITH"):
            toolkit._validate_sql("EXPLAIN SELECT * FROM medicos")


# ---------------------------------------------------------------------------
# Output Formatting Tests
# ---------------------------------------------------------------------------


class TestOutputFormatting:
    """Test result formatting (Req 2.6, 16.2, 16.3)."""

    def test_format_result_empty_dataframe(self, toolkit):
        df = pd.DataFrame()
        result = toolkit._format_result(df)
        assert "no devolvió resultados" in result
        assert "<!--STRUCTURED:" in result

    def test_format_result_includes_structured_metadata(self, toolkit):
        df = pd.DataFrame({"id": [1, 2, 3], "nombre": ["A", "B", "C"]})
        result = toolkit._format_result(df)

        # Extract structured metadata
        assert "<!--STRUCTURED:" in result
        assert "-->", result

        # Parse the JSON
        start = result.index("<!--STRUCTURED:") + len("<!--STRUCTURED:")
        end = result.index("-->", start)
        metadata = json.loads(result[start:end])

        assert metadata["columns"] == ["id", "nombre"]
        assert len(metadata["rows"]) == 3
        assert metadata["total_rows"] == 3
        assert metadata["truncated"] is False

    def test_format_result_text_limited_to_50_rows(self, toolkit):
        df = pd.DataFrame({"val": list(range(80))})
        result = toolkit._format_result(df)

        # Text part should mention truncation
        assert f"Mostrando {_MAX_TEXT_ROWS} de 80 filas totales" in result

        # Count rows in the markdown table (lines between header and structured)
        text_part = result.split("<!--STRUCTURED:")[0]
        table_lines = [
            l for l in text_part.strip().split("\n")
            if l.startswith("|") and "------" not in l and l != text_part.strip().split("\n")[0]
        ]
        # Header line + data lines = 1 header + 50 data
        data_lines = [l for l in text_part.strip().split("\n") if l.startswith("|")]
        # Subtract header and separator
        actual_data_rows = len(data_lines) - 2
        assert actual_data_rows == _MAX_TEXT_ROWS

    def test_format_result_structured_limited_to_100_rows(self, toolkit):
        df = pd.DataFrame({"val": list(range(150))})
        result = toolkit._format_result(df)

        # Parse structured metadata
        start = result.index("<!--STRUCTURED:") + len("<!--STRUCTURED:")
        end = result.index("-->", start)
        metadata = json.loads(result[start:end])

        assert len(metadata["rows"]) == _MAX_STRUCTURED_ROWS
        assert metadata["total_rows"] == 150
        assert metadata["truncated"] is True

    def test_format_result_handles_none_values(self, toolkit):
        df = pd.DataFrame({"id": [1, 2], "nombre": ["A", None]})
        result = toolkit._format_result(df)

        start = result.index("<!--STRUCTURED:") + len("<!--STRUCTURED:")
        end = result.index("-->", start)
        metadata = json.loads(result[start:end])

        # None values should be preserved as null in JSON
        assert metadata["rows"][1]["nombre"] is None

    def test_markdown_table_format(self, toolkit):
        df = pd.DataFrame({"col_a": [1], "col_b": ["test"]})
        result = toolkit._dataframe_to_markdown(df)

        assert "| col_a | col_b |" in result
        assert "|------|------|" in result
        assert "| 1 | test |" in result


# ---------------------------------------------------------------------------
# Safe Error Message Tests
# ---------------------------------------------------------------------------


class TestSafeErrorMessage:
    """Test that error messages don't leak sensitive info (Req 16.1, 16.3)."""

    def test_removes_connection_string(self, toolkit):
        error = "connection to postgresql+pg8000://user:pass@host.rds.amazonaws.com:5432/db failed"
        result = toolkit._safe_error_message(error)
        assert "user:pass" not in result
        assert "host.rds" not in result

    def test_removes_ip_address(self, toolkit):
        error = "could not connect to 10.0.1.45:5432"
        result = toolkit._safe_error_message(error)
        assert "10.0.1.45" not in result

    def test_removes_rds_hostname(self, toolkit):
        error = "connection to my-cluster.cluster-abc123.us-east-1.rds.amazonaws.com refused"
        result = toolkit._safe_error_message(error)
        assert "my-cluster" not in result
        assert "rds.amazonaws.com" not in result

    def test_truncates_long_messages(self, toolkit):
        error = "x" * 500
        result = toolkit._safe_error_message(error)
        assert len(result) <= 203  # 200 chars + "..."
