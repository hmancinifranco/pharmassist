"""Generate synthetic data for the IQVIA (market sales) schema."""
import random
from datetime import date

import numpy as np
from faker import Faker
from psycopg2.extras import execute_values
from tqdm import tqdm

from config import (
    NUM_IQVIA_PRODUCTS, NUM_IQVIA_LABS, NUM_IQVIA_GEOS,
    NUM_IQVIA_PERIODS, NUM_SALES_ROWS, RANDOM_SEED,
)

fake = Faker("es_AR")
Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

MONTH_NAMES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

DRUG_NAMES = [
    "Omeprazol", "Enalapril", "Atorvastatina", "Metformina", "Losartán",
    "Amlodipina", "Ibuprofeno", "Paracetamol", "Amoxicilina", "Azitromicina",
    "Diclofenac", "Ranitidina", "Ciprofloxacina", "Fluoxetina", "Alprazolam",
    "Clonazepam", "Levotiroxina", "Prednisona", "Dexametasona", "Insulina",
    "Salbutamol", "Budesonide", "Montelukast", "Warfarina", "Clopidogrel",
    "Simvastatina", "Rosuvastatina", "Valsartán", "Candesartán", "Bisoprolol",
]

FORMS = [
    "Comprimidos", "Cápsulas", "Suspensión oral", "Inyectable IM",
    "Inyectable IV", "Crema", "Gel", "Gotas", "Parches", "Supositorios",
    "Aerosol", "Polvo", "Solución oral", "Jarabe", "Óvulos",
]

LABS = [
    "Roemmers", "Bagó", "Gador", "Casasco", "Raffo", "Montpellier",
    "Bernabó", "Andrómaco", "Pfizer", "Roche", "Novartis", "Bayer",
    "AstraZeneca", "GSK", "Sanofi", "MSD", "Abbott", "Lilly",
    "Boehringer", "Servier", "Teva", "Sandoz", "Stada", "Ferring",
]

CLASSES = [
    "Antiulcerosos", "Antihipertensivos", "Hipolipemiantes", "Antidepresivos",
    "Ansiolíticos", "AINE", "Analgésicos", "Antibióticos", "Antidiabéticos",
    "Broncodilatadores", "Antihistamínicos", "Corticoides", "Anticoagulantes",
    "Diuréticos", "Antiepilépticos", "Antipsicóticos", "Tiroides",
    "Antiosteoporóticos", "Antifúngicos", "Antivirales",
]

GEOS = [
    "CABA Norte", "CABA Sur", "CABA Centro", "GBA Norte", "GBA Sur",
    "GBA Oeste", "La Plata", "Mar del Plata", "Córdoba Capital",
    "Córdoba Interior", "Rosario", "Santa Fe Interior", "Mendoza",
    "Tucumán", "Salta", "Neuquén", "Bahía Blanca", "San Juan",
    "Entre Ríos", "Misiones",
]


