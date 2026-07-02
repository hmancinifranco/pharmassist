"""
Unit tests for agentcore.error_handler.ErrorHandler.

Tests cover:
- Error classification (Aurora, Bedrock, SQL, memory, generic)
- Retryable vs non-retryable determination
- Memory error detection for graceful degradation
- Message sanitization (hostnames, IPs, ARNs, connection strings)
- Message truncation to 200 chars
- handle() returns correct response structure

Requirements: 4.5, 16.4, 17.5, 20.1, 20.2, 20.3, 20.4, 20.5
"""

import sys
import os

# Ensure agentcore is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentcore.error_handler import (
    ErrorHandler,
    MSG_AURORA_UNREACHABLE,
    MSG_BEDROCK_THROTTLED,
    MSG_BEDROCK_STREAM_ERROR,
    MSG_SQL_TIMEOUT,
    MSG_SQL_VALIDATION,
    MSG_GENERIC_ERROR,
    MAX_MESSAGE_LENGTH,
)


# ---------------------------------------------------------------------------
# Test ErrorHandler.handle() — response structure
# ---------------------------------------------------------------------------


class TestHandle:
    """Tests for ErrorHandler.handle()."""

    def test_handle_returns_dict_with_required_keys(self):
        error = Exception("something went wrong")
        result = ErrorHandler.handle(error, context="test")
        assert isinstance(result, dict)
        assert "result" in result
        assert "structured" in result
        assert "success" in result
        assert "retries" in result

    def test_handle_success_is_false(self):
        error = Exception("fail")
        result = ErrorHandler.handle(error)
        assert result["success"] is False

    def test_handle_structured_is_empty_dict(self):
        error = Exception("fail")
        result = ErrorHandler.handle(error)
        assert result["structured"] == {}

    def test_handle_aurora_connection_refused(self):
        error = OSError("connection refused to host")
        result = ErrorHandler.handle(error, context="query_db")
        assert result["result"] == MSG_AURORA_UNREACHABLE

    def test_handle_aurora_timeout(self):
        error = OSError("connection timed out while connecting to db")
        result = ErrorHandler.handle(error)
        assert result["result"] == MSG_AURORA_UNREACHABLE

    def test_handle_bedrock_throttling(self):
        error = Exception("ThrottlingException: Rate exceeded")
        result = ErrorHandler.handle(error)
        assert result["result"] == MSG_BEDROCK_THROTTLED

    def test_handle_bedrock_stream_error(self):
        error = Exception("ModelStreamErrorException: stream interrupted")
        result = ErrorHandler.handle(error)
        assert result["result"] == MSG_BEDROCK_STREAM_ERROR

    def test_handle_sql_timeout(self):
        error = TimeoutError("canceling statement due to statement timeout")
        result = ErrorHandler.handle(error)
        assert result["result"] == MSG_SQL_TIMEOUT

    def test_handle_value_error_sql_validation(self):
        error = ValueError("SQL must start with SELECT")
        result = ErrorHandler.handle(error)
        assert result["result"] == MSG_SQL_VALIDATION

    def test_handle_generic_error(self):
        error = Exception("something completely unexpected")
        result = ErrorHandler.handle(error)
        assert result["result"] == MSG_GENERIC_ERROR


# ---------------------------------------------------------------------------
# Test ErrorHandler.is_retryable()
# ---------------------------------------------------------------------------


class TestIsRetryable:
    """Tests for ErrorHandler.is_retryable()."""

    def test_value_error_not_retryable(self):
        error = ValueError("INSERT not allowed")
        assert ErrorHandler.is_retryable(error) is False

    def test_aurora_connection_not_retryable(self):
        error = OSError("connection refused")
        assert ErrorHandler.is_retryable(error) is False

    def test_aurora_timeout_not_retryable(self):
        error = OSError("connection timed out")
        assert ErrorHandler.is_retryable(error) is False

    def test_bedrock_throttling_retryable(self):
        error = Exception("ThrottlingException: too many requests")
        assert ErrorHandler.is_retryable(error) is True

    def test_bedrock_stream_error_retryable(self):
        error = Exception("ModelStreamErrorException: internal")
        assert ErrorHandler.is_retryable(error) is True

    def test_sql_timeout_retryable(self):
        error = TimeoutError("statement_timeout exceeded")
        assert ErrorHandler.is_retryable(error) is True

    def test_runtime_error_retryable(self):
        error = RuntimeError("column 'xyz' does not exist")
        assert ErrorHandler.is_retryable(error) is True

    def test_generic_exception_retryable(self):
        error = Exception("unexpected failure")
        assert ErrorHandler.is_retryable(error) is True

    def test_memory_error_not_retryable(self):
        error = Exception("AgentCore_Memory unavailable")
        assert ErrorHandler.is_retryable(error) is False


