"""Test CRM generation step by step to find the bottleneck."""
import os
import time
os.environ["DATASOURCES_RDS_ENDPOINT"] = "localhost"
os.environ["DATASOURCES_DB_USER"] = "postgres"
os.environ["DATASOURCES_DB_PASSWORD"] = "jiyzY1Wxm0WrBQI,1w6=ejq_N16Q6L"
os.environ["DATASOURCES_DB_NAME"] = "pharmassist_sources"
os.environ["SEED_MODE"] = "light"

import psycopg2
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
cur = conn.cursor()

from generators import crm_generator

steps = [
    ("zones", lambda: crm_generator.generate_zones(cur)),
    ("specialties", lambda: crm_generator.generate_specialties(cur)),
    ("tags", lambda: crm_generator.generate_tags(cur)),
    ("apms", lambda: crm_generator.generate_apms(cur, 30)),
    ("doctors", lambda: crm_generator.generate_doctors(cur, 30, 15)),
]

for name, fn in steps:
    t0 = time.time()
    print(f"  {name}...", end=" ", flush=True)
    n = fn()
    conn.commit()
    print(f"{n} rows in {time.time()-t0:.1f}s")

print("\nDone! Basic CRM tables populated.")
conn.close()
