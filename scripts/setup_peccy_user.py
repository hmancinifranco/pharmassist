"""Setup Peccy demo user for PharmAssist.

Creates a third demo APM "Peccy" with:
- Cognito user (email + password from .env: PECCY_EMAIL / PECCY_PASSWORD)
- 12 médicos assigned across Palermo-Norte, Belgrano-Centro, Núñez-Centro
- Visitas from 2025-01 through 2026-12 (so the demo works any time of year)
- Visitas planificadas spread across the full year
- Birthdays distributed across all months

Usage:
    source .env
    python scripts/setup_peccy_user.py

Required env vars:
    AWS_REGION, USER_POOL_ID,
    MEDICOS_TABLE_NAME, VISITAS_TABLE_NAME, PLANIFICADAS_TABLE_NAME,
    PECCY_EMAIL, PECCY_PASSWORD
"""

import os
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

from dotenv import load_dotenv
import boto3

load_dotenv()


def _required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"ERROR: {name} is required in the environment (.env).")
        sys.exit(1)
    return val


REGION = _required("AWS_REGION")
PROFILE = os.environ.get("AWS_PROFILE")
USER_POOL_ID = _required("USER_POOL_ID")
MEDICOS_TABLE = _required("MEDICOS_TABLE_NAME")
VISITAS_TABLE = _required("VISITAS_TABLE_NAME")
PLANIFICADAS_TABLE = _required("PLANIFICADAS_TABLE_NAME")

session = boto3.Session(profile_name=PROFILE, region_name=REGION)
cognito = session.client("cognito-idp")
ddb = session.resource("dynamodb")

medicos_table = ddb.Table(MEDICOS_TABLE)
visitas_table = ddb.Table(VISITAS_TABLE)
planificadas_table = ddb.Table(PLANIFICADAS_TABLE)

APM_NAME = os.environ.get("PECCY_APM_ID", "Peccy")
APM_EMAIL = _required("PECCY_EMAIL")
APM_PASSWORD = _required("PECCY_PASSWORD")

# ─── Peccy's 12 médicos (new MNs that don't collide with existing data) ─

