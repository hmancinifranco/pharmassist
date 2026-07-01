"""
Tests for agentcore/observability.py — timing, metrics, and tracing.

Requirements: 7.1, 7.2, 7.3, 7.4
"""

import json
import logging
import time
from unittest.mock import patch

import pytest

from agentcore.observability import (
    RequestTracer,
    emit_error_metric,
    emit_metric,
    timed_operation,
    traced_tool,
)


class TestEmitMetric:
    """Tests for emit_metric structured logging."""

    def test_emits_metric_as_json_log(self, caplog):
        """Verify metric is emitted as structured JSON in log."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            emit_metric("agent_e2e_latency_ms", 150.5, unit="ms", apm_id="APM_001")

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert "METRIC" in record.message

        # Parse the JSON from the log message
        json_str = record.message.replace("METRIC ", "")
        data = json.loads(json_str)

        assert data["metric_name"] == "agent_e2e_latency_ms"
        assert data["value"] == 150.5
        assert data["unit"] == "ms"
        assert data["apm_id"] == "APM_001"

    def test_emits_metric_with_multiple_dimensions(self, caplog):
        """Verify multiple dimensions are included in metric."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            emit_metric(
                "tool_query_db_latency_ms",
                42.3,
                unit="ms",
                apm_id="APM_002",
                success=True,
                rows_returned=15,
            )

        json_str = caplog.records[0].message.replace("METRIC ", "")
        data = json.loads(json_str)

        assert data["metric_name"] == "tool_query_db_latency_ms"
        assert data["value"] == 42.3
        assert data["success"] is True
        assert data["rows_returned"] == 15


class TestEmitErrorMetric:
    """Tests for emit_error_metric."""

    def test_emits_error_metric_with_type_and_message(self, caplog):
        """Verify error metric includes error_type and error_message."""
        with caplog.at_level(logging.ERROR, logger="agentcore.observability"):
            emit_error_metric(
                error_type="TimeoutError",
                error_message="Query timed out after 5s",
                apm_id="APM_003",
                context="query_db",
            )

        assert len(caplog.records) == 1
        json_str = caplog.records[0].message.replace("METRIC ", "")
        data = json.loads(json_str)

        assert data["metric_name"] == "agent_error"
        assert data["error_type"] == "TimeoutError"
        assert data["error_message"] == "Query timed out after 5s"
        assert data["apm_id"] == "APM_003"
        assert data["context"] == "query_db"

    def test_truncates_long_error_messages(self, caplog):
        """Verify error messages are truncated to 200 chars."""
        long_msg = "x" * 500
        with caplog.at_level(logging.ERROR, logger="agentcore.observability"):
            emit_error_metric(
                error_type="RuntimeError",
                error_message=long_msg,
                apm_id="APM_004",
            )

        json_str = caplog.records[0].message.replace("METRIC ", "")
        data = json.loads(json_str)
        assert len(data["error_message"]) == 200


class TestTimedOperation:
    """Tests for timed_operation context manager."""

    def test_emits_timing_metric(self, caplog):
        """Verify timed_operation emits a latency metric."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            with timed_operation("query_db", apm_id="APM_005"):
                time.sleep(0.01)  # 10ms minimum

        # Find the metric log
        metric_logs = [r for r in caplog.records if "METRIC" in r.message]
        assert len(metric_logs) >= 1

        json_str = metric_logs[0].message.replace("METRIC ", "")
        data = json.loads(json_str)
        assert data["metric_name"] == "tool_query_db_latency_ms"
        assert data["value"] >= 10.0  # At least 10ms
        assert data["apm_id"] == "APM_005"

    def test_propagates_exceptions(self, caplog):
        """Verify exceptions are not swallowed by timed_operation."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            with pytest.raises(ValueError, match="test error"):
                with timed_operation("query_db"):
                    raise ValueError("test error")

    def test_emits_metric_even_on_exception(self, caplog):
        """Verify metric is emitted even when operation raises."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            try:
                with timed_operation("query_db"):
                    raise RuntimeError("boom")
            except RuntimeError:
                pass

        metric_logs = [r for r in caplog.records if "METRIC" in r.message]
        assert len(metric_logs) >= 1

    def test_maps_e2e_operation_name(self, caplog):
        """Verify e2e operation maps to agent_e2e_latency_ms."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            with timed_operation("e2e"):
                pass

        json_str = [r for r in caplog.records if "METRIC" in r.message][0].message.replace("METRIC ", "")
        data = json.loads(json_str)
        assert data["metric_name"] == "agent_e2e_latency_ms"


