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
import re
import secrets
import time
import ssl
from pathlib import Path

import boto3
import pg8000

# ---------------------------------------------------------------------------
# Generators (same package)
# ---------------------------------------------------------------------------
from generators import (
    # Catálogos (retornan pd.DataFrame)
    generate_especialidades,
    generate_loyalty_doctor,
    generate_instituciones,
    generate_lineas,
    generate_ciclos,
    generate_categorias_promocion,
    generate_grillas,
    generate_familias_producto,
    generate_productos,
    # Entidades (retornan list[tuple])
    generate_apms,
    generate_doctors,
    generate_linea_apm,
    generate_datos_visita,
    generate_cartera_medica,
    # Agenda (retornan list[tuple])
    generate_agenda,
    generate_agenda_producto,
    # UltimaMilla (retornan list[tuple])
    generate_ultima_milla_medico,
    generate_ultima_milla_marca,
    generate_ultima_milla_objetivo,
    generate_familia_apx_a_marca_cup,
    generate_detalle_promocion_producto,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE = 1_000       # Default batch size for INSERTs
BIG_BATCH_SIZE = 5_000   # Batch size for UltimaMillaMarca (1.5M rows)
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
    """Create a pg8000 connection with SSL (optional in VPC)."""
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
# Helper: execute DDL statements (CREATE TABLE only — before data load)
# ---------------------------------------------------------------------------


def _execute_ddl_tables(conn) -> None:
    """Execute only CREATE TABLE statements from the DDL file (stop before indexes)."""
    ddl_content = DDL_FILE.read_text(encoding="utf-8")

    # Split DDL into lines, take everything before the INDEX section
    lines = ddl_content.split("\n")
    create_section: list[str] = []

    for line in lines:
        # Stop at index section or CREATE USER section
        if "ÍNDICES DE PERFORMANCE" in line:
            break
        create_section.append(line)

    sql_text = "\n".join(create_section)
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]

    cursor = conn.cursor()
    for stmt in statements:
        meaningful = [l for l in stmt.split("\n") if l.strip() and not l.strip().startswith("--")]
        if not meaningful:
            continue
        try:
            cursor.execute(stmt + ";")
        except Exception as e:
            print(f"[DDL] Warning: {e}")
    cursor.close()
    print("[DDL] CREATE TABLE statements executed.")


# ---------------------------------------------------------------------------
# Helper: execute indexes and grants (post-data-load)
# ---------------------------------------------------------------------------


def _execute_ddl_indexes_and_grants(conn) -> None:
    """Execute CREATE INDEX and CREATE USER/GRANT statements (post-data-load)."""
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

    # El DDL declara el usuario read-only con un password placeholder para que el
    # archivo sea versionable. Se reemplaza acá por uno aleatorio: nadie necesita
    # conocerlo (el agente entra con las credenciales del secret de Aurora), así
    # que no hace falta persistirlo.
    # token_urlsafe genera solo [A-Za-z0-9_-], así que es seguro interpolarlo en el
    # DDL: PostgreSQL no acepta bind params en CREATE/ALTER USER. Se valida igual.
    random_password = secrets.token_urlsafe(32)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", random_password):
        raise RuntimeError("El password generado contiene caracteres inesperados.")
    sql_text = sql_text.replace("readonly_password_placeholder", random_password)

    statements = [s.strip() for s in sql_text.split(";") if s.strip()]

    cursor = conn.cursor()
    for stmt in statements:
        meaningful = [l for l in stmt.split("\n") if l.strip() and not l.strip().startswith("--")]
        if not meaningful:
            continue
        try:
            cursor.execute(stmt + ";")
            # No logueamos la sentencia del CREATE USER para no filtrar el password.
            safe_preview = "CREATE USER codeagent_readonly ..." if "CREATE USER" in stmt else f"{stmt[:70]}..."
            print(f"[IDX] OK: {safe_preview}")
        except Exception as e:
            print(f"[IDX] Warning: {e}")

    # En un re-seed el CREATE USER de arriba falla porque el rol ya existe, así que
    # el password no rotaría. El ALTER garantiza que siempre quede el aleatorio.
    try:
        cursor.execute(f"ALTER USER codeagent_readonly WITH PASSWORD '{random_password}';")
        print("[IDX] OK: ALTER USER codeagent_readonly (password rotado)")
    except Exception as e:
        print(f"[IDX] Warning al rotar el password de codeagent_readonly: {e}")

    cursor.close()
    print("[IDX] Indexes and grants executed.")


