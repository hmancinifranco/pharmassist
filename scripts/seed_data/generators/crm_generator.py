"""Generate synthetic data for the CRM interno schema."""
import random
from datetime import date, timedelta, datetime

import numpy as np
from faker import Faker
from psycopg2.extras import execute_values

from config import (
    NUM_APMS, NUM_DOCTORS, NUM_ZONES, NUM_SPECIALTIES,
    NUM_LINES, NUM_PRODUCTS, NUM_CYCLES, NUM_TAGS, RANDOM_SEED,
)

fake = Faker("es_AR")
Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# --- Argentine pharma domain data ---
SPECIALTIES = [
    "Clínica Médica", "Cardiología", "Gastroenterología", "Pediatría",
    "Ginecología", "Dermatología", "Neurología", "Traumatología",
    "Endocrinología", "Neumología", "Urología", "Oftalmología",
    "Otorrinolaringología", "Psiquiatría", "Reumatología", "Nefrología",
    "Oncología", "Hematología", "Infectología", "Geriatría",
    "Medicina Familiar", "Cirugía General", "Anestesiología",
    "Medicina Interna", "Diabetología",
]

ZONES_CABA = [
    "Belgrano", "Palermo", "Recoleta", "Caballito", "Flores",
    "Villa Urquiza", "Núñez", "Colegiales", "Almagro", "Barracas",
    "San Telmo", "La Boca", "Boedo", "Villa Crespo", "Coghlan",
]

ZONES_GBA = [
    "Vicente López", "San Isidro", "Tigre", "Pilar", "Morón",
    "Avellaneda", "Quilmes", "Lanús", "Lomas de Zamora", "La Plata",
    "San Martín", "Tres de Febrero", "Hurlingham", "Ituzaingó", "Merlo",
    "Moreno", "San Fernando", "Escobar", "Campana", "Zárate",
]

ZONES_INTERIOR = [
    "Córdoba Capital", "Rosario", "Mendoza Capital", "San Miguel de Tucumán",
    "Mar del Plata", "Salta Capital", "Santa Fe Capital", "San Juan Capital",
    "Resistencia", "Corrientes Capital", "Posadas", "Neuquén Capital",
    "Bahía Blanca", "Paraná", "Formosa Capital",
    "San Luis Capital", "Catamarca Capital", "La Rioja Capital",
    "Jujuy Capital", "Río Gallegos", "Ushuaia", "Rawson",
    "Viedma", "Santa Rosa", "Río Cuarto",
]

LINE_NAMES = [
    "Línea Cardio", "Línea Gastro", "Línea Neuro", "Línea Derma",
    "Línea Respiratoria", "Línea Dolor", "Línea Metabólica", "Línea Mujer",
]

PRODUCT_NAMES = [
    "PAMOXET", "ALACIR", "APSICO", "CARDIOLEX", "GASTROZEN",
    "NEUROMAX", "DERMAFIX", "RESPIRAL", "DOLOFEN", "METABIN",
    "FEMIVIT", "HEPATOL", "INMUNEX", "OSTEOFORT", "TIROIDIN",
    "ANXIOLIT", "COLESTOP", "DIABETIN", "HIPERTOL", "LIPIDEX",
]

CADENCIAS = ["Mensual", "Trimestral", "Semestral", "Anual", "Digital"]
CADENCIA_WEIGHTS = [0.15, 0.40, 0.25, 0.12, 0.08]

VISIT_TYPES = ["Presencial", "Virtual", "Telefonica"]
VISIT_TYPE_WEIGHTS = [0.70, 0.20, 0.10]

