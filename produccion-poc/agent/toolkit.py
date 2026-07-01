"""
PharmaToolkit — Funciones expuestas al REPL del CodeAgent.

Provee query_db, get_apm_id y get_ciclo_actual_id como funciones
planas accesibles desde el sandbox del strands-code-agent.

Conexión a Aurora PostgreSQL via SQLAlchemy + pg8000 (pure Python).
Credenciales desde AWS Secrets Manager.
SSL/TLS obligatorio. Pool: pool_size=5, max_overflow=2, pool_pre_ping=True.

Requirements: 1.3, 1.4, 1.5, 7.1, 7.5, 8.3, 8.4
"""

import json
import os
import ssl

import boto3
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool


class PharmaToolkit:
    """Toolkit functions exposed to the CodeAgent REPL.

    NOT Strands @tool decorated — these are plain Python functions
    that the CodeAgent calls directly inside its REPL sandbox.
    """

    def __init__(self, apm_id: str | None = None, db_secret_arn: str | None = None):
        self._apm_id = apm_id
        self._db_secret_arn = db_secret_arn or os.environ.get("DB_SECRET_ARN")
        self._engine = None
        self._ciclo_actual_id: int | None = None

    # ─────────────────────────────────────────────────────────────────────
    # Engine (lazy init)
    # ─────────────────────────────────────────────────────────────────────

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
        dbname = creds.get("dbname", "pharmassist_poc")
        url = (
            f"postgresql+pg8000://{creds['username']}:{creds['password']}"
            f"@{creds['host']}:{creds.get('port', 5432)}/{dbname}"
        )

        # Use RDS CA bundle for SSL verification (Requirement 7.5)
        # The bundle is packaged alongside the agent code
        ssl_context = ssl.create_default_context()
        ca_bundle = os.path.join(os.path.dirname(__file__), "rds-ca-bundle.pem")
        if os.path.exists(ca_bundle):
            ssl_context.load_verify_locations(ca_bundle)

        return create_engine(
            url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=2,
            pool_pre_ping=True,
            connect_args={"ssl_context": ssl_context},
        )

    # ─────────────────────────────────────────────────────────────────────
    # Public API — funciones expuestas al REPL
    # ─────────────────────────────────────────────────────────────────────

    def query_db(self, sql: str) -> pd.DataFrame:
        """Execute a read-only SQL query and return a pandas DataFrame.

        Security (Req 7.1):
            Only SELECT and WITH (CTE) statements are allowed.
            INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE are rejected.

        Performance (Req 8.4):
            statement_timeout = 5000ms enforced per query.

        Args:
            sql: A valid SELECT or WITH SQL string.

        Returns:
            pandas DataFrame with query results.

        Raises:
            ValueError: If the SQL is not a SELECT/WITH query.
        """
        normalized = sql.strip().upper()
        if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
            raise ValueError(
                "Solo se permiten queries SELECT o WITH (CTEs). "
                f"Recibido: {normalized[:30]}..."
            )

        with self.engine.connect() as conn:
            # Enforce statement_timeout per query (Req 8.4)
            conn.execute(text("SET LOCAL statement_timeout = '5000'"))
            result = pd.read_sql(text(sql), conn)
        return result

    def get_apm_id(self) -> str:
        """Return the current APM ID for this session.

        The APM_ID is injected at toolkit initialization and represents
        the logged-in APM user.
        """
        if self._apm_id is None:
            raise RuntimeError("APM_ID no inicializado en esta sesión.")
        return self._apm_id

    def get_ciclo_actual_id(self) -> int:
        """Return the current active cycle ID.

        Queries the ciclo table for the cycle where CURRENT_DATE falls
        between inicio and fin. Falls back to the most recent cycle
        by fin date if no active cycle is found.

        Returns:
            Integer ID of the current promotional cycle.
        """
        if self._ciclo_actual_id is None:
            # Try current cycle (date range match)
            df = self.query_db(
                "SELECT id FROM ciclo "
                "WHERE inicio <= CURRENT_DATE AND fin >= CURRENT_DATE "
                "LIMIT 1"
            )
            if not df.empty:
                self._ciclo_actual_id = int(df.iloc[0]["id"])
            else:
                # Fallback: most recent cycle by end date
                df = self.query_db(
                    "SELECT id FROM ciclo ORDER BY fin DESC LIMIT 1"
                )
                if not df.empty:
                    self._ciclo_actual_id = int(df.iloc[0]["id"])
                else:
                    # Ultimate fallback if table is empty
                    self._ciclo_actual_id = 1
        return self._ciclo_actual_id
