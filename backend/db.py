"""backend/db.py — Connection pool para Aurora PostgreSQL.

Encapsula la conexión a Aurora PostgreSQL usando psycopg2 con
ThreadedConnectionPool. Credenciales obtenidas de AWS Secrets Manager.
SSL/TLS obligatorio con CA bundle de RDS.

Diseñado para ser importado por los endpoints del dashboard (FastAPI).
El pool se inicializa de forma lazy (no al import) para permitir que
el backend arranque sin Aurora configurada (desarrollo local, fallback).

Exports:
    get_connection() -> ContextManager[psycopg2.connection]
    get_pool() -> psycopg2.pool.ThreadedConnectionPool
    close_pool() -> None
"""

import json
import logging
import os
from contextlib import contextmanager
from typing import Generator

import boto3
import psycopg2
from psycopg2 import pool

logger = logging.getLogger(__name__)

_pool: pool.ThreadedConnectionPool | None = None


def _get_secret() -> dict:
    """Fetch DB credentials from AWS Secrets Manager.

    Reads DB_SECRET_ARN from environment. Raises a clear error if not set.

    Returns:
        dict with keys: host, port, username, password, dbname.

    Raises:
        RuntimeError: If DB_SECRET_ARN is not configured.
        Exception: If Secrets Manager call fails (propagated).
    """
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not secret_arn:
        raise RuntimeError(
            "DB_SECRET_ARN no está configurado. "
            "No se puede inicializar el pool de conexiones a Aurora."
        )

    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)

    logger.info("Obteniendo credenciales de Aurora desde Secrets Manager...")
    response = client.get_secret_value(SecretId=secret_arn)
    return json.loads(response["SecretString"])


def _resolve_ca_bundle() -> str:
    """Resolve the path to the RDS CA bundle.

    Priority:
    1. RDS_CA_BUNDLE env var (explicit path)
    2. rds-ca-bundle.pem in the same directory as this file
    3. Falls back to the filename only (psycopg2 will look in default paths)

    Returns:
        Path string to use as sslrootcert.
    """
    # Explicit env var
    env_path = os.environ.get("RDS_CA_BUNDLE")
    if env_path and os.path.exists(env_path):
        return env_path

    # Bundled alongside this module
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rds-ca-bundle.pem")
    if os.path.exists(local_path):
        return local_path

    # Fallback — log warning, return default name
    logger.warning(
        "RDS CA bundle no encontrado. Se usará 'rds-ca-bundle.pem' como nombre. "
        "La conexión SSL podría fallar si el archivo no está en el path de búsqueda."
    )
    return "rds-ca-bundle.pem"


def _init_pool() -> pool.ThreadedConnectionPool:
    """Initialize psycopg2 ThreadedConnectionPool.

    Pool config:
    - minconn=2: Mantiene 2 conexiones abiertas como baseline
    - maxconn=10: Escala hasta 10 conexiones concurrentes
    - sslmode=require: TLS obligatorio
    - connect_timeout=5: Falla rápido si Aurora no responde

    Returns:
        ThreadedConnectionPool instance ready to use.

    Raises:
        RuntimeError: If DB_SECRET_ARN is not configured.
        psycopg2.OperationalError: If connection to Aurora fails.
    """
    secret = _get_secret()
    ca_bundle = _resolve_ca_bundle()

    logger.info(
        "Inicializando pool de conexiones a Aurora (host=%s, dbname=%s, minconn=2, maxconn=10)",
        secret.get("host", "unknown"),
        secret.get("dbname", "unknown"),
    )

    return pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        host=secret["host"],
        port=secret.get("port", 5432),
        dbname=secret["dbname"],
        user=secret["username"],
        password=secret["password"],
        sslmode="require",
        sslrootcert=ca_bundle,
        connect_timeout=5,
    )


def get_pool() -> pool.ThreadedConnectionPool:
    """Get or create the connection pool (singleton).

    Lazy initialization — the pool is not created until the first call.
    If the pool was closed (via close_pool()), it will be re-created.

    Returns:
        Active ThreadedConnectionPool instance.

    Raises:
        RuntimeError: If DB_SECRET_ARN is not configured.
        psycopg2.OperationalError: If connection to Aurora fails.
    """
    global _pool
    if _pool is None or _pool.closed:
        _pool = _init_pool()
    return _pool


@contextmanager
def get_connection() -> Generator:
    """Context manager that gets a connection from the pool and returns it.

    Usage:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT ...", (param,))
                rows = cur.fetchall()

    The connection is automatically returned to the pool when the
    context exits (even if an exception occurs).

    Yields:
        psycopg2 connection object.

    Raises:
        RuntimeError: If DB_SECRET_ARN is not configured.
        psycopg2.OperationalError: If pool is exhausted or connection fails.
    """
    p = get_pool()
    conn = p.getconn()
    try:
        yield conn
    finally:
        p.putconn(conn)


def close_pool() -> None:
    """Close all connections in the pool (clean shutdown).

    Safe to call multiple times. After closing, the next call to
    get_pool() or get_connection() will re-create the pool.
    """
    global _pool
    if _pool is not None and not _pool.closed:
        logger.info("Cerrando pool de conexiones a Aurora...")
        _pool.closeall()
        _pool = None
        logger.info("Pool cerrado correctamente.")
