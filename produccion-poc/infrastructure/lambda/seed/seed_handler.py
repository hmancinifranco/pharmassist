"""
Seed Data Lambda Handler — PharmAssist POC.

Executes DDL (CREATE TABLE), generates seed data using generators,
bulk-inserts into Aurora PostgreSQL, creates indexes and read-only user,
and returns row counts per table.

Uses pg8000 (pure Python) for DB access — no binary dependencies needed.
Environment variables:
  - DB_SECRET_ARN: Secrets Manager ARN with DB credentials
  - DB_NAME: Database name (default: pharmassist_poc)
"""

import json
import os
import time
import ssl
from pathlib import Path

import boto3
import pg8000

# ---------------------------------------------------------------------------
# Generators (same package)
# ---------------------------------------------------------------------------
from generators import (
    generate_especialidad,
    generate_loyalty_doctor,
    generate_institucion,
    generate_linea,
    generate_ciclo,
    generate_categoria_promocion,
    generate_grilla,
    generate_familia_producto,
    generate_producto,
    generate_apms,
    generate_doctors,
    generate_linea_apm,
    generate_datos_visita,
    generate_cartera_medica,
    generate_agenda,
    generate_agenda_producto,
    generate_ultima_milla_medico,
    generate_ultima_milla_marca,
    generate_ultima_milla_objetivo,
    generate_familia_apx_a_marca_cup,
    generate_detalle_promocion_producto,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE = 10_000  # Rows per INSERT batch (for large tables like UltimaMillaMarca)
DDL_FILE = Path(__file__).parent / "ddl.sql"


# ---------------------------------------------------------------------------
# Helper: get DB credentials from Secrets Manager
# ---------------------------------------------------------------------------


def _get_db_credentials() -> dict:
    """Retrieve DB credentials from Secrets Manager."""
    secret_arn = os.environ["DB_SECRET_ARN"]
    region = os.environ.get("AWS_REGION", "us-east-1")

    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response["SecretString"])

    return {
        "user": secret["username"],
        "password": secret["password"],
        "host": secret.get("host", os.environ.get("DB_HOST", "localhost")),
        "port": int(secret.get("port", 5432)),
        "database": secret.get("dbname", os.environ.get("DB_NAME", "pharmassist_poc")),
    }


# ---------------------------------------------------------------------------
# Helper: connect to PostgreSQL
# ---------------------------------------------------------------------------


def _connect(creds: dict):
    """Create a pg8000 connection with SSL."""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    conn = pg8000.connect(
        user=creds["user"],
        password=creds["password"],
        host=creds["host"],
        port=creds["port"],
        database=creds["database"],
        ssl_context=ssl_context,
    )
    conn.autocommit = True
    return conn


# ---------------------------------------------------------------------------
# Helper: execute DDL statements (split by section)
# ---------------------------------------------------------------------------


def _execute_ddl_tables(conn) -> None:
    """Execute only CREATE TABLE statements from the DDL file."""
    ddl_content = DDL_FILE.read_text(encoding="utf-8")

    # Split DDL into statements and execute only CREATE TABLE / DO blocks
    # Stop before CREATE INDEX section
    lines = ddl_content.split("\n")
    create_section: list[str] = []
    in_index_section = False

    for line in lines:
        # Detect index section start
        if "ÍNDICES DE PERFORMANCE" in line or "CREATE INDEX" in line.upper():
            in_index_section = True
        if in_index_section:
            break
        create_section.append(line)

    # Join and split by semicolons
    sql_text = "\n".join(create_section)
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]

    cursor = conn.cursor()
    for stmt in statements:
        # Skip empty or comment-only statements
        meaningful = [l for l in stmt.split("\n") if l.strip() and not l.strip().startswith("--")]
        if not meaningful:
            continue
        try:
            cursor.execute(stmt + ";")
        except Exception as e:
            print(f"[DDL] Warning executing statement: {e}")
            # Continue — IF NOT EXISTS should handle most cases
    cursor.close()
    print("[DDL] CREATE TABLE statements executed successfully.")


