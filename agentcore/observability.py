"""
Observability — Traces and metrics for the Unified Agent.

Provides:
1. Timing decorators for tool execution and end-to-end latency
2. Structured metric emission via CloudWatch-compatible JSON logging
3. Error context enrichment for trace spans
4. Integration with OpenTelemetry (when available via AgentCore runtime)

Metrics emitted (structured logging for CloudWatch Logs Insights):
- metric_name=agent_e2e_latency_ms — total request processing time
- metric_name=tool_query_db_latency_ms — SQL execution duration
- metric_name=tool_memory_latency_ms — memory retrieval/store duration
- metric_name=tool_llm_latency_ms — LLM inference duration
- metric_name=agent_error — error type and message on failures
- metric_name=agent_retries — retry count per request

Trace spans include:
- apm_id, session_id as attributes
- tool name and duration
- error.type, error.message on failure

Requirements: 7.1, 7.2, 7.3, 7.4
"""

import functools
import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenTelemetry integration (optional — available when running in AgentCore)
# ---------------------------------------------------------------------------

_tracer = None


def _get_tracer():
    """Get OpenTelemetry tracer if available.

    AgentCore runtime injects OTel SDK when observability is enabled.
    Falls back gracefully to None if not available (local dev).
    """
    global _tracer
    if _tracer is not None:
        return _tracer

    try:
        from opentelemetry import trace
        _tracer = trace.get_tracer("pharmassist-agent", "1.0.0")
    except ImportError:
        _tracer = None

    return _tracer


def _get_current_span():
    """Get the current active OTel span, or None if unavailable."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.is_recording():
            return span
    except (ImportError, Exception):
        pass
    return None


# ---------------------------------------------------------------------------
# Structured metric emission (CloudWatch Logs Insights compatible)
# ---------------------------------------------------------------------------


def emit_metric(
    metric_name: str,
    value: float,
    unit: str = "ms",
    **dimensions: Any,
) -> None:
    """Emit a structured metric via JSON logging.

    Format is compatible with CloudWatch Logs Insights queries:
        filter metric_name = "agent_e2e_latency_ms"
        | stats avg(value), p50(value), p95(value), p99(value)

    Args:
        metric_name: Name of the metric (e.g., "agent_e2e_latency_ms").
        value: Numeric value for the metric.
        unit: Unit of measurement (ms, count, etc.).
        **dimensions: Additional key-value dimensions (apm_id, tool_name, etc.).
    """
    metric_record = {
        "metric_name": metric_name,
        "value": value,
        "unit": unit,
        **dimensions,
    }
    logger.info(
        "METRIC %s",
        json.dumps(metric_record, ensure_ascii=False, default=str),
    )


def emit_error_metric(
    error_type: str,
    error_message: str,
    apm_id: str = "",
    context: str = "",
) -> None:
    """Emit an error metric with type and sanitized message.

    Also enriches the current OTel span with error attributes.

    Args:
        error_type: Exception class name (e.g., "TimeoutError").
        error_message: Sanitized error message (no secrets).
        apm_id: APM identifier for the request.
        context: Additional context (e.g., tool name, operation).
    """
    # Emit structured metric
    metric_record = {
        "metric_name": "agent_error",
        "error_type": error_type,
        "error_message": error_message[:200],  # Truncate for safety
        "apm_id": apm_id,
        "context": context,
    }
    logger.error(
        "METRIC %s",
        json.dumps(metric_record, ensure_ascii=False, default=str),
    )

    # Enrich current OTel span with error info
    span = _get_current_span()
    if span:
        try:
            from opentelemetry.trace import StatusCode
            span.set_status(StatusCode.ERROR, error_message[:200])
            span.set_attribute("error.type", error_type)
            span.set_attribute("error.message", error_message[:200])
            if apm_id:
                span.set_attribute("apm_id", apm_id)
            if context:
                span.set_attribute("error.context", context)
        except Exception:
            pass  # OTel enrichment is best-effort


# ---------------------------------------------------------------------------
# Timing context manager
# ---------------------------------------------------------------------------


@contextmanager
def timed_operation(operation_name: str, **dimensions):
    """Context manager that times an operation and emits a metric.

    Also creates an OTel span if tracing is available.

    Usage:
        with timed_operation("query_db", apm_id="APM_001"):
            result = toolkit.execute_query(sql)

    Args:
        operation_name: Name of the operation (used as metric suffix).
        **dimensions: Additional dimensions to include in the metric.

    Yields:
        A dict where the caller can set 'error' key on failure.
    """
    context = {"error": None}
    tracer = _get_tracer()
    span = None

    # Start OTel span if tracer available
    if tracer:
        try:
            span = tracer.start_span(f"pharmassist.{operation_name}")
            for key, val in dimensions.items():
                span.set_attribute(key, str(val))
        except Exception:
            span = None

    start = time.perf_counter()
    try:
        yield context
    except Exception as e:
        context["error"] = e
        # Record error in span
        if span:
            try:
                from opentelemetry.trace import StatusCode
                span.set_status(StatusCode.ERROR, str(e)[:200])
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e)[:200])
            except Exception:
                pass
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000

        # Emit timing metric
        metric_suffix = _operation_to_metric_name(operation_name)
        emit_metric(metric_suffix, duration_ms, unit="ms", **dimensions)

        # End span
        if span:
            try:
                span.end()
            except Exception:
                pass


def _operation_to_metric_name(operation_name: str) -> str:
    """Map operation name to the standard metric name.

    Args:
        operation_name: Operation identifier.

    Returns:
        CloudWatch metric name.
    """
    mapping = {
        "e2e": "agent_e2e_latency_ms",
        "query_db": "tool_query_db_latency_ms",
        "memory_retrieve": "tool_memory_latency_ms",
        "memory_store": "tool_memory_latency_ms",
        "llm_invoke": "tool_llm_latency_ms",
    }
    return mapping.get(operation_name, f"tool_{operation_name}_latency_ms")


# ---------------------------------------------------------------------------
# Decorator for timing tool functions
# ---------------------------------------------------------------------------


def traced_tool(tool_name: str):
    """Decorator that adds timing and tracing to a tool function.

    Emits a metric with the tool execution time and records
    errors in the trace span.

    Args:
        tool_name: Name of the tool for metric emission.

    Returns:
        Decorated function with timing instrumentation.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = _get_tracer()
            span = None

            if tracer:
                try:
                    span = tracer.start_span(f"tool.{tool_name}")
                    span.set_attribute("tool.name", tool_name)
                except Exception:
                    span = None

            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                # Record error in span and emit error metric
                if span:
                    try:
                        from opentelemetry.trace import StatusCode
                        span.set_status(StatusCode.ERROR, str(e)[:200])
                        span.set_attribute("error.type", type(e).__name__)
                        span.set_attribute("error.message", str(e)[:200])
                    except Exception:
                        pass
                emit_error_metric(
                    error_type=type(e).__name__,
                    error_message=str(e)[:200],
                    context=f"tool_{tool_name}",
                )
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                emit_metric(
                    _operation_to_metric_name(tool_name),
                    duration_ms,
                    unit="ms",
                    tool_name=tool_name,
                )
                if span:
                    try:
                        span.end()
                    except Exception:
                        pass

        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Request-level instrumentation helper
