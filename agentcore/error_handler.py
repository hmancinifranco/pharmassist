"""
ErrorHandler — Centralized error handling for the Unified Agent.

Provides a single point of control for:
1. Mapping exceptions to user-friendly Spanish messages
2. Logging full error details to CloudWatch (stack traces, context)
3. Sanitizing error messages to never expose infrastructure details
4. Determining retry eligibility per error type
5. Detecting memory subsystem errors (graceful degradation)

Security rules enforced:
- Strip hostnames matching *.rds.amazonaws.com
- Strip IP addresses (IPv4/IPv6)
- Strip connection strings (postgresql://...)
- Strip ARNs (arn:aws:...)
- Strip stack traces from user-facing messages
- Truncate messages > 200 chars

Requirements: 4.5, 16.4, 17.5, 20.1, 20.2, 20.3, 20.4, 20.5
"""

import logging
import re
import traceback
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — User-facing messages (Spanish AR)
# ---------------------------------------------------------------------------

MSG_AURORA_UNREACHABLE = (
    "El sistema de datos no está disponible. Intentá en unos minutos."
)
MSG_BEDROCK_THROTTLED = (
    "El asistente está ocupado. Intentá en unos segundos."
)
MSG_BEDROCK_STREAM_ERROR = (
    "Ocurrió un error con el modelo. Intentá de nuevo."
)
MSG_SQL_TIMEOUT = (
    "La consulta fue demasiado compleja. Intentá una pregunta más específica."
)
MSG_SQL_VALIDATION = (
    "Solo tengo acceso de lectura a la base de datos."
)
MSG_GENERIC_ERROR = (
    "Ocurrió un error inesperado. Intentá de nuevo."
)

# Maximum length for user-facing messages
MAX_MESSAGE_LENGTH = 200

# ---------------------------------------------------------------------------
# Regex patterns for sanitization
# ---------------------------------------------------------------------------

# RDS hostnames: anything.rds.amazonaws.com or *.cluster-*.region.rds.amazonaws.com
_RE_RDS_HOSTNAME = re.compile(
    r"[a-zA-Z0-9\-_.]+\.rds\.amazonaws\.com[:\d]*",
    re.IGNORECASE,
)

# IPv4 addresses (e.g., 10.0.1.42, 192.168.0.1)
_RE_IPV4 = re.compile(
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?\b"
)

# IPv6 addresses (simplified match)
_RE_IPV6 = re.compile(
    r"\b[0-9a-fA-F:]{3,39}\b"
)

# Connection strings: postgresql://... , postgres://...
_RE_CONN_STRING = re.compile(
    r"postgres(ql)?://[^\s\"']+",
    re.IGNORECASE,
)

# ARNs: arn:aws:service:region:account:resource
_RE_ARN = re.compile(
    r"arn:aws:[a-zA-Z0-9\-]+:[a-zA-Z0-9\-]*:\d{12}:[^\s\"']+",
)

