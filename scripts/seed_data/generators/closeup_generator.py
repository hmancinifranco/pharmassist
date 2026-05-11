"""Generate synthetic data for the CloseUp (prescriptions) schema."""
import random
from datetime import date, timedelta

import numpy as np
from faker import Faker
from tqdm import tqdm

from config import (
    NUM_CUP_DOCTORS, NUM_CUP_BRANDS, NUM_CUP_MARKETS,
    NUM_PRESCRIPTIONS, PRESCRIPTION_MONTHS, RANDOM_SEED,
)

fake = Faker("es_AR")
Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# --- Domain data ---
LABS = [
    "Roemmers", "Bagó", "Gador", "Casasco", "Raffo",
    "Montpellier", "Bernabó", "Andrómaco", "Pfizer", "Roche",
    "Novartis", "Bayer", "AstraZeneca", "GSK", "Sanofi",
    "MSD", "Abbott", "Lilly", "Boehringer", "Servier",
    "Teva", "Sandoz", "Stada", "Ferring", "Merck",
]

THERAPEUTIC_CLASSES = [
    "Antiulcerosos", "Antihipertensivos", "Hipolipemiantes", "Antidepresivos",
    "Ansiolíticos", "Antiinflamatorios", "Analgésicos", "Antibióticos",
    "Antidiabéticos", "Broncodilatadores", "Antihistamínicos", "Corticoides",
    "Anticoagulantes", "Antiarrítmicos", "Diuréticos", "Antiepilépticos",
    "Antipsicóticos", "Hormonas tiroideas", "Antiosteoporóticos", "Antifúngicos",
]

REGIONS = [f"REG-{i:02d}" for i in range(1, 21)]
SPECIALTIES_CUP = [f"ESP-{i:02d}" for i in range(1, 26)]


def generate_medicos(cur):
    """Generate CloseUp doctors (superset of CRM doctors)."""
    print("    Generating CloseUp medicos...")
    batch = []
    for i in range(1, NUM_CUP_DOCTORS + 1):
        batch.append((
            f"CUP-{i:06d}",
            fake.first_name(),
            fake.last_name(),
            random.choice(SPECIALTIES_CUP),
            fake.city()[:50],
            random.choice(["Buenos Aires", "CABA", "Córdoba", "Santa Fe", "Mendoza", "Tucumán"]),
            fake.street_name()[:50] if random.random() > 0.5 else None,
            random.choice(REGIONS),
            True,
        ))
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        """INSERT INTO closeup.medico
        (CDGMED, nombre, apellido, especialidad, localidad, provincia, barrio, cdgreg_pmix, activo)
        VALUES %s""",
        batch,
    )
    return NUM_CUP_DOCTORS


def generate_marcas(cur):
    """Generate CloseUp brands/products."""
    print("    Generating CloseUp marcas...")
    forms = ["Comprimidos", "Cápsulas", "Suspensión", "Inyectable", "Crema", "Gotas", "Parches"]
    concentrations = ["5mg", "10mg", "20mg", "25mg", "50mg", "100mg", "200mg", "500mg", "1g"]

    batch = []
    for i in range(1, NUM_CUP_BRANDS + 1):
        lab = random.choice(LABS)
        batch.append((
            f"MK-{i:05d}",
            f"{fake.word().upper()} {random.choice(concentrations)} {random.choice(forms)}",
            lab,
            fake.word().capitalize(),
            random.choice(forms),
            random.choice(concentrations),
        ))
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        """INSERT INTO closeup.marca
        (codigo_marca, nombre_marca, laboratorio, principio_activo, forma_farmaceutica, concentracion)
        VALUES %s""",
        batch,
    )
    return NUM_CUP_BRANDS


def generate_mercados(cur):
    """Generate CloseUp markets."""
    batch = []
    for i, name in enumerate(THERAPEUTIC_CLASSES[:NUM_CUP_MARKETS], 1):
        batch.append((
            f"MER-{i:03d}",
            name,
            name[:10].upper(),
            name,
            f"/{name}/",
        ))
    # Fill remaining with generated names
    for i in range(len(THERAPEUTIC_CLASSES) + 1, NUM_CUP_MARKETS + 1):
        name = f"Mercado {fake.word().capitalize()}"
        batch.append((f"MER-{i:03d}", name, name[:10].upper(), name, f"/{name}/"))

    from psycopg2.extras import execute_values
    execute_values(
        cur,
        """INSERT INTO closeup.mercado
        (CDG_MERCADO, nombre_mercado, abreviatura, clase_terapeutica, path_tipo)
        VALUES %s""",
        batch,
    )
    return len(batch)


