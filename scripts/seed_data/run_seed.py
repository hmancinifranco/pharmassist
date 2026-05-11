"""Run seed with explicit env vars and progress tracking.

Usage: source ../../infrastructure/.venv/bin/activate && python run_seed.py
"""
import os
import sys
import time

# Force connection params for SSM tunnel
os.environ["DATASOURCES_RDS_ENDPOINT"] = "localhost"
os.environ["DATASOURCES_DB_USER"] = "postgres"
os.environ["DATASOURCES_DB_PASSWORD"] = "jiyzY1Wxm0WrBQI,1w6=ejq_N16Q6L"
os.environ["DATASOURCES_DB_NAME"] = "pharmassist_sources"
os.environ.setdefault("SEED_MODE", "light")  # default to light for SSM tunnel

import psycopg2
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

def get_connection():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)

def run_schemas():
    """Create schemas fresh."""
    from init_schemas import main as init_main
    sys.argv = ["init_schemas.py", "--fresh"]
    init_main()

def run_generators():
    """Run all generators."""
    from generators import crm_generator, closeup_generator, iqvia_generator, maestros_generator

    conn = get_connection()
    conn.autocommit = False

    print("\n[1/4] CRM Interno...")
    t0 = time.time()
    summary_crm = crm_generator.generate_all(conn)
    print(f"  Done in {time.time() - t0:.1f}s")
    for k, v in summary_crm.items():
        print(f"    {k}: {v:,}")

    print("\n[2/4] CloseUp...")
    t0 = time.time()
    summary_cup = closeup_generator.generate_all(conn)
    print(f"  Done in {time.time() - t0:.1f}s")
    for k, v in summary_cup.items():
        print(f"    {k}: {v:,}")

    print("\n[3/4] IQVIA...")
    t0 = time.time()
    summary_iqvia = iqvia_generator.generate_all(conn)
    print(f"  Done in {time.time() - t0:.1f}s")
    for k, v in summary_iqvia.items():
        print(f"    {k}: {v:,}")

    print("\n[4/4] Maestros + UltimaMilla...")
    t0 = time.time()
    summary_maestros = maestros_generator.generate_all(conn)
    print(f"  Done in {time.time() - t0:.1f}s")
    for k, v in summary_maestros.items():
        print(f"    {k}: {v:,}")

    conn.close()

if __name__ == "__main__":
    start = time.time()
    print("=" * 60)
    print("STEP 1: Fresh schemas")
    print("=" * 60)

    # Kill zombie connections and recreate schemas
    conn_admin = get_connection()
    conn_admin.autocommit = True
    cur_admin = conn_admin.cursor()
    cur_admin.execute("""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = %s AND pid <> pg_backend_pid()
    """, (DB_NAME,))
    print(f"  Killed {cur_admin.rowcount} zombie connections")
    for schema in ["maestros", "iqvia", "closeup", "crm_interno"]:
        cur_admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    print("  Dropped all schemas")
    conn_admin.close()

    # Recreate schemas
    sys.argv = ["init_schemas.py"]
    from init_schemas import main as init_main
    init_main()

    print("\n" + "=" * 60)
    print(f"STEP 2: Generating data (mode: {os.environ.get('SEED_MODE', 'light')})")
    print("=" * 60)
    run_generators()

    elapsed = time.time() - start
    print(f"\n✅ Total time: {elapsed:.1f}s")