# Stack trace patterns (File "...", line N)
_RE_STACK_TRACE = re.compile(
    r'File ".*?", line \d+.*',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Error classification helpers
# ---------------------------------------------------------------------------

# Exception messages/types that indicate Aurora connectivity issues
_AURORA_PATTERNS = (
    "connection refused",
    "could not connect",
    "connection timed out",
    "timeout expired",
    "no route to host",
    "network is unreachable",
    "connection reset",
    "broken pipe",
    "server closed the connection",
    "operationalerror",
    "could not translate host name",
    "pg_hba.conf",
    "ssl connection has been closed",
    "connection to server",
)

# Exception messages/types that indicate Bedrock throttling
_BEDROCK_THROTTLE_PATTERNS = (
    "throttlingexception",
    "throttling",
    "rate exceeded",
    "too many requests",
    "serviceunav",
)

# Exception messages/types that indicate Bedrock model stream errors
_BEDROCK_STREAM_PATTERNS = (
    "modelstreamerrorexception",
    "model stream error",
    "internalservererror",
    "modelerrorexception",
)

# Exception messages/types for SQL timeouts
_SQL_TIMEOUT_PATTERNS = (
    "statement_timeout",
    "canceling statement due to statement timeout",
    "query_timeout",
)

# Exception messages/types for memory subsystem
_MEMORY_PATTERNS = (
    "agentcore_memory",
    "memory",
    "memoryclient",
    "memory_id",
    "createevent",
    "retrieveevents",
    "semantic_search",
    "memoryunavailable",
)


def _matches_patterns(error: Exception, patterns: tuple) -> bool:
    """Check if error message or type matches any of the given patterns."""
    error_msg = str(error).lower()
    error_type = type(error).__name__.lower()
    full_text = f"{error_type}: {error_msg}"
    return any(p in full_text for p in patterns)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ErrorHandler:
    """Centralized error handler for the Unified Agent.

    All methods are static — no state needed. Call from any catch block.
    """

    @staticmethod
    def handle(error: Exception, context: str = "") -> dict:
        """Map an exception to a safe user-facing response.

        Logs the full error detail (including stack trace) to CloudWatch,
        then returns a sanitized, user-friendly message. Never exposes
        hostnames, IPs, connection strings, ARNs, or stack traces.

        Args:
            error: The caught exception.
            context: Optional context string for logging (e.g., "query_db",
                     "memory_retrieval"). Used in log messages only.

        Returns:
            {"result": str, "structured": {}, "success": False, "retries": int}
        """
        # Log full error to CloudWatch (internal only)
        logger.error(
            "ErrorHandler [%s]: %s: %s\n%s",
            context or "unknown",
            type(error).__name__,
            str(error),
            traceback.format_exc(),
        )

        # Determine user-facing message based on error type
        message = ErrorHandler._classify_error(error)

        return {
            "result": message,
            "structured": {},
            "success": False,
            "retries": 0,
        }

    @staticmethod
    def is_retryable(error: Exception) -> bool:
        """Determine if an error should trigger a retry.

        Non-retryable errors:
        - ValueError (SQL validation / user intent cannot be fulfilled)
        - Aurora connection errors (infrastructure issue, retrying won't help)

        Retryable errors:
        - Bedrock throttling (transient, back-off helps)
        - Bedrock model stream errors (transient)
        - SQL timeouts (can simplify query on retry)
        - RuntimeError (SQL syntax — LLM can self-correct)
        - Generic/unknown exceptions (worth one more try)

        Args:
            error: The caught exception.

        Returns:
            True if the error is worth retrying, False otherwise.
        """
        # ValueError: SQL validation rejection — never retry
        if isinstance(error, ValueError):
            return False

        # Aurora unreachable — infrastructure issue, retry won't help
        if _matches_patterns(error, _AURORA_PATTERNS):
            return False

        # Memory errors — not retryable (proceed without memory instead)
        if ErrorHandler.is_memory_error(error):
            return False

        # Bedrock throttling — retryable (transient)
        if _matches_patterns(error, _BEDROCK_THROTTLE_PATTERNS):
            return True

        # Bedrock stream errors — retryable (transient)
        if _matches_patterns(error, _BEDROCK_STREAM_PATTERNS):
            return True

        # SQL timeout — retryable (can simplify query)
        if isinstance(error, TimeoutError) or _matches_patterns(error, _SQL_TIMEOUT_PATTERNS):
            return True

        # RuntimeError — retryable (SQL syntax, LLM can self-correct)
        if isinstance(error, RuntimeError):
            return True

        # Default: retryable (generic errors worth one more try)
        return True

    @staticmethod
    def is_memory_error(error: Exception) -> bool:
        """Check if an error is from the memory subsystem.

        Memory errors trigger graceful degradation: the agent proceeds
        without memory context rather than failing the request.

        Args:
            error: The caught exception.

        Returns:
            True if the error originates from the memory subsystem.
        """
        return _matches_patterns(error, _MEMORY_PATTERNS)

    @staticmethod
    def sanitize_message(message: str) -> str:
        """Remove sensitive information from a message string.

        Strips:
        - RDS hostnames (*.rds.amazonaws.com)
        - IP addresses (IPv4)
        - Connection strings (postgresql://...)
        - ARNs (arn:aws:...)
        - Stack trace fragments

        Truncates to MAX_MESSAGE_LENGTH chars.

        Args:
            message: Raw error message that may contain sensitive data.

        Returns:
            Sanitized message safe for user display.
        """
        sanitized = message

        # Strip connection strings first (most specific)
        sanitized = _RE_CONN_STRING.sub("[conexión oculta]", sanitized)

        # Strip ARNs
        sanitized = _RE_ARN.sub("[recurso oculto]", sanitized)

        # Strip RDS hostnames
        sanitized = _RE_RDS_HOSTNAME.sub("[host oculto]", sanitized)

        # Strip IPv4 addresses
        sanitized = _RE_IPV4.sub("[IP oculta]", sanitized)

        # Strip stack traces
        sanitized = _RE_STACK_TRACE.sub("", sanitized)

        # Truncate
        if len(sanitized) > MAX_MESSAGE_LENGTH:
            sanitized = sanitized[:MAX_MESSAGE_LENGTH - 3] + "..."

        return sanitized.strip()

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _classify_error(error: Exception) -> str:
        """Classify an error and return the appropriate user-facing message."""
        # Aurora connectivity issues
        if _matches_patterns(error, _AURORA_PATTERNS):
            return MSG_AURORA_UNREACHABLE

        # Bedrock throttling
        if _matches_patterns(error, _BEDROCK_THROTTLE_PATTERNS):
            return MSG_BEDROCK_THROTTLED

        # Bedrock model stream errors
        if _matches_patterns(error, _BEDROCK_STREAM_PATTERNS):
            return MSG_BEDROCK_STREAM_ERROR

        # SQL timeout
        if isinstance(error, TimeoutError) or _matches_patterns(error, _SQL_TIMEOUT_PATTERNS):
            return MSG_SQL_TIMEOUT

        # SQL validation (ValueError from query_db)
        if isinstance(error, ValueError):
            return MSG_SQL_VALIDATION

        # Memory errors — should not reach user, but if they do, use generic
        if ErrorHandler.is_memory_error(error):
            return MSG_GENERIC_ERROR

        # Default: generic error message
        return MSG_GENERIC_ERROR
