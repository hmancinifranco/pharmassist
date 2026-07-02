"""
PharmaToolkit — Tool query_db para el Unified Agent de PharmAssist.

Expone query_db como un Strands @tool que Claude invoca directamente.
Conexión a Aurora PostgreSQL via SQLAlchemy + pg8000 (pure Python).
Credenciales desde AWS Secrets Manager. SSL/TLS obligatorio.
Pool: pool_size=5, max_overflow=2, pool_pre_ping=True.

Output format:
- Texto tabular (max 50 filas) para el LLM
- Metadata JSON estructurada (max 100 filas) como sufijo HTML comment
  para parsing por el frontend (ResponseFormatter)

Requirements: 2.1, 2.2, 2.3, 2.6, 4.1, 4.2, 4.3, 4.4, 16.1, 16.2, 16.3
"""

import json
import logging
import os
import re
import ssl
import time
from typing import Optional

import boto3
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from strands import tool

try:
    from agentcore.observability import emit_metric, emit_error_metric, timed_operation
except ModuleNotFoundError:
    from observability import emit_metric, emit_error_metric, timed_operation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Forbidden SQL patterns — statements that mutate data or schema
# ---------------------------------------------------------------------------

_FORBIDDEN_PREFIXES = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
)

# Max rows for text output (LLM context) and structured metadata (frontend)
_MAX_TEXT_ROWS = 50
_MAX_STRUCTURED_ROWS = 100


# ---------------------------------------------------------------------------
# PharmaToolkit class — manages engine and connection pool
# ---------------------------------------------------------------------------