TAGS_HOBBIES = [
    ("Fútbol", "deporte"), ("Tenis", "deporte"), ("Golf", "deporte"),
    ("Running", "deporte"), ("Natación", "deporte"), ("Ciclismo", "deporte"),
    ("Lectura", "hobby"), ("Cine", "hobby"), ("Música", "hobby"),
    ("Cocina", "hobby"), ("Viajes", "hobby"), ("Fotografía", "hobby"),
    ("Vinos", "aficion"), ("Gastronomía", "aficion"), ("Arte", "aficion"),
    ("Teatro", "aficion"), ("Jardinería", "hobby"), ("Yoga", "deporte"),
    ("Paddle", "deporte"), ("Esquí", "deporte"), ("Pesca", "hobby"),
    ("Ajedrez", "hobby"), ("Pintura", "hobby"), ("Meditación", "hobby"),
    ("Senderismo", "deporte"), ("Rugby", "deporte"), ("Hockey", "deporte"),
    ("Básquet", "deporte"), ("Voley", "deporte"), ("Boxeo", "deporte"),
    ("Crossfit", "deporte"), ("Pilates", "deporte"), ("Danza", "hobby"),
    ("Escritura", "hobby"), ("Podcasts", "hobby"), ("Gaming", "hobby"),
    ("Coleccionismo", "hobby"), ("Astronomía", "hobby"),
    ("Voluntariado", "aficion"), ("Docencia", "aficion"),
]

CATEGORIES = [
    ("foco", "F", 1),
    ("hiperfoco", "HF", 2),
    ("recordatorio", "R", 3),
    ("lanzamiento", "L", 4),
]


def generate_zones(cur):
    """Generate zones."""
    from config import NUM_ZONES
    all_zones = []
    for i, name in enumerate(ZONES_CABA, 1):
        all_zones.append((f"Z-{i:03d}", name, "CABA", "Buenos Aires"))
    for i, name in enumerate(ZONES_GBA, len(ZONES_CABA) + 1):
        all_zones.append((f"Z-{i:03d}", name, "GBA", "Buenos Aires"))
    for i, name in enumerate(ZONES_INTERIOR, len(ZONES_CABA) + len(ZONES_GBA) + 1):
        prov = name.replace(" Capital", "")
        all_zones.append((f"Z-{i:03d}", name, "Interior", prov))

    # Trim to NUM_ZONES
    all_zones = all_zones[:NUM_ZONES]

    execute_values(
        cur,
        "INSERT INTO crm_interno.zona (codigo, nombre, region, provincia) VALUES %s",
        all_zones,
        page_size=1000,
    )
    return len(all_zones)


def generate_specialties(cur):
    """Generate medical specialties."""
    from config import NUM_SPECIALTIES
    data = [(f"ESP-{i:03d}", name) for i, name in enumerate(SPECIALTIES[:NUM_SPECIALTIES], 1)]
    execute_values(
        cur,
        "INSERT INTO crm_interno.especialidad (codigo, nombre) VALUES %s",
        data,
        page_size=1000,
    )
    return len(data)


def generate_tags(cur):
    """Generate tags/hobbies."""
    data = [(name, tipo, True) for name, tipo in TAGS_HOBBIES[:NUM_TAGS]]
    execute_values(
        cur,
        "INSERT INTO crm_interno.tag (nombre, tipo, activo) VALUES %s",
        data,
        page_size=1000,
    )
    return len(data)


def generate_apms(cur, num_zones):
    """Generate APMs."""
    from config import NUM_APMS
    apms = []
    for i in range(1, NUM_APMS + 1):
        apms.append((
            f"APM-{i:03d}",
            fake.first_name(),
            fake.last_name(),
            fake.email(),
            fake.phone_number()[:20],
            random.randint(1, num_zones),
            None,
            True,
            fake.date_between(start_date="-10y", end_date="-1y"),
        ))
    execute_values(
        cur,
        """INSERT INTO crm_interno.apm
        (codigo, nombre, apellido, email, telefono, zona_id, gerente_id, activo, fecha_ingreso)
        VALUES %s""",
        apms,
        page_size=1000,
    )
    # Set some gerente_ids (first 5 APMs are managers)
    for i in range(6, NUM_APMS + 1):
        gerente = random.randint(1, min(5, NUM_APMS))
        cur.execute(
            "UPDATE crm_interno.apm SET gerente_id = %s WHERE id = %s",
            (gerente, i),
        )
    return NUM_APMS