PECCY_MEDICOS = [
    {
        "Medico_MN": 550101, "Nombre": "Martín", "Apellido": "Kreutzer",
        "Mail": "martin.kreutzer@hospital.org.ar",
        "Telefono_Consultorio": "011-4501-2200",
        "Telefono_Celular": "+54 9 11 5501-1001",
        "Especialidad_Medica": "Gastroenterología",
        "Calle": "Av. Cabildo", "Altura": "2100", "Barrio": "Belgrano",
        "Zona": "Belgrano-Centro",
        "Fecha_Nacimiento": "1978-02-14",
        "Hobby_Intereses": "Vela, Fotografía",
        "Religion": "Católica", "Cadencia": "Mensual",
        "Hospital": "Hospital Alemán",
        "Facultad": "UBA – Facultad de Medicina", "Anio_Egresado": 2005,
        "Latitud": Decimal("-34.560200"), "Longitud": Decimal("-58.454100"),
    },
    {
        "Medico_MN": 550102, "Nombre": "Carolina", "Apellido": "Vidal",
        "Mail": "carolina.vidal@medicos.com.ar",
        "Telefono_Consultorio": "011-4502-3300",
        "Telefono_Celular": "+54 9 11 5502-2002",
        "Especialidad_Medica": "Dermatología",
        "Calle": "Av. Del Libertador", "Altura": "5800", "Barrio": "Belgrano",
        "Zona": "Belgrano-Centro",
        "Fecha_Nacimiento": "1985-05-22",
        "Hobby_Intereses": "Yoga, Pintura",
        "Religion": "No especifica", "Cadencia": "Trimestral",
        "Hospital": "Hospital Británico",
        "Facultad": "Universidad Austral – Medicina", "Anio_Egresado": 2012,
        "Latitud": Decimal("-34.558900"), "Longitud": Decimal("-58.452300"),
    },
    {
        "Medico_MN": 550103, "Nombre": "Rodrigo", "Apellido": "Estévez",
        "Mail": "rodrigo.estevez@outlook.com",
        "Telefono_Consultorio": "011-4503-4400",
        "Telefono_Celular": "+54 9 11 5503-3003",
        "Especialidad_Medica": "Neurología",
        "Calle": "Av. Monroe", "Altura": "3200", "Barrio": "Núñez",
        "Zona": "Núñez-Centro",
        "Fecha_Nacimiento": "1970-08-30",
        "Hobby_Intereses": "Ajedrez, Lectura",
        "Religion": "Judía", "Cadencia": "Mensual",
        "Hospital": "Hospital de Clínicas",
        "Facultad": "Universidad de Rosario – Medicina", "Anio_Egresado": 1998,
        "Latitud": Decimal("-34.545500"), "Longitud": Decimal("-58.455200"),
    },
    {
        "Medico_MN": 550104, "Nombre": "Luciana", "Apellido": "Paz",
        "Mail": "luciana.paz@gmail.com",
        "Telefono_Consultorio": "011-4504-5500",
        "Telefono_Celular": "+54 9 11 5504-4004",
        "Especialidad_Medica": "Psiquiatría",
        "Calle": "Av. Cabildo", "Altura": "4500", "Barrio": "Núñez",
        "Zona": "Núñez-Centro",
        "Fecha_Nacimiento": "1982-11-03",
        "Hobby_Intereses": "Running, Cine",
        "Religion": "Católica", "Cadencia": "Trimestral",
        "Hospital": "Hospital Pirovano",
        "Facultad": "Universidad Favaloro – Medicina", "Anio_Egresado": 2010,
        "Latitud": Decimal("-34.547800"), "Longitud": Decimal("-58.458900"),
    },
    {
        "Medico_MN": 550105, "Nombre": "Federico", "Apellido": "Mansilla",
        "Mail": "federico.mansilla@hospital.org.ar",
        "Telefono_Consultorio": "011-4505-6600",
        "Telefono_Celular": "+54 9 11 5505-5005",
        "Especialidad_Medica": "Clínica Médica",
        "Calle": "Av. Del Libertador", "Altura": "7200", "Barrio": "Núñez",
        "Zona": "Núñez-Centro",
        "Fecha_Nacimiento": "1975-04-17",
        "Hobby_Intereses": "Golf, Viajes",
        "Religion": "Evangélica", "Cadencia": "Semestral",
        "Hospital": "Sanatorio Güemes",
        "Facultad": "Universidad del Salvador – Medicina", "Anio_Egresado": 2003,
        "Latitud": Decimal("-34.543200"), "Longitud": Decimal("-58.452700"),
    },
    {
        "Medico_MN": 550106, "Nombre": "Valentina", "Apellido": "Quiroga",
        "Mail": "valentina.quiroga@yahoo.com.ar",
        "Telefono_Consultorio": "011-4506-7700",
        "Telefono_Celular": "+54 9 11 5506-6006",
        "Especialidad_Medica": "Pediatría",
        "Calle": "Av. Congreso", "Altura": "2800", "Barrio": "Belgrano",
        "Zona": "Belgrano-Centro",
        "Fecha_Nacimiento": "1990-07-09",
        "Hobby_Intereses": "Natación, Cocina",
        "Religion": "Otra", "Cadencia": "Mensual",
        "Hospital": "Hospital Garrahan",
        "Facultad": "UBA – Facultad de Medicina", "Anio_Egresado": 2017,
        "Latitud": Decimal("-34.562100"), "Longitud": Decimal("-58.456800"),
    },
    {
        "Medico_MN": 550107, "Nombre": "Gonzalo", "Apellido": "Rivas",
        "Mail": "gonzalo.rivas@medicos.com.ar",
        "Telefono_Consultorio": "011-4507-8800",
        "Telefono_Celular": "+54 9 11 5507-7007",
        "Especialidad_Medica": "Endocrinología",
        "Calle": "Av. Cabildo", "Altura": "3600", "Barrio": "Palermo",
        "Zona": "Palermo-Norte",
        "Fecha_Nacimiento": "1968-12-25",
        "Hobby_Intereses": "Tenis, Música",
        "Religion": "No especifica", "Cadencia": "Trimestral",
        "Hospital": "Hospital Italiano",
        "Facultad": "Hospital Italiano – Instituto Universitario", "Anio_Egresado": 1996,
        "Latitud": Decimal("-34.575600"), "Longitud": Decimal("-58.423100"),
    },
    {
        "Medico_MN": 550108, "Nombre": "Agustina", "Apellido": "Lozano",
        "Mail": "agustina.lozano@hotmail.com",
        "Telefono_Consultorio": "011-4508-9900",
        "Telefono_Celular": "+54 9 11 5508-8008",
        "Especialidad_Medica": "Ginecología",
        "Calle": "Av. Santa Fe", "Altura": "4900", "Barrio": "Palermo",
        "Zona": "Palermo-Norte",
        "Fecha_Nacimiento": "1987-01-28",
        "Hobby_Intereses": "Esquí, Jardinería",
        "Religion": "Católica", "Cadencia": "Semestral",
        "Hospital": "Hospital Fernández",
        "Facultad": "Universidad de Córdoba – Medicina", "Anio_Egresado": 2014,
        "Latitud": Decimal("-34.578200"), "Longitud": Decimal("-58.421500"),
    },
    {
        "Medico_MN": 550109, "Nombre": "Tomás", "Apellido": "Ibáñez",
        "Mail": "tomas.ibanez@hospital.org.ar",
        "Telefono_Consultorio": "011-4509-1100",
        "Telefono_Celular": "+54 9 11 5509-9009",
        "Especialidad_Medica": "Urología",
        "Calle": "Av. Libertador", "Altura": "6100", "Barrio": "Belgrano",
        "Zona": "Belgrano-Centro",
        "Fecha_Nacimiento": "1973-10-11",
        "Hobby_Intereses": "Pesca, Ciclismo",
        "Religion": "Judía", "Cadencia": "Mensual",
        "Hospital": "CEMIC",
        "Facultad": "Universidad de La Plata – Medicina", "Anio_Egresado": 2001,
        "Latitud": Decimal("-34.557400"), "Longitud": Decimal("-58.450600"),
    },
    {
        "Medico_MN": 550110, "Nombre": "Camila", "Apellido": "Duarte",
        "Mail": "camila.duarte@outlook.com",
        "Telefono_Consultorio": "011-4510-2200",
        "Telefono_Celular": "+54 9 11 5510-0010",
        "Especialidad_Medica": "Nutrición",
        "Calle": "Av. Triunvirato", "Altura": "4100", "Barrio": "Palermo",
        "Zona": "Palermo-Norte",
        "Fecha_Nacimiento": "1992-06-15",
        "Hobby_Intereses": "Yoga, Viajes, Lectura",
        "Religion": "No especifica", "Cadencia": "Trimestral",
        "Hospital": "Sanatorio Otamendi",
        "Facultad": "Universidad Maimónides – Medicina", "Anio_Egresado": 2019,
        "Latitud": Decimal("-34.576900"), "Longitud": Decimal("-58.424800"),
    },
    {
        "Medico_MN": 550111, "Nombre": "Sebastián", "Apellido": "Montes",
        "Mail": "sebastian.montes@gmail.com",
        "Telefono_Consultorio": "011-4511-3300",
        "Telefono_Celular": "+54 9 11 5511-1011",
        "Especialidad_Medica": "Traumatología",
        "Calle": "Av. Monroe", "Altura": "5500", "Barrio": "Núñez",
        "Zona": "Núñez-Centro",
        "Fecha_Nacimiento": "1980-03-06",
        "Hobby_Intereses": "Natación, Ajedrez",
        "Religion": "Católica", "Cadencia": "Semestral",
        "Hospital": "Hospital Austral",
        "Facultad": "Universidad Austral – Medicina", "Anio_Egresado": 2008,
        "Latitud": Decimal("-34.544100"), "Longitud": Decimal("-58.453400"),
    },
    {
        "Medico_MN": 550112, "Nombre": "María José", "Apellido": "Ferreyra",
        "Mail": "mjose.ferreyra@medicos.com.ar",
        "Telefono_Consultorio": "011-4512-4400",
        "Telefono_Celular": "+54 9 11 5512-2012",
        "Especialidad_Medica": "Infectología",
        "Calle": "Av. Del Libertador", "Altura": "4200", "Barrio": "Palermo",
        "Zona": "Palermo-Norte",
        "Fecha_Nacimiento": "1984-09-19",
        "Hobby_Intereses": "Ciclismo, Fotografía",
        "Religion": "Evangélica", "Cadencia": "Anual",
        "Hospital": "Hospital Posadas",
        "Facultad": "Universidad de Tucumán – Medicina", "Anio_Egresado": 2011,
        "Latitud": Decimal("-34.574300"), "Longitud": Decimal("-58.422000"),
    },
]