def _execute_ddl_indexes_and_grants(conn) -> None:
    """Execute CREATE INDEX and GRANT statements (post-data-load)."""
    ddl_content = DDL_FILE.read_text(encoding="utf-8")

    lines = ddl_content.split("\n")
    index_section: list[str] = []
    in_index_section = False

    for line in lines:
        if "ÍNDICES DE PERFORMANCE" in line:
            in_index_section = True
        if in_index_section:
            index_section.append(line)

    sql_text = "\n".join(index_section)

    # Handle DO $$ blocks specially — they contain semicolons inside
    # Split carefully: find DO $$ ... END $$; blocks first
    # Simple approach: split by ";", rejoin DO blocks
    parts = sql_text.split(";")
    statements: list[str] = []
    buffer = ""
    in_do_block = False

    for part in parts:
        if "DO $$" in part or "DO $" in part:
            in_do_block = True
            buffer = part
        elif in_do_block:
            buffer += ";" + part
            if "END $$" in part or "END $" in part:
                in_do_block = False
                statements.append(buffer.strip())
                buffer = ""
        else:
            if part.strip():
                statements.append(part.strip())

    cursor = conn.cursor()
    for stmt in statements:
        meaningful = [l for l in stmt.split("\n") if l.strip() and not l.strip().startswith("--")]
        if not meaningful:
            continue
        try:
            cursor.execute(stmt + ";")
            print(f"[IDX] OK: {stmt[:60]}...")
        except Exception as e:
            print(f"[IDX] Warning: {e} — stmt: {stmt[:80]}...")
    cursor.close()
    print("[IDX] Indexes and grants executed successfully.")


# ---------------------------------------------------------------------------
# Helper: bulk insert using multi-value INSERT (pg8000 compatible)
# ---------------------------------------------------------------------------


def _bulk_insert(conn, table: str, columns: list[str], rows: list[tuple],
                 batch_size: int = BATCH_SIZE) -> int:
    """
    Insert rows into table using multi-value INSERT statements in batches.

    Builds: INSERT INTO table (col1, col2) VALUES (...), (...), ...
    Uses %s placeholders flattened for pg8000.

    Returns total rows inserted.
    """
    if not rows:
        return 0

    n_cols = len(columns)
    col_list = ", ".join(f'"{c}"' if any(ch.isupper() for ch in c) else c for c in columns)
    total_inserted = 0
    cursor = conn.cursor()

    for batch_start in range(0, len(rows), batch_size):
        batch = rows[batch_start:batch_start + batch_size]

        # Build VALUES clause: (%s, %s, %s), (%s, %s, %s), ...
        placeholders_row = "(" + ", ".join(["%s"] * n_cols) + ")"
        placeholders = ", ".join([placeholders_row] * len(batch))

        # Flatten all values into a single list
        flat_values = []
        for row in batch:
            for val in row:
                flat_values.append(val)

        sql = f'INSERT INTO {table} ({col_list}) VALUES {placeholders}'

        try:
            cursor.execute(sql, flat_values)
            total_inserted += len(batch)
        except Exception as e:
            print(f"[INSERT] Error on {table} batch at offset {batch_start}: {e}")
            # Try row-by-row for this batch to identify bad rows
            for row in batch:
                try:
                    single_sql = f'INSERT INTO {table} ({col_list}) VALUES {placeholders_row}'
                    cursor.execute(single_sql, list(row))
                    total_inserted += 1
                except Exception as row_err:
                    print(f"[INSERT] Skipping row in {table}: {row_err}")

    cursor.close()
    return total_inserted


# ---------------------------------------------------------------------------
# Helper: quote table name (for mixed-case tables like "UltimaMillaMarca")
# ---------------------------------------------------------------------------


def _quote_table(name: str) -> str:
    """Quote table name if it contains uppercase letters."""
    if any(c.isupper() for c in name):
        return f'"{name}"'
    return name


# ---------------------------------------------------------------------------
# Main orchestration: generate and insert all data in dependency order
# ---------------------------------------------------------------------------