def generate_doctors(cur, num_zones, num_specialties):
    """Generate doctors."""
    from config import NUM_DOCTORS
    doctors = []
    for i in range(1, NUM_DOCTORS + 1):
        cadencia = random.choices(CADENCIAS, weights=CADENCIA_WEIGHTS, k=1)[0]
        doctors.append((
            f"MN-{i:06d}",
            fake.first_name(),
            fake.last_name(),
            fake.email() if random.random() > 0.3 else None,
            fake.phone_number()[:20],
            fake.phone_number()[:20] if random.random() > 0.5 else None,
            random.randint(1, num_specialties),
            random.randint(1, num_zones),
            fake.street_address()[:200],
            fake.company()[:100] if random.random() > 0.4 else None,
            random.choice(["UBA", "UNC", "UNR", "UNLP", "UNT", None]),
            None,
            fake.date_of_birth(minimum_age=30, maximum_age=70),
            cadencia,
            True,
            round(random.uniform(-34.7, -34.5), 7),
            round(random.uniform(-58.5, -58.3), 7),
        ))
    execute_values(
        cur,
        """INSERT INTO crm_interno.doctor
        (matricula_nacional, nombre, apellido, email, telefono1, telefono2,
         especialidad_id, zona_id, direccion, hospital, facultad, intereses,
         fecha_nacimiento, cadencia, activo, latitud, longitud)
        VALUES %s""",
        doctors,
        page_size=1000,
    )
    return NUM_DOCTORS


def generate_tag_doctors(cur):
    """Assign 1-3 tags to each doctor."""
    data = []
    for doc_id in range(1, NUM_DOCTORS + 1):
        num_tags = random.randint(1, 3)
        tags = random.sample(range(1, NUM_TAGS + 1), min(num_tags, NUM_TAGS))
        for tag_id in tags:
            data.append((tag_id, doc_id))
    execute_values(
        cur,
        "INSERT INTO crm_interno.tag_doctor (tag_id, doctor_id) VALUES %s ON CONFLICT DO NOTHING",
        data,
        page_size=1000,
    )
    return len(data)


def generate_lines(cur):
    """Generate product lines."""
    from config import NUM_LINES
    data = [(f"LIN-{i:02d}", name, name[:3].upper()) for i, name in enumerate(LINE_NAMES[:NUM_LINES], 1)]
    execute_values(
        cur,
        "INSERT INTO crm_interno.linea (codigo, nombre, abreviatura) VALUES %s",
        data,
        page_size=1000,
    )
    return len(data)


def generate_linea_apm(cur):
    """Assign 2-4 lines to each APM."""
    data = []
    for apm_id in range(1, NUM_APMS + 1):
        num_lines = random.randint(2, 4)
        lines = random.sample(range(1, NUM_LINES + 1), num_lines)
        for linea_id in lines:
            data.append((apm_id, linea_id))
    execute_values(
        cur,
        "INSERT INTO crm_interno.linea_apm (apm_id, linea_id) VALUES %s ON CONFLICT DO NOTHING",
        data,
        page_size=1000,
    )
    return len(data)


def generate_products(cur):
    """Generate product families."""
    products = []
    for i in range(1, NUM_PRODUCTS + 1):
        base_name = PRODUCT_NAMES[i % len(PRODUCT_NAMES)]
        concentration = random.choice(["5mg", "10mg", "20mg", "50mg", "100mg", "200mg", "500mg"])
        form = random.choice(["Comp x 30", "Comp x 60", "Caps x 20", "Susp 120ml", "Amp x 5"])
        products.append((
            f"SKU-{i:04d}",
            f"{base_name} {concentration} {form}",
            base_name[:8],
            fake.sentence(nb_words=4),
            fake.word(),
            random.randint(1, NUM_LINES),
            random.choice(["OTC", "RX"]),
            form,
            True,
        ))
    execute_values(
        cur,
        """INSERT INTO crm_interno.familia_producto
        (codigo, nombre, nombre_corto, descripcion, principio_activo,
         linea_id, tipo, presentacion, activo)
        VALUES %s""",
        products,
        page_size=1000,
    )
    return NUM_PRODUCTS