# Specialty → products mapping (from product_catalog.py)
ESPECIALIDAD_PRODUCTOS = {
    "Gastroenterología": ["ALACIR", "CIRUELAX MINITABS"],
    "Psiquiatría": ["APSICO", "PAMOXET"],
    "Dermatología": ["PANCUTAN NF", "TRIMACREM PLUS", "MENCOGRIN AP", "SUTRICO TAR", "TRICOPLUS"],
    "Ginecología": ["TRICOFIN", "TANVIMIL ACD"],
    "Clínica Médica": ["TANDIUR", "TIOCTAN", "CO-TIOCTAN", "TANVIMIL B1 B6 B12"],
    "Endocrinología": ["TIOCTAN", "CO-TIOCTAN", "TANVIMIL AMINOÁCIDOS"],
    "Neurología": ["APSICO", "PAMOXET", "ONEFIN"],
    "Urología": ["ONEFIN", "TACNA"],
    "Pediatría": ["TANVIMIL ACD", "TANVIMIL ACD FLUOR", "AEROGAL"],
    "Nutrición": ["TANVIMIL AMINOÁCIDOS", "TANVIMIL PLUS", "TANVIMIL B1 B6 B12"],
    "Infectología": ["TRICOFIN", "TACNA"],
    "Traumatología": ["TIOCTAN", "TANVIMIL B1 B6 B12"],
}