def _seed_all_data(conn) -> dict[str, int]:
    """
    Generate and insert all seed data in dependency waves.
    Returns dict of table_name → row_count.
    """
    counts: dict[str, int] = {}

    # =========================================================================
    # WAVE 1: Catálogos sin dependencias
    # =========================================================================
    print("[WAVE 1] Generating catalogs (no dependencies)...")
    t0 = time.time()

    especialidades = generate_especialidad()
    counts["especialidad"] = _bulk_insert(
        conn, "especialidad", ["nombre"], especialidades
    )

    loyalties = generate_loyalty_doctor()
    counts["loyalty_doctor"] = _bulk_insert(
        conn, "loyalty_doctor", ["nombre"], loyalties
    )

    instituciones = generate_institucion()
    counts["institucion"] = _bulk_insert(
        conn, "institucion", ["nombre", "ciudad"], instituciones
    )

    lineas = generate_linea()
    counts["linea"] = _bulk_insert(
        conn, "linea", ["nombre", "descripcion"], lineas
    )

    ciclos = generate_ciclo()
    counts["ciclo"] = _bulk_insert(
        conn, "ciclo", ["nombre", "fecha_inicio", "fecha_fin", "activo"], ciclos
    )

    categorias = generate_categoria_promocion()
    counts["categoria_promocion"] = _bulk_insert(
        conn, "categoria_promocion", ["id", "nombre"], categorias
    )

    print(f"[WAVE 1] Done in {time.time() - t0:.1f}s")

    # =========================================================================
    # WAVE 2: Tablas con dependencia de primer nivel
    # =========================================================================
    print("[WAVE 2] Generating first-level dependents...")
    t0 = time.time()

    grillas = generate_grilla()
    counts["grilla"] = _bulk_insert(
        conn, "grilla", ["id_ciclo", "nombre"], grillas
    )

    familias = generate_familia_producto()
    counts["familia_producto"] = _bulk_insert(
        conn, "familia_producto", ["nombre", "id_linea"], familias
    )

    productos = generate_producto()
    counts["producto"] = _bulk_insert(
        conn, "producto", ["nombre", "id_familia_producto", "id_linea", "activo"], productos
    )

    apms = generate_apms(lineas)
    counts["apm"] = _bulk_insert(
        conn, "apm", ["nombre", "apellido", "email", "id_linea", "activo"], apms
    )

    doctors = generate_doctors(especialidades, loyalties, instituciones)
    counts["doctor"] = _bulk_insert(
        conn, "doctor",
        ["nombre", "apellido", "matricula_nacional", "id_especialidad",
         "id_loyalty", "id_institucion", "email", "telefono", "ciudad", "zona"],
        doctors
    )

    print(f"[WAVE 2] Done in {time.time() - t0:.1f}s")


    # =========================================================================
    # WAVE 3: Tablas de relación y operativas
    # =========================================================================
    print("[WAVE 3] Generating relational tables...")
    t0 = time.time()

    linea_apms = generate_linea_apm(apms, lineas)
    counts["linea_apm"] = _bulk_insert(
        conn, "linea_apm", ["id_apm", "id_linea"], linea_apms
    )

    datos_visita = generate_datos_visita(doctors)
    counts["datos_visita"] = _bulk_insert(
        conn, "datos_visita",
        ["id_doctor", "cadencia", "frecuencia_ideal", "activo"],
        datos_visita
    )

    cartera = generate_cartera_medica(apms, doctors, lineas)
    counts["cartera_medica"] = _bulk_insert(
        conn, "cartera_medica",
        ["id_apm", "id_doctor", "id_linea", "inactivo", "fecha_asignacion"],
        cartera
    )

    print(f"[WAVE 3] Done in {time.time() - t0:.1f}s")

    # =========================================================================
    # WAVE 4: Agenda (150,000 rows)
    # =========================================================================
    print("[WAVE 4] Generating agenda (150K rows)...")
    t0 = time.time()

    agenda = generate_agenda(apms, doctors, ciclos)
    counts["agenda"] = _bulk_insert(
        conn, "agenda",
        ["id_apm", "id_doctor", "fecha", "tipo_visita", "notas", "id_ciclo", "zona"],
        agenda
    )

    print(f"[WAVE 4] Done in {time.time() - t0:.1f}s")

    # =========================================================================
    # WAVE 5: Agenda producto (300,000 rows)
    # =========================================================================
    print("[WAVE 5] Generating agenda_producto (300K rows)...")
    t0 = time.time()

    agenda_productos = generate_agenda_producto(len(agenda), productos)
    counts["agenda_producto"] = _bulk_insert(
        conn, "agenda_producto",
        ["id_agenda", "id_producto", "orden"],
        agenda_productos
    )

    print(f"[WAVE 5] Done in {time.time() - t0:.1f}s")

    # =========================================================================
    # WAVE 6: UltimaMillaMedico (30,000 rows)
    # =========================================================================
    print("[WAVE 6] Generating UltimaMillaMedico (30K rows)...")
    t0 = time.time()

    # Build list of doctor IDs (format "DOC_00001" ... "DOC_30000")
    doctor_ids = [f"DOC_{i+1:05d}" for i in range(len(doctors))]

    um_medicos = generate_ultima_milla_medico(doctor_ids)
    counts["UltimaMillaMedico"] = _bulk_insert(
        conn, _quote_table("UltimaMillaMedico"),
        ["idMedicoCUP", "idMedicoAPX", "IETrim", "ShareTrim", "ShareTrim_1", "ShareMes"],
        um_medicos
    )

    print(f"[WAVE 6] Done in {time.time() - t0:.1f}s")


    # =========================================================================
    # WAVE 7: UltimaMillaMarca (~1.5M rows — chunked generation + insert)
    # =========================================================================
    print("[WAVE 7] Generating UltimaMillaMarca (~1.5M rows) in chunks...")
    t0 = time.time()

    # Build CUP IDs from doctor IDs (same mapping as generate_ultima_milla_medico)
    medico_cup_ids = [f"CUP_DOC_{i+1:05d}" for i in range(len(doctors))]

    # Process in chunks of 1000 doctors at a time to manage memory
    # (1000 doctors × ~50 marcas = ~50K rows per chunk)
    doctor_chunk_size = 1000
    um_marca_total = 0

    for chunk_start in range(0, len(medico_cup_ids), doctor_chunk_size):
        chunk_ids = medico_cup_ids[chunk_start:chunk_start + doctor_chunk_size]
        chunk_rows = generate_ultima_milla_marca(chunk_ids)

        inserted = _bulk_insert(
            conn, _quote_table("UltimaMillaMarca"),
            ["idMedicoCUP", "idMarca", "idMercado", "idLaboratorio",
             "marcaNombre", "ShareMarcaMercado", "ShareMarcaMes",
             "IEMarcaTrim", "ShareMarcaTrim", "ShareMarcaTrim_1"],
            chunk_rows,
            batch_size=BATCH_SIZE,
        )
        um_marca_total += inserted

        if (chunk_start // doctor_chunk_size + 1) % 5 == 0:
            elapsed = time.time() - t0
            progress_pct = (chunk_start + doctor_chunk_size) / len(medico_cup_ids) * 100
            print(f"[WAVE 7] Progress: {progress_pct:.0f}% — {um_marca_total:,} rows — {elapsed:.1f}s")

    counts["UltimaMillaMarca"] = um_marca_total
    print(f"[WAVE 7] Done: {um_marca_total:,} rows in {time.time() - t0:.1f}s")

    # =========================================================================
    # WAVE 8: Tablas finales (UltimaMillaObjetivo, familia_APX, detalle_promo)
    # =========================================================================
    print("[WAVE 8] Generating final tables...")
    t0 = time.time()

    # Build especialidad IDs from the generated DataFrames
    especialidad_ids = [f"ESP_{i+1:03d}" for i in range(len(especialidades))]
    familia_producto_ids = [f"FP_{i+1:02d}" for i in range(len(familias))]
    grilla_ids = [f"GRI_{i+1:02d}" for i in range(len(grillas))]
    categoria_ids = ["1", "2"]
    ciclo_ids = [f"CIC_{i+1:02d}" for i in range(len(ciclos))]

    um_objetivo = generate_ultima_milla_objetivo(especialidad_ids)
    counts["UltimaMillaObjetivoMarcaMercado"] = _bulk_insert(
        conn, _quote_table("UltimaMillaObjetivoMarcaMercado"),
        ["idEspecialidad", "idMarca", "idMercado", "marcaNombre"],
        um_objetivo
    )

    # Generate familia_APX_a_Marca_CUP with valid codMarcaCUP
    # (marca IDs that exist in UltimaMillaMarca — use the pool from the generator)
    marca_cup_ids_valid = [f"MRC_{i+1:03d}" for i in range(80)]
    familia_apx_cup = generate_familia_apx_a_marca_cup(familia_producto_ids, marca_cup_ids_valid)
    counts["familia_APX_a_Marca_CUP"] = _bulk_insert(
        conn, "familia_apx_a_marca_cup",
        ["id_familia_producto_apx", "codMarcaCUP"],
        familia_apx_cup
    )

    detalle_promo = generate_detalle_promocion_producto(
        familia_producto_ids, grilla_ids, categoria_ids, ciclo_ids
    )
    counts["detalle_promocion_producto"] = _bulk_insert(
        conn, "detalle_promocion_producto",
        ["id", "id_familia_producto", "id_grilla", "id_categoria_promocion", "id_ciclo"],
        detalle_promo
    )

    print(f"[WAVE 8] Done in {time.time() - t0:.1f}s")

    return counts


# ---------------------------------------------------------------------------
# Lambda Handler
# ---------------------------------------------------------------------------


def handler(event, context):
    """
    Lambda handler: seeds Aurora PostgreSQL with all PharmAssist POC data.

    Steps:
      1. Get DB credentials from Secrets Manager
      2. Connect to PostgreSQL
      3. Execute DDL (CREATE TABLE only)
      4. Generate and insert seed data in dependency order
      5. Execute indexes and read-only user setup (post-load)
      6. Return counts per table

    Returns:
        dict with statusCode, body (JSON with counts or error)
    """
    total_start = time.time()

    try:
        # Step 1: Get credentials
        print("[HANDLER] Getting DB credentials from Secrets Manager...")
        creds = _get_db_credentials()
        print(f"[HANDLER] Connecting to {creds['host']}:{creds['port']}/{creds['database']}")

        # Step 2: Connect
        conn = _connect(creds)
        print("[HANDLER] Connected to PostgreSQL successfully.")

        # Step 3: Execute DDL (CREATE TABLE only)
        print("[HANDLER] Executing DDL (CREATE TABLE)...")
        _execute_ddl_tables(conn)

        # Step 4: Generate and insert seed data
        print("[HANDLER] Starting seed data generation and insertion...")
        counts = _seed_all_data(conn)

        # Step 5: Create indexes and read-only user (post-load for performance)
        print("[HANDLER] Creating indexes and read-only user...")
        _execute_ddl_indexes_and_grants(conn)

        # Step 6: Close connection
        conn.close()

        total_elapsed = time.time() - total_start
        total_rows = sum(counts.values())

        result = {
            "status": "success",
            "total_rows": total_rows,
            "total_time_seconds": round(total_elapsed, 1),
            "counts": counts,
        }

        print(f"[HANDLER] COMPLETE — {total_rows:,} rows in {total_elapsed:.1f}s")
        print(f"[HANDLER] Counts: {json.dumps(counts, indent=2)}")

        return {
            "statusCode": 200,
            "body": json.dumps(result),
        }

    except Exception as e:
        total_elapsed = time.time() - total_start
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[HANDLER] ERROR after {total_elapsed:.1f}s: {error_msg}")

        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "error": error_msg,
                "elapsed_seconds": round(total_elapsed, 1),
            }),
        }
