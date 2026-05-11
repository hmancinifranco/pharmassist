"""Initialize database schemas by executing DDL files against PostgreSQL."""
import os
import sys
import psycopg2
from pathlib import Path

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


SCHEMAS_DIR = Path(__file__).parent / "schemas"

DDL_FILES = [
    "crm_ddl.sql",
    "closeup_ddl.sql",
    "iqvia_ddl.sql",
    "maestros_ddl.sql",
]


def get_connection():
    """Create a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def execute_ddl(conn, ddl_file: Path):
    """Execute a DDL file against the database."""
    print(f"  Executing {ddl_file.name}...")
    sql = ddl_file.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"  ✓ {ddl_file.name} done")


def drop_schemas(conn):
    """Drop all schemas to start fresh."""
    schemas = ["maestros", "iqvia", "closeup", "crm_interno"]
    with conn.cursor() as cur:
        for schema in schemas:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE;")
            print(f"  Dropped schema: {schema}")
    conn.commit()


def main():
    """Main entry point."""
    fresh = "--fresh" in sys.argv

    print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    conn = get_connection()
    print("Connected.\n")

    if fresh:
        print("Dropping existing schemas (--fresh mode)...")
        drop_schemas(conn)
        print()

    print("Creating schemas and tables...")
    for ddl_file_name in DDL_FILES:
        ddl_path = SCHEMAS_DIR / ddl_file_name
        if not ddl_path.exists():
            print(f"  ✗ File not found: {ddl_path}")
            sys.exit(1)
        execute_ddl(conn, ddl_path)

    print("\n✅ All schemas created successfully.")

    # Print table counts per schema
    print("\nSchema summary:")
    with conn.cursor() as cur:
        for schema in ["crm_interno", "closeup", "iqvia", "maestros"]:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                (schema,),
            )
            count = cur.fetchone()[0]
            print(f"  {schema}: {count} tables")

    conn.close()


if __name__ == "__main__":
    main()