CADENCIA_DIAS = {
    "Mensual": 30, "Trimestral": 90, "Semestral": 180, "Anual": 365,
}

TIPOS_VISITA = ["Presencial", "Presencial", "Presencial", "Virtual", "Telefónica"]

NOTAS_TEMPLATES = [
    "Se entregó material informativo sobre {prod}. Buena recepción.",
    "El médico consultó sobre posología de {prod}. Se aclararon dudas.",
    "Visita de seguimiento. Se discutió eficacia de {prod} en pacientes.",
    "Se presentó nueva evidencia clínica de {prod}. Interés alto.",
    "Reunión productiva. Se abordaron beneficios de {prod}.",
    "Se revisaron casos clínicos con {prod}. Médico receptivo.",
    "Se coordinó charla informativa sobre {prod} para el equipo médico.",
    "El médico compartió experiencia positiva con {prod}.",
    "Se discutieron novedades de {prod}. Médico solicitó muestras.",
    "Presentación de {prod}. Se acordó seguimiento en próxima visita.",
]


# ─── Step 1: Create Cognito user ───────────────────────────────────────

def create_peccy_cognito():
    print(f"Creating Cognito user: {APM_EMAIL}")
    try:
        cognito.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=APM_EMAIL,
            UserAttributes=[
                {"Name": "email", "Value": APM_EMAIL},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:apm_id", "Value": APM_NAME},
            ],
            TemporaryPassword=APM_PASSWORD,
            MessageAction="SUPPRESS",
        )
        cognito.admin_set_user_password(
            UserPoolId=USER_POOL_ID,
            Username=APM_EMAIL,
            Password=APM_PASSWORD,
            Permanent=True,
        )
        print(f"  ✓ Cognito user created: {APM_EMAIL}")
    except cognito.exceptions.UsernameExistsException:
        print("  ⚠ User already exists, updating apm_id and password")
        cognito.admin_update_user_attributes(
            UserPoolId=USER_POOL_ID,
            Username=APM_EMAIL,
            UserAttributes=[{"Name": "custom:apm_id", "Value": APM_NAME}],
        )
        cognito.admin_set_user_password(
            UserPoolId=USER_POOL_ID,
            Username=APM_EMAIL,
            Password=APM_PASSWORD,
            Permanent=True,
        )
        print(f"  ✓ Updated existing user: {APM_EMAIL}")


# ─── Step 2: Insert médicos into DynamoDB ───────────────────────────────

def insert_peccy_medicos():
    print(f"Inserting {len(PECCY_MEDICOS)} médicos for Peccy...")
    count = 0
    for med in PECCY_MEDICOS:
        item = dict(med)
        item["APM"] = APM_NAME
        # Don't set Fecha_Ultima_Visita yet — will be set by visitas
        medicos_table.put_item(Item=item)
        count += 1
    print(f"  ✓ Inserted {count} médicos")


# ─── Step 3: Generate visitas (2025-01 through 2026-12) ────────────────

