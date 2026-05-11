"""Configuration for synthetic data generation."""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# --- Connection ---
# Can be overridden via env vars for local dev vs RDS
DB_HOST = os.environ.get("DATASOURCES_RDS_ENDPOINT", "localhost")
DB_PORT = int(os.environ.get("DATASOURCES_RDS_PORT", "5432"))
DB_NAME = os.environ.get("DATASOURCES_DB_NAME", "pharmassist_sources")
DB_USER = os.environ.get("DATASOURCES_DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DATASOURCES_DB_PASSWORD", "postgres")

# --- Volumes ---
# Use SEED_MODE=light for quick validation (~5 min via SSM tunnel)
# Use SEED_MODE=full for production-like volumes (~30 min via SSM tunnel)
SEED_MODE = os.environ.get("SEED_MODE", "light")

if SEED_MODE == "light":
    NUM_APMS = 10
    NUM_DOCTORS = 500
    NUM_ZONES = 30
    NUM_SPECIALTIES = 15
    NUM_LINES = 5
    NUM_PRODUCTS = 50
    NUM_CYCLES = 4
    NUM_TAGS = 20
    NUM_CUP_DOCTORS = 2000
    NUM_CUP_BRANDS = 500
    NUM_CUP_MARKETS = 20
    NUM_PRESCRIPTIONS = 100_000
    PRESCRIPTION_MONTHS = 12
    NUM_IQVIA_PRODUCTS = 1000
    NUM_IQVIA_LABS = 50
    NUM_IQVIA_GEOS = 20
    NUM_IQVIA_PERIODS = 24
    NUM_SALES_ROWS = 100_000
    NUM_MAESTRO_MEDICOS = 500
    NUM_MAESTRO_PRODUCTOS = 80
else:  # full
    NUM_APMS = 50
    NUM_DOCTORS = 3000
    NUM_ZONES = 60
    NUM_SPECIALTIES = 25
    NUM_LINES = 8
    NUM_PRODUCTS = 150
    NUM_CYCLES = 6
    NUM_TAGS = 40
    NUM_CUP_DOCTORS = 15000
    NUM_CUP_BRANDS = 3000
    NUM_CUP_MARKETS = 60
    NUM_PRESCRIPTIONS = 3_000_000
    PRESCRIPTION_MONTHS = 24
    NUM_IQVIA_PRODUCTS = 8000
    NUM_IQVIA_LABS = 150
    NUM_IQVIA_GEOS = 50
    NUM_IQVIA_PERIODS = 36
    NUM_SALES_ROWS = 2_500_000
    NUM_MAESTRO_MEDICOS = 3000
    NUM_MAESTRO_PRODUCTOS = 300

# --- Seed for reproducibility ---
RANDOM_SEED = 42