# ---------------------------------------------------------------------------
# Helper: bulk insert using multi-value INSERT (pg8000 compatible)
# ---------------------------------------------------------------------------


def _bulk_insert(conn, table: str, columns: list[str], rows: list[tuple],
                 batch_size: int = BATCH_SIZE) -> int:
    """
    Insert rows into table using multi-value INSERT in batches.
    Uses ON CONFLICT DO NOTHING for idempotent re-runs.
    Uses %s placeholders for pg8000.
    Returns total rows inserted.
    """
    if not rows:
        return 0

    n_cols = len(columns)
    # Quote column names that have uppercase letters
    col_list = ", ".join(
        f'"{c}"' if any(ch.isupper() for ch in c) else c
        for c in columns
    )
    total_inserted = 0
    cursor = conn.cursor()

    for batch_start in range(0, len(rows), batch_size):
        batch = rows[batch_start:batch_start + batch_size]

        # Build VALUES clause: (%s, %s, ...), (%s, %s, ...), ...
        placeholders_row = "(" + ", ".join(["%s"] * n_cols) + ")"
        placeholders = ", ".join([placeholders_row] * len(batch))

        # Flatten all values into a single list
        flat_values = []
        for row in batch:
            for val in row:
                flat_values.append(val)

        sql = f'INSERT INTO {table} ({col_list}) VALUES {placeholders} ON CONFLICT DO NOTHING'

        try:
            cursor.execute(sql, flat_values)
            total_inserted += len(batch)
        except Exception as e:
            print(f"[INSERT] Error on {table} at offset {batch_start}: {e}")
            # Log but continue — ON CONFLICT should handle duplicates
            # but if there's a different error (e.g. FK violation), skip this batch
            total_inserted += 0

        # Progress logging for large tables
        if batch_start > 0 and batch_start % (batch_size * 10) == 0:
            print(f"[INSERT] {table}: {batch_start + len(batch):,}/{len(rows):,} processed")

    cursor.close()
    return total_inserted


# ---------------------------------------------------------------------------
# Helper: insert DataFrame rows (for catalog generators that return DataFrames)
# ---------------------------------------------------------------------------


def _insert_dataframe(conn, table: str, columns: list[str], df, batch_size: int = BATCH_SIZE) -> int:
    """Convert a pandas DataFrame to list[tuple] and bulk insert."""
    rows = [tuple(row) for row in df[columns].itertuples(index=False, name=None)]
    return _bulk_insert(conn, table, columns, rows, batch_size)


# ---------------------------------------------------------------------------
# Helper: quote table name (for mixed-case tables like "UltimaMillaMarca")
# ---------------------------------------------------------------------------


def _qt(name: str) -> str:
    """Quote table name if it contains uppercase letters."""
    if any(c.isupper() for c in name):
        return f'"{name}"'
    return name


# ---------------------------------------------------------------------------
# Main orchestration: generate and insert all data in dependency order
# ---------------------------------------------------------------------------