def generate_categories(cur):
    """Generate promotion categories."""
    for nombre, abrev, orden in CATEGORIES:
        cur.execute(
            "INSERT INTO crm_interno.categoria (nombre, abreviatura, orden) VALUES (%s, %s, %s)",
            (nombre, abrev, orden),
        )
    return len(CATEGORIES)


def generate_cycles(cur):
    """Generate promotion cycles (last 3 years, semesters)."""
    cycles = []
    start_year = 2024
    for i in range(NUM_CYCLES):
        year = start_year + i // 2
        semester = (i % 2) + 1
        start = date(year, 1 if semester == 1 else 7, 1)
        end = date(year, 6, 30) if semester == 1 else date(year, 12, 31)
        name = f"Ciclo {year}-S{semester}"
        is_active = (i == NUM_CYCLES - 1)  # last one is active
        cycles.append((name, start, end, is_active))
    execute_values(
        cur,
        "INSERT INTO crm_interno.ciclo (nombre, fecha_inicio, fecha_fin, activo) VALUES %s",
        cycles,
        page_size=1000,
    )
    return NUM_CYCLES


def generate_grillas(cur):
    """Generate grillas (one per line per cycle)."""
    grillas = []
    for linea_id in range(1, NUM_LINES + 1):
        for ciclo_idx in range(NUM_CYCLES):
            grillas.append((
                f"GR-L{linea_id}-C{ciclo_idx+1}",
                f"Grilla Línea {linea_id} Ciclo {ciclo_idx+1}",
                linea_id,
            ))
    execute_values(
        cur,
        "INSERT INTO crm_interno.grilla (abreviatura, nombre, linea_id) VALUES %s",
        grillas,
        page_size=1000,
    )
    return len(grillas)


def generate_detalle_promocion(cur):
    """Generate promotion details (products in grillas with categories)."""
    # Get active cycle
    cur.execute("SELECT id FROM crm_interno.ciclo WHERE activo = true LIMIT 1")
    active_cycle_id = cur.fetchone()[0]

    # Get all grillas
    cur.execute("SELECT id, linea_id FROM crm_interno.grilla")
    grillas = cur.fetchall()

    data = []
    for grilla_id, linea_id in grillas:
        # Get products for this line
        cur.execute(
            "SELECT id FROM crm_interno.familia_producto WHERE linea_id = %s",
            (linea_id,),
        )
        products = [r[0] for r in cur.fetchall()]
        if not products:
            continue

        # Assign 3-8 products per grilla with categories
        num_prods = min(random.randint(3, 8), len(products))
        selected = random.sample(products, num_prods)
        for prod_id in selected:
            cat_id = random.choices([1, 2, 3, 4], weights=[0.3, 0.2, 0.4, 0.1], k=1)[0]
            data.append((prod_id, grilla_id, cat_id, active_cycle_id, "activo", "activo"))

    execute_values(
        cur,
        """INSERT INTO crm_interno.detalle_promocion_producto
        (familia_producto_id, grilla_id, categoria_id, ciclo_id, estado_ciclo, estado_grilla)
        VALUES %s""",
        data,
        page_size=1000,
    )
    return len(data)


def generate_cartera_medica(cur):
    """Assign ~60 doctors to each APM."""
    data = []
    doctors_per_apm = NUM_DOCTORS // NUM_APMS
    doctor_ids = list(range(1, NUM_DOCTORS + 1))
    random.shuffle(doctor_ids)

    for apm_id in range(1, NUM_APMS + 1):
        start = (apm_id - 1) * doctors_per_apm
        end = start + doctors_per_apm
        assigned = doctor_ids[start:end]
        for doc_id in assigned:
            data.append((
                apm_id, doc_id,
                fake.date_between(start_date="-3y", end_date="-6m"),
                True,
            ))

    execute_values(
        cur,
        """INSERT INTO crm_interno.cartera_medica (apm_id, doctor_id, fecha_creacion, activa)
        VALUES %s ON CONFLICT DO NOTHING""",
        data,
        page_size=1000,
    )
    return len(data)