class TestTracedToolDecorator:
    """Tests for traced_tool decorator."""

    def test_measures_tool_execution_time(self, caplog):
        """Verify traced_tool emits latency metric."""

        @traced_tool("query_db")
        def my_tool(sql: str) -> str:
            time.sleep(0.01)
            return "result"

        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            result = my_tool("SELECT 1")

        assert result == "result"
        metric_logs = [r for r in caplog.records if "METRIC" in r.message]
        assert len(metric_logs) >= 1

        json_str = metric_logs[0].message.replace("METRIC ", "")
        data = json.loads(json_str)
        assert data["metric_name"] == "tool_query_db_latency_ms"
        assert data["value"] >= 10.0

    def test_emits_error_metric_on_failure(self, caplog):
        """Verify traced_tool emits error metric when tool raises."""

        @traced_tool("query_db")
        def failing_tool(sql: str) -> str:
            raise TimeoutError("too slow")

        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            with pytest.raises(TimeoutError):
                failing_tool("SELECT *")

        error_logs = [r for r in caplog.records if "agent_error" in r.message]
        assert len(error_logs) >= 1

        json_str = error_logs[0].message.replace("METRIC ", "")
        data = json.loads(json_str)
        assert data["error_type"] == "TimeoutError"

    def test_preserves_function_metadata(self):
        """Verify traced_tool preserves original function name and docstring."""

        @traced_tool("my_tool")
        def original_function():
            """Original docstring."""
            pass

        assert original_function.__name__ == "original_function"
        assert original_function.__doc__ == "Original docstring."


class TestRequestTracer:
    """Tests for RequestTracer end-to-end tracking."""

    def test_complete_emits_e2e_latency(self, caplog):
        """Verify RequestTracer emits e2e latency on success."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            tracer = RequestTracer(apm_id="APM_010", session_id="sess-001")
            tracer.start()
            time.sleep(0.01)
            tracer.complete(success=True, retries=0)

        metric_logs = [r for r in caplog.records if "METRIC" in r.message and "agent_e2e" in r.message]
        assert len(metric_logs) >= 1

        json_str = metric_logs[0].message.replace("METRIC ", "")
        data = json.loads(json_str)
        assert data["metric_name"] == "agent_e2e_latency_ms"
        assert data["value"] >= 10.0
        assert data["apm_id"] == "APM_010"
        assert data["success"] is True

    def test_complete_with_retries_emits_retry_metric(self, caplog):
        """Verify retry metric is emitted when retries > 0."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            tracer = RequestTracer(apm_id="APM_011", session_id="sess-002")
            tracer.start()
            tracer.complete(success=True, retries=2)

        metric_logs = [r for r in caplog.records if "agent_retries" in r.message]
        assert len(metric_logs) >= 1

        json_str = metric_logs[0].message.replace("METRIC ", "")
        data = json.loads(json_str)
        assert data["metric_name"] == "agent_retries"
        assert data["value"] == 2

    def test_fail_emits_error_and_latency(self, caplog):
        """Verify RequestTracer emits both error and latency on failure."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            tracer = RequestTracer(apm_id="APM_012", session_id="sess-003")
            tracer.start()
            tracer.fail(error=TimeoutError("query too slow"), retries=1)

        # Check e2e latency was emitted
        e2e_logs = [r for r in caplog.records if "agent_e2e" in r.message]
        assert len(e2e_logs) >= 1

        # Check error metric was emitted
        error_logs = [r for r in caplog.records if "agent_error" in r.message]
        assert len(error_logs) >= 1

        json_str = error_logs[0].message.replace("METRIC ", "")
        data = json.loads(json_str)
        assert data["error_type"] == "TimeoutError"
        assert data["apm_id"] == "APM_012"

    def test_fail_includes_error_type_in_span(self, caplog):
        """Verify error type and message are recorded for trace spans."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            tracer = RequestTracer(apm_id="APM_013", session_id="sess-004")
            tracer.start()
            tracer.fail(error=RuntimeError("SQL syntax error"), retries=2)

        error_logs = [r for r in caplog.records if "agent_error" in r.message]
        json_str = error_logs[0].message.replace("METRIC ", "")
        data = json.loads(json_str)
        assert data["error_type"] == "RuntimeError"
        assert "SQL syntax error" in data["error_message"]

    def test_no_retry_metric_when_zero_retries(self, caplog):
        """Verify no retry metric is emitted when retries=0."""
        with caplog.at_level(logging.INFO, logger="agentcore.observability"):
            tracer = RequestTracer(apm_id="APM_014", session_id="sess-005")
            tracer.start()
            tracer.complete(success=True, retries=0)

        retry_logs = [r for r in caplog.records if "agent_retries" in r.message]
        assert len(retry_logs) == 0