def _seed_all_data(conn) -> dict[str, int]:
    """
    Generate and insert all seed data in 8 waves (dependency order).
    Returns dict of table_name -> row_count.
    """
    counts: dict[str, int] = {}

    # =========================================================================
    # WAVE 1: Catálogos sin dependencias (DataFrames)
    # Tables: especialidad, loyalty_doctor, institucion, linea, ciclo,
    #         categoria_promocion
    # =========================================================================
    print("[WAVE 1] Generating catalogs (no dependencies)...")
    t0 = time.time()

    especialidades_df = generate_especialidades(n=50)
    counts["especialidad"] = _insert_dataframe(
        conn, "especialidad", ["id", "nombre"], especialidades_df
    )

    loyalty_df = generate_loyalty_doctor()
    counts["loyalty_doctor"] = _insert_dataframe(
        conn, "loyalty_doctor", ["id", "nombre"], loyalty_df
    )

    instituciones_df = generate_instituciones(n=500)
    counts["institucion"] = _insert_dataframe(
        conn, "institucion", ["id", "nombre"], instituciones_df
    )

    lineas_df = generate_lineas(n=5)
    counts["linea"] = _insert_dataframe(
        conn, "linea", ["id", "nombre", "abreviatura"], lineas_df
    )

    ciclos_df = generate_ciclos(n=12)
    counts["ciclo"] = _insert_dataframe(
        conn, "ciclo", ["id", "inicio", "fin", "nombre"], ciclos_df
    )

    categorias_df = generate_categorias_promocion()
    counts["categoria_promocion"] = _insert_dataframe(
        conn, "categoria_promocion", ["id", "abreviatura", "nombre_categoria"], categorias_df
    )

    print(f"[WAVE 1] Done in {time.time() - t0:.1f}s")

    # =========================================================================
    # WAVE 2: Catálogos con FK (DataFrames)
    # Tables: grilla (FK→linea), familia_producto, producto (FK→linea)
    # =========================================================================
    print("[WAVE 2] Generating catalogs with FK...")
    t0 = time.time()

    grillas_df = generate_grillas(lineas_df, n=10)
    counts["grilla"] = _insert_dataframe(
        conn, "grilla", ["id", "nombre_grilla", "id_linea"], grillas_df
    )

    familias_df = generate_familias_producto(n=40)
    counts["familia_producto"] = _insert_dataframe(
        conn, "familia_producto",
        ["id", "nombre", "principio_activo", "accion_terapeutica"],
        familias_df
    )

    productos_df = generate_productos(lineas_df, n=150)
    counts["producto"] = _insert_dataframe(
        conn, "producto", ["id", "nombre", "id_linea"], productos_df
    )

    print(f"[WAVE 2] Done in {time.time() - t0:.1f}s")


    # =========================================================================
    # WAVE 3: Entidades principales (list[tuple])
    # Tables: apm (200), doctor (30,000)
    # =========================================================================
    print("[WAVE 3] Generating entities (APM + Doctor)...")
    t0 = time.time()

    # Extract ID lists from DataFrames for entity generators
    linea_ids = lineas_df["id"].tolist()
    especialidad_ids = especialidades_df["id"].tolist()
    loyalty_ids = loyalty_df["id"].tolist()

    apm_rows = generate_apms(linea_ids, n=200)
    # DDL columns: id, "primerNombre", "primerApellido", email, id_linea,
    #              gerente_regional_id, "codigoPromotor", inactivo
    counts["apm"] = _bulk_insert(
        conn, "apm",
        ["id", "primerNombre", "primerApellido", "email", "id_linea",
         "gerente_regional_id", "codigoPromotor", "inactivo"],
        apm_rows
    )

    doctor_rows = generate_doctors(especialidad_ids, loyalty_ids, n=30_000)
    # DDL columns: id, "primerNombre", "primerApellido", "matriculaNacional",
    #              especialidad_id, loyalty_id, categoria_id, inactivo
    counts["doctor"] = _bulk_insert(
        conn, "doctor",
        ["id", "primerNombre", "primerApellido", "matriculaNacional",
         "especialidad_id", "loyalty_id", "categoria_id", "inactivo"],
        doctor_rows
    )

    print(f"[WAVE 3] Done in {time.time() - t0:.1f}s")

    # =========================================================================
    # WAVE 4: Entity relations (list[tuple])
    # Tables: linea_apm (~300), datos_visita (25,000), cartera_medica (25,000)
    # =========================================================================
    print("[WAVE 4] Generating entity relations...")
    t0 = time.time()

    # Extract IDs from generated tuples
    apm_ids = [row[0] for row in apm_rows]
    doctor_ids = [row[0] for row in doctor_rows]
    institucion_ids = instituciones_df["id"].tolist()

    linea_apm_rows = generate_linea_apm(apm_ids, linea_ids, target=300)
    # DDL columns: id, id_apm, id_linea
    counts["linea_apm"] = _bulk_insert(
        conn, "linea_apm", ["id", "id_apm", "id_linea"], linea_apm_rows
    )

    datos_visita_rows = generate_datos_visita(institucion_ids, n=25_000)
    # DDL columns: id, frecuencia, institucion_id
    counts["datos_visita"] = _bulk_insert(
        conn, "datos_visita", ["id", "frecuencia", "institucion_id"], datos_visita_rows
    )

    datos_visita_ids = [row[0] for row in datos_visita_rows]
    cartera_rows = generate_cartera_medica(apm_ids, doctor_ids, datos_visita_ids, n=25_000)
    # DDL columns: id, apm_id, doctor_id, datos_visita_id, inactivo
    counts["cartera_medica"] = _bulk_insert(
        conn, "cartera_medica",
        ["id", "apm_id", "doctor_id", "datos_visita_id", "inactivo"],
        cartera_rows
    )

    print(f"[WAVE 4] Done in {time.time() - t0:.1f}s")


    # =========================================================================
    # WAVE 5: Agenda (150,000) + Agenda_producto (300,000)
    # =========================================================================
    print("[WAVE 5] Generating agenda (150K) + agenda_producto (300K)...")
    t0 = time.time()

    familia_producto_ids = familias_df["id"].tolist()

    agenda_rows = generate_agenda(cartera_rows, n=150_000)
    # DDL columns: id, inicio, fin, apm_id, doctor_id, visita_exitosa,
    #              observaciones, visita_tipo, inactivo
    counts["agenda"] = _bulk_insert(
        conn, "agenda",
        ["id", "inicio", "fin", "apm_id", "doctor_id", "visita_exitosa",
         "observaciones", "visita_tipo", "inactivo"],
        agenda_rows
    )

    agenda_producto_rows = generate_agenda_producto(agenda_rows, familia_producto_ids, n=300_000)
    # DDL columns: id, id_agenda, id_producto
    counts["agenda_producto"] = _bulk_insert(
        conn, "agenda_producto",
        ["id", "id_agenda", "id_producto"],
        agenda_producto_rows
    )

    print(f"[WAVE 5] Done in {time.time() - t0:.1f}s")

    # =========================================================================
    # WAVE 6: UltimaMillaMedico (30,000 rows)
    # =========================================================================
    print("[WAVE 6] Generating UltimaMillaMedico (30K)...")
    t0 = time.time()

    um_medico_rows = generate_ultima_milla_medico(doctor_ids)
    # DDL columns: "idMedicoCUP", "idMedicoAPX", "IETrim", "ShareTrim",
    #              "ShareTrim_1", "ShareMes"
    counts["UltimaMillaMedico"] = _bulk_insert(
        conn, _qt("UltimaMillaMedico"),
        ["idMedicoCUP", "idMedicoAPX", "IETrim", "ShareTrim", "ShareTrim_1", "ShareMes"],
        um_medico_rows
    )

    print(f"[WAVE 6] Done in {time.time() - t0:.1f}s")

    # =========================================================================
    # WAVE 7: UltimaMillaMarca (~1.5M rows — chunked for memory)
    # =========================================================================
    print("[WAVE 7] Generating UltimaMillaMarca (~1.5M rows)...")
    t0 = time.time()

    # CUP IDs map: "CUP_DOC_00001" (same prefix used by generate_ultima_milla_medico)
    medico_cup_ids = [f"CUP_{doc_id}" for doc_id in doctor_ids]

    # Process in chunks of 1000 doctors to manage memory
    doctor_chunk_size = 1000
    um_marca_total = 0
    um_marca_columns = [
        "idMedicoCUP", "idMarca", "idMercado", "idLaboratorio",
        "marcaNombre", "ShareMarcaMercado", "ShareMarcaMes",
        "IEMarcaTrim", "ShareMarcaTrim", "ShareMarcaTrim_1",
    ]

    for chunk_start in range(0, len(medico_cup_ids), doctor_chunk_size):
        chunk_ids = medico_cup_ids[chunk_start:chunk_start + doctor_chunk_size]
        chunk_rows = generate_ultima_milla_marca(chunk_ids)

        inserted = _bulk_insert(
            conn, _qt("UltimaMillaMarca"),
            um_marca_columns,
            chunk_rows,
            batch_size=BIG_BATCH_SIZE,
        )
        um_marca_total += inserted

        chunk_num = chunk_start // doctor_chunk_size + 1
        if chunk_num % 5 == 0:
            elapsed = time.time() - t0
            progress_pct = (chunk_start + doctor_chunk_size) / len(medico_cup_ids) * 100
            print(f"[WAVE 7] {progress_pct:.0f}% — {um_marca_total:,} rows — {elapsed:.1f}s")

    counts["UltimaMillaMarca"] = um_marca_total
    print(f"[WAVE 7] Done: {um_marca_total:,} rows in {time.time() - t0:.1f}s")


    # =========================================================================
    # WAVE 8: Final tables (UltimaMillaObjetivo, familia_APX, detalle_promo)
    # =========================================================================
    print("[WAVE 8] Generating final tables...")
    t0 = time.time()

    grilla_ids = grillas_df["id"].tolist()
    categoria_ids = categorias_df["id"].tolist()
    ciclo_ids = ciclos_df["id"].tolist()

    um_objetivo_rows = generate_ultima_milla_objetivo(especialidad_ids)
    # DDL columns: "idEspecialidad", "idMarca", "idMercado", "marcaNombre"
    counts["UltimaMillaObjetivoMarcaMercado"] = _bulk_insert(
        conn, _qt("UltimaMillaObjetivoMarcaMercado"),
        ["idEspecialidad", "idMarca", "idMercado", "marcaNombre"],
        um_objetivo_rows
    )

    familia_apx_rows = generate_familia_apx_a_marca_cup(familia_producto_ids)
    # DDL columns: id_familia_producto_apx, "codMarcaCUP"
    counts["familia_APX_a_Marca_CUP"] = _bulk_insert(
        conn, "familia_apx_a_marca_cup",
        ["id_familia_producto_apx", "codMarcaCUP"],
        familia_apx_rows
    )

    detalle_promo_rows = generate_detalle_promocion_producto(
        familia_producto_ids, grilla_ids, categoria_ids, ciclo_ids, n=100
    )
    # DDL columns: id, id_familia_producto, id_grilla, id_categoria_promocion, id_ciclo
    counts["detalle_promocion_producto"] = _bulk_insert(
        conn, "detalle_promocion_producto",
        ["id", "id_familia_producto", "id_grilla", "id_categoria_promocion", "id_ciclo"],
        detalle_promo_rows
    )

    print(f"[WAVE 8] Done in {time.time() - t0:.1f}s")

    return counts