def generate_periodos(cur):
    """Generate period dimension (36 months)."""
    today = date.today()
    start_year = today.year - 3
    batch = []
    for i in range(NUM_IQVIA_PERIODS):
        year = start_year + i // 12
        month = (i % 12) + 1
        batch.append((
            f"{year}-{month:02d}",
            year, month,
            (month - 1) // 3 + 1,
            1 if month <= 6 else 2,
            MONTH_NAMES[month - 1],
        ))
    execute_values(
        cur,
        """INSERT INTO iqvia.dim_periodo
        (idPeriodo, anio, mes, trimestre, semestre, nombre_mes)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_drogas(cur):
    """Generate drug dimension."""
    batch = []
    for i, name in enumerate(DRUG_NAMES, 1):
        batch.append((f"DRG-{i:04d}", f"D{i:04d}", name))
    # Fill to reasonable size
    for i in range(len(DRUG_NAMES) + 1, 200):
        batch.append((f"DRG-{i:04d}", f"D{i:04d}", fake.word().capitalize()))
    execute_values(
        cur,
        "INSERT INTO iqvia.dim_droga (idDroga, codDroga, descripcion) VALUES %s",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_formas(cur):
    """Generate pharmaceutical form dimension."""
    batch = [(f"FRM-{i:03d}", f"F{i:03d}", None, name) for i, name in enumerate(FORMS, 1)]
    execute_values(
        cur,
        """INSERT INTO iqvia.dim_forma_farmaceutica
        (idForma, codFormaFarmaceutica, codNomenclatura, descripcion)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_laboratorios(cur):
    """Generate laboratory dimension."""
    batch = []
    for i, name in enumerate(LABS[:NUM_IQVIA_LABS], 1):
        tipo = "Nacional" if i <= 10 else "Multinacional"
        batch.append((f"LAB-{i:04d}", f"L{i:04d}", None, name))
    # Fill remaining
    for i in range(len(LABS) + 1, NUM_IQVIA_LABS + 1):
        batch.append((f"LAB-{i:04d}", f"L{i:04d}", None, f"Lab {fake.company()[:30]}"))
    execute_values(
        cur,
        """INSERT INTO iqvia.dim_laboratorio
        (idLaboratorio, codLaboratorio, codNomenclatura, descripcion)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_clases_terapeuticas(cur):
    """Generate therapeutic class dimension."""
    batch = []
    for i, name in enumerate(CLASSES, 1):
        batch.append((f"CLS-{i:03d}", f"C{i:03d}", None, name))
    execute_values(
        cur,
        """INSERT INTO iqvia.dim_clase_terapeutica
        (idClase, codClaseTerapeutica, adCodigoHeredado, descripcion)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_clases(cur):
    """Generate market class dimension (for fact table grouping)."""
    batch = []
    for i, name in enumerate(CLASSES, 1):
        batch.append((f"MC-{i:03d}", f"MC{i:03d}", name))
    execute_values(
        cur,
        "INSERT INTO iqvia.dim_clase (idClase, codClase, descripcion) VALUES %s",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_geografias(cur):
    """Generate geography dimension."""
    batch = []
    for i, name in enumerate(GEOS[:NUM_IQVIA_GEOS], 1):
        prov = name.split()[0] if " " in name else name
        batch.append((f"GEO-{i:03d}", name, prov, "Argentina", "Farmacias"))
    for i in range(len(GEOS) + 1, NUM_IQVIA_GEOS + 1):
        batch.append((f"GEO-{i:03d}", f"Zona {i}", "Interior", "Argentina", "Farmacias"))
    execute_values(
        cur,
        """INSERT INTO iqvia.dim_geografia
        (idGeografia, nombre, provincia, region, canal)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_presentaciones(cur):
    """Generate product/presentation dimension."""
    print("    Generating IQVIA presentaciones...")
    concentrations = ["5mg", "10mg", "20mg", "25mg", "50mg", "100mg", "200mg", "500mg"]
    batch = []
    for i in range(1, NUM_IQVIA_PRODUCTS + 1):
        drug_idx = (i % 199) + 1
        cls_idx = (i % len(CLASSES)) + 1
        conc = random.choice(concentrations)
        name = f"{fake.word().upper()} {conc} {random.choice(FORMS)}"
        batch.append((
            f"IQV-{i:06d}",
            f"P{i:06d}",
            name,
            f"EAN-{i:011d}" if random.random() > 0.3 else None,
            f"CLS-{cls_idx:03d}",
            None,  # idCombinacion
            None,  # fecha_lanzamiento
            conc,
        ))
    execute_values(
        cur,
        """INSERT INTO iqvia.dim_presentacion
        (idProducto, codigo, descripcion, adCodigoHeredado,
         idClaseTerapeutica, idCombinacion, fecha_lanzamiento, concentracion)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_rel_producto_laboratorio(cur):
    """Assign each product to a lab."""
    batch = []
    for i in range(1, NUM_IQVIA_PRODUCTS + 1):
        lab_idx = (i % NUM_IQVIA_LABS) + 1
        batch.append((f"IQV-{i:06d}", f"LAB-{lab_idx:04d}"))
    execute_values(
        cur,
        """INSERT INTO iqvia.rel_producto_laboratorio (idProducto, idLaboratorio)
        VALUES %s ON CONFLICT DO NOTHING""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_fact_mercado_valor(cur, conn):
    """Generate sales fact table (~2.5M rows) with seasonality."""
    print("    Generating fact_mercado_valor (this may take a minute)...")

    # Not all products sell in all geos in all periods
    # Realistic: ~70% of products active per period, ~30% of geos per product
    batch = []
    batch_size = 50000
    total = 0
    target = NUM_SALES_ROWS

    # Pre-compute period IDs
    today = date.today()
    start_year = today.year - 3
    periods = [f"{start_year + i//12}-{(i%12)+1:02d}" for i in range(NUM_IQVIA_PERIODS)]

    # Seasonality factors (winter = more respiratory, summer = less)
    seasonality = [0.9, 0.85, 0.95, 1.0, 1.05, 1.1, 1.15, 1.1, 1.05, 1.0, 0.95, 0.9]

    rows_per_period = target // NUM_IQVIA_PERIODS

    for period_idx, period_id in enumerate(tqdm(periods, desc="    Periods")):
        month = (period_idx % 12)
        season_factor = seasonality[month]

        # Pick active products for this period
        num_active = int(NUM_IQVIA_PRODUCTS * 0.7)
        active_products = random.sample(range(1, NUM_IQVIA_PRODUCTS + 1), num_active)

        rows_left = rows_per_period
        per_product = max(1, rows_left // num_active)

        for prod_idx in active_products:
            if rows_left <= 0:
                break
            # Each product sells in 2-8 geos
            num_geos = random.randint(2, min(8, NUM_IQVIA_GEOS))
            geos = random.sample(range(1, NUM_IQVIA_GEOS + 1), num_geos)
            cls_idx = (prod_idx % len(CLASSES)) + 1

            for geo_idx in geos:
                if rows_left <= 0:
                    break
                base_units = int(np.random.lognormal(5, 1.5))
                units = int(base_units * season_factor)
                valor = units * random.uniform(50, 5000)
                valor_usd = valor / random.uniform(800, 1200)
                dosis = units * random.uniform(0.5, 3.0)

                batch.append((
                    f"MC-{cls_idx:03d}",
                    f"IQV-{prod_idx:06d}",
                    period_id,
                    f"GEO-{geo_idx:03d}",
                    units,
                    round(dosis, 2),
                    round(valor, 2),
                    round(valor_usd, 2),
                ))
                rows_left -= 1

            if len(batch) >= batch_size:
                execute_values(
                    cur,
                    """INSERT INTO iqvia.fact_mercado_valor
                    (idClase, idProducto, idPeriodo, idGeografia, unidades, dosis, valor, valorUSD)
                    VALUES %s""",
                    batch,
                    page_size=5000,
                )
                total += len(batch)
                batch = []
                conn.commit()

    if batch:
        execute_values(
            cur,
            """INSERT INTO iqvia.fact_mercado_valor
            (idClase, idProducto, idPeriodo, idGeografia, unidades, dosis, valor, valorUSD)
            VALUES %s""",
            batch,
            page_size=5000,
        )
        total += len(batch)
        conn.commit()

    return total


def generate_all(conn):
    """Generate all IQVIA data."""
    summary = {}
    with conn.cursor() as cur:
        print("  Generating IQVIA data...")
        summary["dim_periodo"] = generate_periodos(cur)
        summary["dim_droga"] = generate_drogas(cur)
        summary["dim_forma"] = generate_formas(cur)
        summary["dim_laboratorio"] = generate_laboratorios(cur)
        summary["dim_clase_terapeutica"] = generate_clases_terapeuticas(cur)
        summary["dim_clase"] = generate_clases(cur)
        summary["dim_geografia"] = generate_geografias(cur)
        conn.commit()

        summary["dim_presentacion"] = generate_presentaciones(cur)
        conn.commit()

        summary["rel_producto_laboratorio"] = generate_rel_producto_laboratorio(cur)
        conn.commit()

        summary["fact_mercado_valor"] = generate_fact_mercado_valor(cur, conn)

    return summary