def generate_mercado_productos(cur):
    """Assign products to markets (each product in 1-2 markets)."""
    print("    Generating mercado_producto...")
    batch = []
    for brand_idx in range(1, NUM_CUP_BRANDS + 1):
        num_markets = random.choices([1, 2], weights=[0.7, 0.3], k=1)[0]
        markets = random.sample(range(1, NUM_CUP_MARKETS + 1), num_markets)
        for mkt_idx in markets:
            batch.append((
                f"MER-{mkt_idx:03d}",
                f"MK-{brand_idx:05d}",
                f"MK-{brand_idx:05d}",
                random.choice(LABS)[:20],
                "AR",
            ))
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        """INSERT INTO closeup.mercado_producto
        (CDG_MERCADO, CDG_PROD, codigo_marca, codigo_laboratorio, codigo_pais)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_prescripciones(cur, conn):
    """Generate prescription fact table (~3M rows) with Pareto distribution."""
    print("    Generating prescripciones (this may take a minute)...")

    today = date.today()
    start_date = today.replace(day=1) - timedelta(days=PRESCRIPTION_MONTHS * 30)

    # Pareto: 20% of doctors generate 80% of prescriptions
    doctor_weights = np.random.pareto(1.5, NUM_CUP_DOCTORS) + 1
    doctor_weights = doctor_weights / doctor_weights.sum()

    # Generate month-by-month
    batch = []
    batch_size = 50000
    total = 0
    rows_per_month = NUM_PRESCRIPTIONS // PRESCRIPTION_MONTHS

    for month_offset in tqdm(range(PRESCRIPTION_MONTHS), desc="    Months"):
        current_date = start_date + timedelta(days=month_offset * 30)
        year = current_date.year
        month = current_date.month

        # Pick doctors for this month (weighted by Pareto)
        num_active_docs = int(NUM_CUP_DOCTORS * 0.6)  # 60% active per month
        active_docs = np.random.choice(
            NUM_CUP_DOCTORS, size=num_active_docs, replace=False, p=doctor_weights
        )

        prescriptions_left = rows_per_month
        per_doc = max(1, prescriptions_left // num_active_docs)

        for doc_idx in active_docs:
            if prescriptions_left <= 0:
                break
            doc_id = f"CUP-{doc_idx + 1:06d}"
            num_px = random.randint(1, per_doc * 3)
            num_px = min(num_px, prescriptions_left)

            for _ in range(num_px):
                brand_idx = random.randint(1, NUM_CUP_BRANDS)
                cantidad = random.randint(1, 20)
                batch.append((
                    doc_id,
                    f"MK-{brand_idx:05d}",
                    f"MK-{brand_idx:05d}",
                    None,  # CDGMED_REG
                    random.choice(SPECIALTIES_CUP),
                    random.choice(REGIONS),
                    random.choice(LABS)[:20],
                    random.choice(THERAPEUTIC_CLASSES)[:20],
                    cantidad,
                    cantidad if random.random() > 0.3 else 0,  # px_farma
                    cantidad if random.random() > 0.8 else 0,  # px_delivery
                    date(year, month, random.randint(1, 28)),
                    "C",
                ))
                prescriptions_left -= 1

            if len(batch) >= batch_size:
                from psycopg2.extras import execute_values
                execute_values(
                    cur,
                    """INSERT INTO closeup.prescripcion
                    (CDGMED, CDGPRO, CDGMAR, CDGMED_REG, CDGESP1, CDGREG_PMIX,
                     CDGLAB, CDGCLA4, cantidad, px_farma, px_delivery, fecha, tipo_dom)
                    VALUES %s""",
                    batch,
                    page_size=5000,
                )
                total += len(batch)
                batch = []
                conn.commit()

    if batch:
        from psycopg2.extras import execute_values
        execute_values(
            cur,
            """INSERT INTO closeup.prescripcion
            (CDGMED, CDGPRO, CDGMAR, CDGMED_REG, CDGESP1, CDGREG_PMIX,
             CDGLAB, CDGCLA4, cantidad, px_farma, px_delivery, fecha, tipo_dom)
            VALUES %s""",
            batch,
            page_size=5000,
        )
        total += len(batch)
        conn.commit()

    return total


def generate_all(conn):
    """Generate all CloseUp data."""
    summary = {}
    with conn.cursor() as cur:
        print("  Generating CloseUp data...")
        summary["medico"] = generate_medicos(cur)
        conn.commit()
        summary["marca"] = generate_marcas(cur)
        conn.commit()
        summary["mercado"] = generate_mercados(cur)
        conn.commit()
        summary["mercado_producto"] = generate_mercado_productos(cur)
        conn.commit()
        summary["prescripcion"] = generate_prescripciones(cur, conn)

    return summary
