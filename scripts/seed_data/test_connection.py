"""Quick test: connect to RDS and generate CRM dimensions only."""
import sys
import os
import time

# Force connection params
os.environ["DATASOURCES_RDS_ENDPOINT"] = "localhost"
os.environ["DATASOURCES_DB_USER"] = "postgres"
os.environ["DATASOURCES_DB_PASSWORD"] = "jiyzY1Wxm0WrBQI,1w6=ejq_N16Q6L"

import psycopg2
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME}...")
conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
print("Connected!")

cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM crm_interno.zona")
print(f"Zones already in DB: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM crm_interno.doctor")
print(f"Doctors already in DB: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM closeup.prescripcion")
print(f"Prescriptions already in DB: {cur.fetchone()[0]}")

conn.close()
print("Done!")