# ---------------------------------------------------------------------------


class RequestTracer:
    """Tracks timing and metadata for a single agent request.

    Creates an end-to-end span and emits the aggregate latency metric
    on completion.

    Usage:
        tracer = RequestTracer(apm_id="APM_001", session_id="sess-123")
        tracer.start()
        # ... process request ...
        tracer.complete(success=True, retries=0)
        # or on error:
        tracer.fail(error=e, retries=1)
    """

    def __init__(self, apm_id: str, session_id: str):
        self.apm_id = apm_id
        self.session_id = session_id
        self._start_time: Optional[float] = None
        self._span = None

    def start(self) -> None:
        """Begin timing the request and open the root span."""
        self._start_time = time.perf_counter()

        tracer = _get_tracer()
        if tracer:
            try:
                self._span = tracer.start_span("agent.handle_invoke")
                self._span.set_attribute("apm_id", self.apm_id)
                self._span.set_attribute("session_id", self.session_id)
            except Exception:
                self._span = None

    def complete(self, success: bool = True, retries: int = 0) -> None:
        """Mark the request as complete and emit metrics.

        Args:
            success: Whether the request completed successfully.
            retries: Number of retries attempted.
        """
        duration_ms = self._elapsed_ms()

        # Emit end-to-end latency
        emit_metric(
            "agent_e2e_latency_ms",
            duration_ms,
            unit="ms",
            apm_id=self.apm_id,
            session_id=self.session_id,
            success=success,
        )

        # Emit retry count
        if retries > 0:
            emit_metric(
                "agent_retries",
                retries,
                unit="count",
                apm_id=self.apm_id,
            )

        # Close span
        if self._span:
            try:
                self._span.set_attribute("retries", retries)
                self._span.set_attribute("success", success)
                self._span.set_attribute("duration_ms", duration_ms)
                self._span.end()
            except Exception:
                pass

        logger.info(
            "Request complete: apm_id=%s, duration_ms=%.1f, success=%s, retries=%d",
            self.apm_id,
            duration_ms,
            success,
            retries,
        )

    def fail(self, error: Exception, retries: int = 0) -> None:
        """Mark the request as failed, emit error metrics.

        Args:
            error: The exception that caused the failure.
            retries: Number of retries attempted.
        """
        duration_ms = self._elapsed_ms()

        # Emit end-to-end latency (even on failure)
        emit_metric(
            "agent_e2e_latency_ms",
            duration_ms,
            unit="ms",
            apm_id=self.apm_id,
            session_id=self.session_id,
            success=False,
        )

        # Emit retry count
        emit_metric(
            "agent_retries",
            retries,
            unit="count",
            apm_id=self.apm_id,
        )

        # Emit error metric
        emit_error_metric(
            error_type=type(error).__name__,
            error_message=str(error)[:200],
            apm_id=self.apm_id,
            context="handle_invoke",
        )

        # Close span with error
        if self._span:
            try:
                from opentelemetry.trace import StatusCode
                self._span.set_status(StatusCode.ERROR, str(error)[:200])
                self._span.set_attribute("error.type", type(error).__name__)
                self._span.set_attribute("error.message", str(error)[:200])
                self._span.set_attribute("retries", retries)
                self._span.set_attribute("success", False)
                self._span.set_attribute("duration_ms", duration_ms)
                self._span.end()
            except Exception:
                pass

    def _elapsed_ms(self) -> float:
        """Calculate elapsed time since start in milliseconds."""
        if self._start_time is None:
            return 0.0
        return (time.perf_counter() - self._start_time) * 1000