def generate_agenda(cur):
    """Generate visit history."""
    from config import NUM_DOCTORS, NUM_APMS
    print("    Generating agenda (visits)...")
    today = date.today()
    start_date = today - timedelta(days=365)  # 1 year back for light mode

    # Get cartera assignments
    cur.execute("SELECT apm_id, doctor_id FROM crm_interno.cartera_medica WHERE activa = true")
    carteras = cur.fetchall()

    batch = []
    total = 0

    for apm_id, doctor_id in carteras:
        # Each doctor gets 2-6 visits over 1 year in light mode
        num_visits = random.randint(2, 6)
        for _ in range(num_visits):
            visit_date = fake.date_between(start_date=start_date, end_date=today)
            hour = random.randint(8, 18)
            start_dt = datetime(visit_date.year, visit_date.month, visit_date.day, hour, 0)
            end_dt = start_dt + timedelta(minutes=random.randint(10, 45))
            tipo = random.choices(VISIT_TYPES, weights=VISIT_TYPE_WEIGHTS, k=1)[0]
            inactivo = random.random() < 0.02
            exitosa = random.random() > 0.05

            batch.append((
                apm_id, doctor_id, start_dt, end_dt, None,
                random.choice(["Mañana", "Tarde"]),
                tipo, None, inactivo, exitosa,
            ))

    # Single bulk insert using execute_values for speed
    execute_values(
        cur,
        """INSERT INTO crm_interno.agenda
        (apm_id, doctor_id, fecha_inicio, fecha_fin, descripcion,
         turno, tipo_visita, zona_id, inactivo, visita_exitosa)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    total = len(batch)

    return total


def generate_agenda_producto(cur):
    """Assign 1-4 products to each visit."""
    print("    Generating agenda_producto...")
    cur.execute("SELECT id, apm_id FROM crm_interno.agenda")
    agendas = cur.fetchall()

    # Get products per line per APM
    cur.execute("""
        SELECT la.apm_id, fp.id
        FROM crm_interno.linea_apm la
        JOIN crm_interno.familia_producto fp ON fp.linea_id = la.linea_id
    """)
    apm_products = {}
    for apm_id, prod_id in cur.fetchall():
        apm_products.setdefault(apm_id, []).append(prod_id)

    batch = []

    for agenda_id, apm_id in agendas:
        products = apm_products.get(apm_id, [])
        if not products:
            continue
        num_prods = random.randint(1, min(4, len(products)))
        selected = random.sample(products, num_prods)
        for orden, prod_id in enumerate(selected, 1):
            batch.append((agenda_id, prod_id, orden))

    execute_values(
        cur,
        "INSERT INTO crm_interno.agenda_producto (agenda_id, familia_producto_id, orden) VALUES %s",
        batch,
        page_size=1000,
    )

    return len(batch)


def generate_all(conn):
    """Generate all CRM data. Returns summary dict."""
    summary = {}
    with conn.cursor() as cur:
        print("  Generating CRM interno data...")
        summary["zona"] = generate_zones(cur)
        summary["especialidad"] = generate_specialties(cur)
        summary["tag"] = generate_tags(cur)
        summary["apm"] = generate_apms(cur, summary["zona"])
        summary["doctor"] = generate_doctors(cur, summary["zona"], summary["especialidad"])
        summary["tag_doctor"] = generate_tag_doctors(cur)
        summary["linea"] = generate_lines(cur)
        summary["linea_apm"] = generate_linea_apm(cur)
        summary["familia_producto"] = generate_products(cur)
        summary["categoria"] = generate_categories(cur)
        summary["ciclo"] = generate_cycles(cur)
        summary["grilla"] = generate_grillas(cur)
        summary["detalle_promocion"] = generate_detalle_promocion(cur)
        summary["cartera_medica"] = generate_cartera_medica(cur)
        conn.commit()

        summary["agenda"] = generate_agenda(cur)
        conn.commit()

        summary["agenda_producto"] = generate_agenda_producto(cur)
        conn.commit()

    return summary