class PharmaToolkit:
    """Toolkit que gestiona la conexión a Aurora PostgreSQL y ejecuta queries.

    Lazy-initializes the SQLAlchemy engine on first query execution.
    Credentials are fetched from AWS Secrets Manager.
    SSL/TLS is enforced using the RDS CA bundle.
    """

    def __init__(self, db_secret_arn: Optional[str] = None):
        self._db_secret_arn = db_secret_arn or os.environ.get("DB_SECRET_ARN", "")
        self._engine = None

    # -----------------------------------------------------------------
    # Engine (lazy init)
    # -----------------------------------------------------------------

    @property
    def engine(self):
        """SQLAlchemy Engine — lazy initialization with connection pooling."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    def _get_credentials(self) -> dict:
        """Retrieve DB credentials from Secrets Manager.

        The secret must contain keys: host, port, username, password, dbname.
        """
        if not self._db_secret_arn:
            raise RuntimeError(
                "DB_SECRET_ARN no configurado. No se puede conectar a la base de datos."
            )

        region = os.environ.get("AWS_REGION", "us-east-1")
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=self._db_secret_arn)
        return json.loads(response["SecretString"])

    def _create_engine(self):
        """Create SQLAlchemy engine with pool and SSL/TLS.

        - Driver: pg8000 (pure Python, no libpq dependency)
        - Pool: QueuePool with pool_size=5, max_overflow=2
        - pool_pre_ping=True for connection health checks
        - SSL/TLS enforced via ssl_context with RDS CA bundle
        """
        creds = self._get_credentials()
        dbname = creds.get("dbname", "pharmassist")
        url = (
            f"postgresql+pg8000://{creds['username']}:{creds['password']}"
            f"@{creds['host']}:{creds.get('port', 5432)}/{dbname}"
        )

        # Use RDS CA bundle for SSL verification
        # The bundle should be packaged alongside the agent code
        ssl_context = ssl.create_default_context()
        ca_bundle = os.path.join(os.path.dirname(__file__), "rds-ca-bundle.pem")
        if os.path.exists(ca_bundle):
            ssl_context.load_verify_locations(ca_bundle)
        else:
            logger.warning(
                "RDS CA bundle no encontrado en %s. Usando verificación por defecto.",
                ca_bundle,
            )

        return create_engine(
            url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=2,
            pool_pre_ping=True,
            connect_args={"ssl_context": ssl_context},
        )

    # -----------------------------------------------------------------
    # SQL Validation
    # -----------------------------------------------------------------

    def _validate_sql(self, sql: str) -> str:
        """Validate and normalize SQL statement.

        Rules:
        - Strip whitespace
        - Only allow SELECT or WITH (case-insensitive)
        - Reject INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE
        - Reject semicolons mid-query (prevent multi-statement injection)

        Args:
            sql: Raw SQL string from the LLM.

        Returns:
            Normalized SQL string.

        Raises:
            ValueError: If SQL is not a valid read-only statement.
        """
        normalized = sql.strip()

        if not normalized:
            raise ValueError("La query SQL está vacía.")

        # Check for semicolons (multi-statement injection prevention)
        # Allow trailing semicolons but reject any semicolons before the end
        sql_without_trailing = normalized.rstrip(";").strip()
        if ";" in sql_without_trailing:
            raise ValueError(
                "La query contiene múltiples sentencias (';' encontrado). "
                "Solo se permite una sentencia SQL a la vez."
            )

        # Check first keyword
        upper = normalized.upper().lstrip()
        if not (upper.startswith("SELECT") or upper.startswith("WITH")):
            # Check if it starts with a forbidden keyword
            first_word = re.split(r"\s", upper, maxsplit=1)[0]
            if first_word in _FORBIDDEN_PREFIXES:
                raise ValueError(
                    f"Operación '{first_word}' no permitida. "
                    "Solo se permiten queries SELECT o WITH (CTEs)."
                )
            raise ValueError(
                "Solo se permiten queries SELECT o WITH (CTEs). "
                f"Recibido: {normalized[:50]}..."
            )

        return normalized

    # -----------------------------------------------------------------
    # Query execution
    # -----------------------------------------------------------------

    def execute_query(self, sql: str) -> str:
        """Execute a validated read-only SQL query and format the result.

        Validates the SQL, executes with a 5-second timeout, and returns:
        - Markdown table (max 50 rows) for the LLM
        - Structured JSON metadata (max 100 rows) as HTML comment suffix
          for the frontend ResponseFormatter

        Args:
            sql: SQL query string (SELECT or WITH).

        Returns:
            Formatted string with text table + structured metadata.

        Raises:
            ValueError: If SQL is invalid.
            Exception: If database execution fails (propagated with safe message).
        """
        validated_sql = self._validate_sql(sql)

        start_time = time.perf_counter()
        try:
            with self.engine.connect() as conn:
                # Enforce statement_timeout per query (5 seconds)
                conn.execute(text("SET LOCAL statement_timeout = '5000'"))
                df = pd.read_sql(text(validated_sql), conn)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_msg = str(e)
            logger.error("Error ejecutando query SQL: %s", error_msg)

            # Emit query_db error metric with timing
            emit_metric(
                "tool_query_db_latency_ms",
                duration_ms,
                unit="ms",
                success=False,
            )
            emit_error_metric(
                error_type=type(e).__name__,
                error_message=self._safe_error_message(error_msg),
                context="query_db",
            )

            # Check for timeout
            if "statement timeout" in error_msg.lower() or "canceling statement" in error_msg.lower():
                raise TimeoutError(
                    "La query excedió el tiempo límite de 5 segundos. "
                    "Intentá simplificar la consulta o agregar filtros."
                ) from e

            # Re-raise with safe message (no connection details)
            raise RuntimeError(
                f"Error al ejecutar la query: {self._safe_error_message(error_msg)}"
            ) from e

        # Emit successful query_db latency metric
        duration_ms = (time.perf_counter() - start_time) * 1000
        emit_metric(
            "tool_query_db_latency_ms",
            duration_ms,
            unit="ms",
            success=True,
            rows_returned=len(df),
        )

        return self._format_result(df)

    # -----------------------------------------------------------------
    # Output formatting
    # -----------------------------------------------------------------

    def _format_result(self, df: pd.DataFrame) -> str:
        """Format DataFrame as text table + structured JSON metadata.

        Text output: Markdown table with max 50 rows.
        Structured metadata: JSON with max 100 rows, appended as HTML comment.

        Args:
            df: pandas DataFrame with query results.

        Returns:
            Formatted string: text table + structured metadata suffix.
        """
        total_rows = len(df)
        columns = df.columns.tolist()

        # --- Text output (max 50 rows for LLM context) ---
        text_df = df.head(_MAX_TEXT_ROWS)
        text_output = self._dataframe_to_markdown(text_df)

        if total_rows > _MAX_TEXT_ROWS:
            text_output += f"\n\nMostrando {_MAX_TEXT_ROWS} de {total_rows} filas totales."
        elif total_rows == 0:
            text_output = "La query no devolvió resultados."

        # --- Structured metadata (max 100 rows for frontend rendering) ---
        structured_df = df.head(_MAX_STRUCTURED_ROWS)
        rows_data = structured_df.to_dict(orient="records")

        # Convert non-serializable types to strings
        for row in rows_data:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None
                elif not isinstance(value, (str, int, float, bool, type(None))):
                    row[key] = str(value)

        structured_metadata = {
            "columns": columns,
            "rows": rows_data,
            "total_rows": total_rows,
            "truncated": total_rows > _MAX_STRUCTURED_ROWS,
        }

        # Append structured metadata as HTML comment (parsed by ResponseFormatter)
        metadata_json = json.dumps(structured_metadata, ensure_ascii=False, default=str)
        structured_suffix = f"\n\n<!--STRUCTURED:{metadata_json}-->"

        return text_output + structured_suffix

    def _dataframe_to_markdown(self, df: pd.DataFrame) -> str:
        """Convert a DataFrame to a Markdown table string.

        Args:
            df: pandas DataFrame to convert.

        Returns:
            Markdown table string.
        """
        if df.empty:
            return ""

        columns = df.columns.tolist()

        # Header
        header = "| " + " | ".join(str(col) for col in columns) + " |"
        separator = "|" + "|".join("------" for _ in columns) + "|"

        # Rows
        rows = []
        for _, row in df.iterrows():
            row_str = "| " + " | ".join(
                str(val) if not pd.isna(val) else "" for val in row
            ) + " |"
            rows.append(row_str)

        return "\n".join([header, separator] + rows)

    def _safe_error_message(self, error: str) -> str:
        """Sanitize error message to avoid leaking sensitive info.

        Removes hostnames, IPs, connection strings, credentials.

        Args:
            error: Raw error message string.

        Returns:
            Sanitized error message safe for user display.
        """
        # Remove anything that looks like a connection string
        sanitized = re.sub(
            r"postgresql\+?\w*://[^\s]+", "[conexión oculta]", error
        )
        # Remove IP addresses
        sanitized = re.sub(
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "[host oculto]", sanitized
        )
        # Remove hostnames that look like RDS endpoints
        sanitized = re.sub(
            r"[\w\-]+\.[\w\-]+\.[\w\-]+\.rds\.amazonaws\.com",
            "[host oculto]",
            sanitized,
        )
        # Remove port patterns following hosts
        sanitized = re.sub(r":\d{4,5}", "", sanitized)

        # Truncate if too long
        if len(sanitized) > 200:
            sanitized = sanitized[:200] + "..."

        return sanitized


# ---------------------------------------------------------------------------
# Module-level toolkit instance (lazy initialized)
# ---------------------------------------------------------------------------

_toolkit: Optional[PharmaToolkit] = None


def _get_toolkit() -> PharmaToolkit:
    """Get or create the singleton PharmaToolkit instance."""
    global _toolkit
    if _toolkit is None:
        _toolkit = PharmaToolkit()
    return _toolkit


# ---------------------------------------------------------------------------
# Strands @tool function — invoked by Claude
# ---------------------------------------------------------------------------


@tool
def query_db(sql: str) -> str:
    """Ejecuta una query SQL SELECT contra la base de datos PostgreSQL del laboratorio.

    Solo acepta queries SELECT y WITH (CTEs). Rechaza INSERT/UPDATE/DELETE/DROP/ALTER/CREATE.
    Timeout: 5 segundos. Máximo 50 filas en texto, 100 filas en metadata estructurada.

    Usá esta herramienta para cualquier consulta de datos: prescripciones, médicos,
    visitas, ventas, cartera, productos, zonas, etc.

    Args:
        sql: Query SQL válida (SELECT o WITH).

    Returns:
        Resultado tabular como texto + metadata JSON para el frontend.
    """
    toolkit = _get_toolkit()
    return toolkit.execute_query(sql)