def generate_peccy_visitas():
    print("Generating visitas for Peccy (2025-01 → 2026-12)...")
    next_id = 100000  # High starting ID to avoid collisions
    count = 0
    ultima_visita = {}  # MN → latest date string

    for med in PECCY_MEDICOS:
        mn = med["Medico_MN"]
        zona = med["Zona"]
        esp = med["Especialidad_Medica"]
        cadencia = med["Cadencia"]
        intervalo = CADENCIA_DIAS.get(cadencia, 90)
        productos = ESPECIALIDAD_PRODUCTOS.get(esp, ["PAMOXET"])

        # Generate visits from 2025-01-15 through 2026-12-15
        current = date(2025, 1, 15)
        end = date(2026, 12, 15)

        while current <= end:
            # Add some jitter (±10 days)
            jitter = random.randint(-10, 10)
            visit_date = current + timedelta(days=jitter)
            # Clamp to valid range
            if visit_date < date(2025, 1, 1):
                visit_date = date(2025, 1, random.randint(5, 25))
            if visit_date > date(2026, 12, 28):
                visit_date = date(2026, 12, random.randint(1, 20))

            fecha_str = visit_date.isoformat()

            # Pick 1-3 products
            n_prods = min(random.randint(1, 3), len(productos))
            prods = random.sample(productos, n_prods)
            prods_str = "|".join(prods)

            nota = random.choice(NOTAS_TEMPLATES).format(prod=prods[0])

            visitas_table.put_item(Item={
                "Visita_ID": next_id,
                "APM": APM_NAME,
                "Medico_MN": mn,
                "Fecha_Visita": fecha_str,
                "Zona": zona,
                "Tipo_Visita": random.choice(TIPOS_VISITA),
                "Productos_Presentados": prods_str,
                "Notas": nota,
            })

            # Track latest visit per medico
            if mn not in ultima_visita or fecha_str > ultima_visita[mn]:
                ultima_visita[mn] = fecha_str

            next_id += 1
            count += 1
            current += timedelta(days=intervalo)

    print(f"  ✓ Created {count} visitas")

    # Update Fecha_Ultima_Visita on each medico
    print("  Updating Fecha_Ultima_Visita on médicos...")
    for mn, fecha in ultima_visita.items():
        medicos_table.update_item(
            Key={"Medico_MN": mn},
            UpdateExpression="SET Fecha_Ultima_Visita = :f",
            ExpressionAttributeValues={":f": fecha},
        )
    print(f"  ✓ Updated {len(ultima_visita)} médicos with Fecha_Ultima_Visita")


# ─── Step 4: Generate visitas planificadas (today → 2026-12) ───────────

def generate_peccy_planificadas():
    print("Generating visitas planificadas for Peccy...")
    today = date.today()
    end = date(2026, 12, 31)
    count = 0

    for med in PECCY_MEDICOS:
        mn = med["Medico_MN"]
        zona = med["Zona"]
        esp = med["Especialidad_Medica"]
        cadencia = med["Cadencia"]
        intervalo = CADENCIA_DIAS.get(cadencia, 90)
        productos = ESPECIALIDAD_PRODUCTOS.get(esp, ["PAMOXET"])

        # Start from today, generate future planned visits
        current = today + timedelta(days=random.randint(1, intervalo))

        while current <= end:
            fecha_str = current.isoformat()
            apm_fecha = f"{APM_NAME}#{fecha_str}"

            n_prods = min(random.randint(1, 2), len(productos))
            prods = random.sample(productos, n_prods)

            planificadas_table.put_item(Item={
                "APM_Fecha": apm_fecha,
                "Medico_MN": mn,
                "APM": APM_NAME,
                "Fecha_Planificada": fecha_str,
                "Zona": zona,
                "Tipo_Visita": random.choice(TIPOS_VISITA),
                "Productos_Sugeridos": "|".join(prods),
                "Estado": "Pendiente",
            })
            count += 1
            current += timedelta(days=intervalo + random.randint(-5, 5))

    print(f"  ✓ Created {count} visitas planificadas")


# ─── Main ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("PharmAssist — Setup Peccy Demo User")
    print("=" * 60)

    create_peccy_cognito()
    insert_peccy_medicos()
    generate_peccy_visitas()
    generate_peccy_planificadas()

    print("\n" + "=" * 60)
    print("Done! Peccy demo user ready:")
    print(f"  Email:    {APM_EMAIL}")
    print(f"  APM ID:   {APM_NAME}")
    print(f"  Médicos:  {len(PECCY_MEDICOS)}")
    print(f"  Zonas:    Belgrano-Centro, Núñez-Centro, Palermo-Norte")
    print("  (password from .env, not printed)")
    print("=" * 60)
