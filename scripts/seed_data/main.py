"""Main orchestrator for synthetic data generation.

Generates data in the correct order to maintain referential integrity:
1. CRM interno (dimensions + operational tables)
2. CloseUp (dimensions + fact table)
3. IQVIA (dimensions + fact table)
4. Maestros + UltimaMilla (cross-source integration)

Usage:
    python main.py              # Generate all data
    python main.py --fresh      # Drop and recreate schemas first
    python main.py --schema-only  # Only create schemas, no data
"""
import sys
import time
import psycopg2

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
from init_schemas import main as init_schemas_main


def get_connection():
    """Create a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def print_summary(all_summaries: dict):
    """Print a summary of generated data."""
    print("\n" + "=" * 60)
    print("GENERATION SUMMARY")
    print("=" * 60)
    for source, summary in all_summaries.items():
        print(f"\n  {source}:")
        for table, count in summary.items():
            print(f"    {table}: {count:,} rows")
    print("\n" + "=" * 60)


def main():
    """Main entry point."""
    schema_only = "--schema-only" in sys.argv

    # Step 1: Create schemas
    print("=" * 60)
    print("STEP 1: Creating schemas")
    print("=" * 60)
    init_schemas_main()

    if schema_only:
        print("\n--schema-only mode: skipping data generation.")
        return

    # Step 2: Generate data
    print("\n" + "=" * 60)
    print("STEP 2: Generating synthetic data")
    print("=" * 60)

    conn = get_connection()
    all_summaries = {}
    start_time = time.time()

    try:
        # Import generators here to avoid circular imports with config
        from generators import crm_generator, closeup_generator, iqvia_generator, maestros_generator

        # 2a: CRM interno
        print("\n[1/4] CRM Interno...")
        t0 = time.time()
        all_summaries["CRM Interno"] = crm_generator.generate_all(conn)
        print(f"  Done in {time.time() - t0:.1f}s")

        # 2b: CloseUp
        print("\n[2/4] CloseUp (prescripciones)...")
        t0 = time.time()
        all_summaries["CloseUp"] = closeup_generator.generate_all(conn)
        print(f"  Done in {time.time() - t0:.1f}s")

        # 2c: IQVIA
        print("\n[3/4] IQVIA (ventas de mercado)...")
        t0 = time.time()
        all_summaries["IQVIA"] = iqvia_generator.generate_all(conn)
        print(f"  Done in {time.time() - t0:.1f}s")

        # 2d: Maestros + UltimaMilla (depends on CRM + CloseUp)
        print("\n[4/4] Maestros + UltimaMilla...")
        t0 = time.time()
        all_summaries["Maestros"] = maestros_generator.generate_all(conn)
        print(f"  Done in {time.time() - t0:.1f}s")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error during generation: {e}")
        raise
    finally:
        conn.close()

    elapsed = time.time() - start_time
    print_summary(all_summaries)
    print(f"\n✅ Total generation time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
