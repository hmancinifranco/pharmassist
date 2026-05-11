"""Kill all active connections to the database and drop schemas."""
import os
os.environ.setdefault("DATASOURCES_RDS_ENDPOINT", "localhost")
os.environ.setdefault("DATASOURCES_DB_USER", "postgres")
os.environ.setdefault("DATASOURCES_DB_PASSWORD", "jiyzY1Wxm0WrBQI,1w6=ejq_N16Q6L")
os.environ.setdefault("DATASOURCES_DB_NAME", "pharmassist_sources")

import psycopg2
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
conn.autocommit = True
cur = conn.cursor()

# Kill all other connections
print("Killing other connections...")
cur.execute("""
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = %s AND pid <> pg_backend_pid()
""", (DB_NAME,))
killed = cur.rowcount
print(f"  Killed {killed} connections")

# Now drop schemas
print("Dropping schemas...")
for schema in ["maestros", "iqvia", "closeup", "crm_interno"]:
    cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    print(f"  Dropped {schema}")

conn.close()
print("Done!")