# ---------------------------------------------------------------------------
# Lambda Handler
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Validation: run post-seed validation queries
# ---------------------------------------------------------------------------


def _validate(conn) -> dict:
    """
    Run validation queries against the seeded database.
    Returns validation results including counts, index checks, and user checks.
    """
    cursor = conn.cursor()
    results: dict = {"counts": {}, "indices": [], "user_check": {}}

    # --- Row counts ---
    count_queries = {
        "UltimaMillaMarca": 'SELECT COUNT(*) FROM "UltimaMillaMarca"',
        "cartera_medica_active": "SELECT COUNT(*) FROM cartera_medica WHERE inactivo = false",
        "agenda": "SELECT COUNT(*) FROM agenda",
        "doctor": "SELECT COUNT(*) FROM doctor",
        "apm": "SELECT COUNT(*) FROM apm",
        "UltimaMillaMedico": 'SELECT COUNT(*) FROM "UltimaMillaMedico"',
        "agenda_producto": "SELECT COUNT(*) FROM agenda_producto",
        "familia_APX_a_Marca_CUP": "SELECT COUNT(*) FROM familia_apx_a_marca_cup",
        "detalle_promocion_producto": "SELECT COUNT(*) FROM detalle_promocion_producto",
    }

    for name, query in count_queries.items():
        try:
            cursor.execute(query)
            row = cursor.fetchone()
            results["counts"][name] = row[0] if row else 0
            print(f"[VALIDATE] {name}: {results['counts'][name]:,}")
        except Exception as e:
            results["counts"][name] = f"ERROR: {e}"
            print(f"[VALIDATE] {name}: ERROR - {e}")

    # --- Check indices exist ---
    index_query = """
        SELECT indexname, tablename
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
    """
    try:
        cursor.execute(index_query)
        rows = cursor.fetchall()
        results["indices"] = [
            {"index_name": r[0], "table_name": r[1]}
            for r in rows
            if not r[0].endswith("_pkey")  # exclude primary key indices
        ]
        print(f"[VALIDATE] Found {len(results['indices'])} non-PK indices")
    except Exception as e:
        results["indices"] = f"ERROR: {e}"
        print(f"[VALIDATE] Index check ERROR: {e}")

    # --- Check read-only user exists ---
    user_check_query = """
        SELECT rolname, rolcanlogin
        FROM pg_roles
        WHERE rolname = 'codeagent_readonly'
    """
    try:
        cursor.execute(user_check_query)
        row = cursor.fetchone()
        if row:
            results["user_check"] = {
                "exists": True,
                "rolname": row[0],
                "can_login": row[1],
            }
            print(f"[VALIDATE] User codeagent_readonly: exists={True}, can_login={row[1]}")
        else:
            results["user_check"] = {"exists": False}
            print("[VALIDATE] User codeagent_readonly: NOT FOUND")
    except Exception as e:
        results["user_check"] = {"exists": False, "error": str(e)}
        print(f"[VALIDATE] User check ERROR: {e}")

    # --- Verify read-only user permissions (try SET ROLE) ---
    try:
        cursor.execute("SET ROLE codeagent_readonly")
        cursor.execute('SELECT 1 FROM "UltimaMillaMarca" LIMIT 1')
        row = cursor.fetchone()
        results["user_check"]["can_select"] = row is not None
        print(f"[VALIDATE] codeagent_readonly can SELECT: {row is not None}")
        # Reset role back to admin
        cursor.execute("RESET ROLE")
    except Exception as e:
        results["user_check"]["can_select"] = False
        results["user_check"]["select_error"] = str(e)
        print(f"[VALIDATE] codeagent_readonly SELECT test ERROR: {e}")
        # Reset role in case of error
        try:
            cursor.execute("RESET ROLE")
        except Exception:
            pass

    cursor.close()
    return results