# ---------------------------------------------------------------------------
# Test ErrorHandler.is_memory_error()
# ---------------------------------------------------------------------------


class TestIsMemoryError:
    """Tests for ErrorHandler.is_memory_error()."""

    def test_memory_keyword_detected(self):
        error = Exception("AgentCore_Memory service is down")
        assert ErrorHandler.is_memory_error(error) is True

    def test_memory_client_detected(self):
        error = Exception("MemoryClient connection failed")
        assert ErrorHandler.is_memory_error(error) is True

    def test_semantic_search_detected(self):
        error = Exception("semantic_search timed out")
        assert ErrorHandler.is_memory_error(error) is True

    def test_create_event_detected(self):
        error = Exception("CreateEvent failed for session")
        assert ErrorHandler.is_memory_error(error) is True

    def test_non_memory_error_not_detected(self):
        error = Exception("column 'nombre' does not exist")
        assert ErrorHandler.is_memory_error(error) is False

    def test_bedrock_error_not_memory(self):
        error = Exception("ThrottlingException from Bedrock")
        assert ErrorHandler.is_memory_error(error) is False


# ---------------------------------------------------------------------------
# Test ErrorHandler.sanitize_message()
# ---------------------------------------------------------------------------


class TestSanitizeMessage:
    """Tests for ErrorHandler.sanitize_message()."""

    def test_strips_rds_hostname(self):
        msg = "Cannot connect to mydb.cluster-abc123.us-east-1.rds.amazonaws.com:5432"
        result = ErrorHandler.sanitize_message(msg)
        assert "rds.amazonaws.com" not in result
        assert "[host oculto]" in result

    def test_strips_ipv4_address(self):
        msg = "Connection refused to 10.0.1.42:5432"
        result = ErrorHandler.sanitize_message(msg)
        assert "10.0.1.42" not in result
        assert "[IP oculta]" in result

    def test_strips_connection_string(self):
        msg = "Failed: postgresql://admin:secret@myhost.rds.amazonaws.com:5432/pharmdb"
        result = ErrorHandler.sanitize_message(msg)
        assert "postgresql://" not in result
        assert "admin" not in result
        assert "secret" not in result

    def test_strips_arn(self):
        msg = "Access denied for arn:aws:secretsmanager:us-east-1:123456789012:secret:mydb-abc123"
        result = ErrorHandler.sanitize_message(msg)
        assert "arn:aws:" not in result
        assert "123456789012" not in result
        assert "[recurso oculto]" in result

    def test_truncates_long_messages(self):
        msg = "A" * 300
        result = ErrorHandler.sanitize_message(msg)
        assert len(result) <= MAX_MESSAGE_LENGTH

    def test_preserves_short_safe_messages(self):
        msg = "column 'nombre' does not exist"
        result = ErrorHandler.sanitize_message(msg)
        assert result == msg

    def test_strips_stack_trace(self):
        msg = 'Error occurred\nFile "/app/agent.py", line 42, in handle\n    raise ValueError("bad")'
        result = ErrorHandler.sanitize_message(msg)
        assert 'File "' not in result
        assert "line 42" not in result

    def test_empty_message(self):
        result = ErrorHandler.sanitize_message("")
        assert result == ""

    def test_combined_sensitive_data(self):
        msg = (
            "OperationalError: could not connect to "
            "postgresql://user:pass@mydb.cluster-x.us-east-1.rds.amazonaws.com:5432/db "
            "from 192.168.1.100 using arn:aws:rds:us-east-1:123456789012:cluster:mydb"
        )
        result = ErrorHandler.sanitize_message(msg)
        assert "postgresql://" not in result
        assert "rds.amazonaws.com" not in result
        assert "192.168.1.100" not in result
        assert "123456789012" not in result