# ---------------------------------------------------------------------------
# Lambda Handler
# ---------------------------------------------------------------------------


def handler(event, context):
    """
    Lambda handler: seeds or validates Aurora PostgreSQL for PharmAssist POC.

    Actions (determined by event.get("action")):
      - "seed" (default): Generate and load all seed data
      - "validate": Run validation queries on existing data

    Seed steps:
      1. Get DB credentials from Secrets Manager
      2. Connect to PostgreSQL
      3. Execute DDL (CREATE TABLE only)
      4. Generate and insert seed data in 8 dependency waves
      5. Execute indexes and read-only user setup (post-load)
      6. Return counts per table

    Validate steps:
      1. Get DB credentials from Secrets Manager
      2. Connect to PostgreSQL
      3. Run count queries, check indices, check read-only user
      4. Return validation results

    Returns:
        dict with statusCode and body (JSON with counts or error)
    """
    action = event.get("action", "seed") if event else "seed"
    total_start = time.time()

    try:
        # Step 1: Get credentials
        print(f"[HANDLER] Action: {action}")
        print("[HANDLER] Getting DB credentials from Secrets Manager...")
        creds = _get_db_credentials()
        print(f"[HANDLER] Connecting to {creds['host']}:{creds['port']}/{creds['database']}")

        # Step 2: Connect
        conn = _connect(creds)
        print("[HANDLER] Connected to PostgreSQL.")

        if action == "validate":
            # --- VALIDATE mode ---
            print("[HANDLER] Running validation queries...")
            validation_results = _validate(conn)
            conn.close()

            total_elapsed = time.time() - total_start
            result = {
                "status": "success",
                "action": "validate",
                "total_time_seconds": round(total_elapsed, 1),
                "validation": validation_results,
            }
            print(f"[HANDLER] VALIDATE COMPLETE in {total_elapsed:.1f}s")
            return {
                "statusCode": 200,
                "body": json.dumps(result),
            }

        if action == "grants":
            # --- GRANTS mode ---
            # Reaplica índices y grants y rota el password del rol read-only,
            # sin regenerar los datos. Útil para rotar la credencial sin el
            # costo de un seed completo.
            print("[HANDLER] Reaplicando índices y grants (sin regenerar datos)...")
            _execute_ddl_indexes_and_grants(conn)
            conn.close()
            total_elapsed = time.time() - total_start
            print(f"[HANDLER] GRANTS COMPLETE in {total_elapsed:.1f}s")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "action": "grants",
                    "total_time_seconds": round(total_elapsed, 1),
                }),
            }

        # --- SEED mode (default) ---
        # Step 3: Execute DDL (CREATE TABLE only)
        print("[HANDLER] Executing DDL (CREATE TABLE)...")
        _execute_ddl_tables(conn)

        # Step 4: Generate and insert seed data
        print("[HANDLER] Starting seed data generation...")
        counts = _seed_all_data(conn)

        # Step 5: Create indexes and read-only user (post-load)
        print("[HANDLER] Creating indexes and read-only user...")
        _execute_ddl_indexes_and_grants(conn)

        # Step 6: Close connection
        conn.close()

        total_elapsed = time.time() - total_start
        total_rows = sum(counts.values())

        result = {
            "status": "success",
            "action": "seed",
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
                "action": action,
                "error": error_msg,
                "elapsed_seconds": round(total_elapsed, 1),
            }),
        }
