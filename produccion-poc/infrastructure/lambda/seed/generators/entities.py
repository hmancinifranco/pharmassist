"""
Generadores de tablas dependientes (entidades con FKs a catálogos).

Genera datos realistas para:
- apm (200 registros) — APMs con nombres argentinos, FK a linea
- doctor (30,000 registros) — Médicos con matrícula única, FKs a especialidad/loyalty
- linea_apm (~300 registros) — Asignaciones APM ↔ línea (1-2 líneas por APM)
- datos_visita (25,000 registros) — Frecuencia de visita + FK a institución
- cartera_medica (25,000 registros) — Relación APM ↔ doctor ↔ datos_visita

Todas las funciones reciben DataFrames o listas de IDs de tablas padre
para garantizar integridad referencial (FKs válidas).
Retornan list[tuple] listos para INSERT.
Usan random con seed fijo (42) para reproducibilidad.

IDs generados con formato VARCHAR:
- APM: "APM_001" ... "APM_200"
- Doctor: "DOC_00001" ... "DOC_30000"
- linea_apm: "LA_001" ... "LA_300"
- datos_visita: "DV_00001" ... "DV_25000"
- cartera_medica: "CM_00001" ... "CM_25000"
"""

import random

# Seed fijo para reproducibilidad
random.seed(42)


# =============================================================================
# DATOS REALISTAS — Nombres y apellidos argentinos
# =============================================================================

_NOMBRES_MASCULINOS = [
    "Juan", "Carlos", "Miguel", "José", "Pedro", "Martín", "Lucas",
    "Nicolás", "Matías", "Alejandro", "Diego", "Fernando", "Andrés",
    "Sebastián", "Pablo", "Gabriel", "Gonzalo", "Facundo", "Ignacio",
    "Federico", "Ramiro", "Tomás", "Agustín", "Maximiliano", "Leonardo",
    "Santiago", "Emiliano", "Franco", "Rodrigo", "Ezequiel",
]

_NOMBRES_FEMENINOS = [
    "María", "Laura", "Ana", "Carolina", "Valentina", "Sofía", "Camila",
    "Luciana", "Florencia", "Daniela", "Gabriela", "Julieta", "Romina",
    "Natalia", "Soledad", "Mariana", "Paula", "Andrea", "Cecilia",
    "Victoria", "Celeste", "Micaela", "Milagros", "Agustina", "Antonella",
    "Rocío", "Belén", "Marina", "Silvina", "Lorena",
]

# Mezcla de apellidos españoles e italianos (realista para Argentina)
_APELLIDOS = [
    "González", "Rodríguez", "López", "Martínez", "García", "Fernández",
    "Pérez", "Sánchez", "Ramírez", "Torres", "Díaz", "Álvarez",
    "Romero", "Ruiz", "Gutiérrez", "Moreno", "Muñoz", "Ortiz",
    "Jiménez", "Castro", "Vargas", "Ramos", "Herrera", "Medina",
    "Acosta", "Flores", "Ríos", "Suárez", "Reyes", "Cruz",
    "Molina", "Peralta", "Cabrera", "Sosa", "Rojas", "Méndez",
    "Vega", "Cardozo", "Aguirre", "Domínguez", "Morales", "Navarro",
    "Blanco", "Giménez", "Ledesma", "Figueroa", "Contreras", "Luna",
    # Italianos (frecuentes en Argentina)
    "Rossi", "Russo", "Ferrari", "Bianchi", "Romano", "Colombo",
    "Ricci", "Marino", "Greco", "Bruno", "Gallo", "Conti",
    "De Luca", "Mancini", "Costa", "Lombardi", "Moretti", "Barbieri",
]

_FRECUENCIAS = ["Mensual", "Trimestral", "Semestral", "Anual"]
_FRECUENCIA_PESOS = [0.30, 0.40, 0.20, 0.10]

# Categorías de doctor (categoría interna del laboratorio)
_CATEGORIAS_DOCTOR = ["A", "B", "C", "D", "E"]
_CATEGORIA_PESOS = [0.10, 0.20, 0.35, 0.25, 0.10]


# =============================================================================
# HELPERS
# =============================================================================


def _random_nombre() -> str:
    """Retorna un nombre de pila argentino aleatorio (M o F)."""
    if random.random() < 0.5:
        return random.choice(_NOMBRES_MASCULINOS)
    return random.choice(_NOMBRES_FEMENINOS)


def _random_apellido() -> str:
    """Retorna un apellido argentino aleatorio (español o italiano)."""
    return random.choice(_APELLIDOS)


def _generate_email(nombre: str, apellido: str, dominio: str) -> str:
    """Genera email a partir de nombre y apellido."""
    nombre_clean = nombre.lower().replace("á", "a").replace("é", "e") \
        .replace("í", "i").replace("ó", "o").replace("ú", "u") \
        .replace("ñ", "n").replace(" ", "")
    apellido_clean = apellido.lower().replace("á", "a").replace("é", "e") \
        .replace("í", "i").replace("ó", "o").replace("ú", "u") \
        .replace("ñ", "n").replace(" ", "")
    sufijo = random.randint(1, 99)
    return f"{nombre_clean}.{apellido_clean}{sufijo}@{dominio}"


# =============================================================================
# APM — 200 APMs
# DDL: id VARCHAR(20) PK, "primerNombre", "primerApellido", email,
#      id_linea FK→linea, gerente_regional_id, "codigoPromotor", inactivo
# =============================================================================


def generate_apms(linea_ids: list[str], n: int = 200) -> list[tuple]:
    """
    Genera 200 APMs (Agentes de Propaganda Médica).

    Args:
        linea_ids: list de IDs VARCHAR de la tabla linea (ej: ["LIN_01", ...]).
        n: cantidad de APMs a generar (default 200).

    Retorna: list[(id, primerNombre, primerApellido, email, id_linea,
                   gerente_regional_id, codigoPromotor, inactivo)]

    Reglas:
    - ID formato "APM_001" a "APM_200"
    - id_linea distribuido round-robin entre las líneas disponibles
    - ~5% inactivo=True
    - gerente_regional_id: IDs ficticios "GR_01" a "GR_10" (10 gerentes)
    - codigoPromotor: código numérico único por APM
    """
    n_lineas = len(linea_ids)
    gerentes = [f"GR_{i:02d}" for i in range(1, 11)]  # 10 gerentes regionales
    apms: list[tuple] = []

    for i in range(n):
        apm_id = f"APM_{i + 1:03d}"
        nombre = _random_nombre()
        apellido = _random_apellido()
        email = _generate_email(nombre, apellido, "example.com")
        id_linea = linea_ids[i % n_lineas]
        gerente_id = random.choice(gerentes)
        codigo_promotor = f"{10000 + i}"
        inactivo = random.random() < 0.05  # 5% inactivos

        apms.append((
            apm_id, nombre, apellido, email, id_linea,
            gerente_id, codigo_promotor, inactivo,
        ))

    return apms


# =============================================================================
# DOCTOR — 30,000 médicos
# DDL: id VARCHAR(20) PK, "primerNombre", "primerApellido",
#      "matriculaNacional" VARCHAR(20), especialidad_id FK→especialidad,
#      loyalty_id FK→loyalty_doctor, categoria_id VARCHAR(10), inactivo
# =============================================================================


def generate_doctors(
    especialidad_ids: list[str],
    loyalty_ids: list[str],
    n: int = 30_000,
) -> list[tuple]:
    """
    Genera 30,000 médicos con datos realistas argentinos.

    Args:
        especialidad_ids: list de IDs VARCHAR de especialidad.
        loyalty_ids: list de IDs VARCHAR de loyalty_doctor.
        n: cantidad de doctores (default 30,000).

    Retorna: list[(id, primerNombre, primerApellido, matriculaNacional,
                   especialidad_id, loyalty_id, categoria_id, inactivo)]

    Reglas:
    - ID formato "DOC_00001" a "DOC_30000"
    - matriculaNacional UNIQUE, formato 6 dígitos: "100001" a "130000"
    - especialidad_id: distribución no uniforme (primeras 10 más frecuentes)
    - loyalty_id: distribución piramidal (Platino 5%, Oro 15%, Plata 30%, Bronce 35%, Nuevo 15%)
    - categoria_id: A/B/C/D/E según pesos definidos
    - ~5% inactivo=True
    - Nombres mezcla española/italiana (realista Argentina)
    """
    n_especialidades = len(especialidad_ids)
    n_loyalties = len(loyalty_ids)

    # Pesos para especialidades (las primeras 10 son más comunes)
    esp_pesos = [3.0] * min(10, n_especialidades) + [1.0] * max(0, n_especialidades - 10)
    total_peso = sum(esp_pesos)
    esp_pesos = [p / total_peso for p in esp_pesos]

    # Pesos para loyalty: Platino(5%), Oro(15%), Plata(30%), Bronce(35%), Nuevo(15%)
    loyalty_pesos = [0.05, 0.15, 0.30, 0.35, 0.15]
    # Ajustar si hay diferente cantidad de loyalties
    if n_loyalties != 5:
        loyalty_pesos = [1.0 / n_loyalties] * n_loyalties

    doctors: list[tuple] = []

    for i in range(n):
        doctor_id = f"DOC_{i + 1:05d}"
        nombre = _random_nombre()
        apellido = _random_apellido()
        matricula = f"{100001 + i}"  # 6 dígitos únicos

        # FK especialidad con distribución ponderada
        especialidad_id = random.choices(especialidad_ids, weights=esp_pesos, k=1)[0]

        # FK loyalty con distribución piramidal
        loyalty_id = random.choices(loyalty_ids, weights=loyalty_pesos, k=1)[0]

        # Categoría interna (A-E)
        categoria_id = random.choices(_CATEGORIAS_DOCTOR, weights=_CATEGORIA_PESOS, k=1)[0]

        # ~5% inactivos
        inactivo = random.random() < 0.05

        doctors.append((
            doctor_id, nombre, apellido, matricula,
            especialidad_id, loyalty_id, categoria_id, inactivo,
        ))

    return doctors


# =============================================================================
# LINEA_APM — ~300 asignaciones APM ↔ línea
# DDL: id VARCHAR(20) PK, id_apm FK→apm, id_linea FK→linea
# =============================================================================


def generate_linea_apm(
    apm_ids: list[str],
    linea_ids: list[str],
    target: int = 300,
) -> list[tuple]:
    """
    Genera ~300 asignaciones de APMs a líneas.

    Args:
        apm_ids: list de IDs VARCHAR de APMs (ej: ["APM_001", ...]).
        linea_ids: list de IDs VARCHAR de líneas (ej: ["LIN_01", ...]).
        target: cantidad objetivo de asignaciones (default 300).

    Retorna: list[(id, id_apm, id_linea)]

    Reglas:
    - Cada APM tiene al menos 1 línea asignada
    - ~50% de APMs tienen una segunda línea
    - No hay duplicados (mismo APM+linea no se repite)
    - ID formato "LA_001" a "LA_300"
    """
    n_lineas = len(linea_ids)
    asignaciones: list[tuple] = []
    used_pairs: set = set()
    counter = 0

    # Primero: cada APM tiene al menos 1 línea (round-robin)
    for idx, apm_id in enumerate(apm_ids):
        linea_id = linea_ids[idx % n_lineas]
        pair = (apm_id, linea_id)
        if pair not in used_pairs:
            used_pairs.add(pair)
            counter += 1
            la_id = f"LA_{counter:03d}"
            asignaciones.append((la_id, apm_id, linea_id))

    # Segundo: agregar segunda línea a APMs aleatorios hasta llegar al target
    shuffled_apms = list(apm_ids)
    random.shuffle(shuffled_apms)

    for apm_id in shuffled_apms:
        if len(asignaciones) >= target:
            break
        # Elegir una línea aleatoria diferente
        linea_id = random.choice(linea_ids)
        pair = (apm_id, linea_id)
        if pair not in used_pairs:
            used_pairs.add(pair)
            counter += 1
            la_id = f"LA_{counter:03d}"
            asignaciones.append((la_id, apm_id, linea_id))

    # Rellenar si faltan
    while len(asignaciones) < target:
        apm_id = random.choice(apm_ids)
        linea_id = random.choice(linea_ids)
        pair = (apm_id, linea_id)
        if pair not in used_pairs:
            used_pairs.add(pair)
            counter += 1
            la_id = f"LA_{counter:03d}"
            asignaciones.append((la_id, apm_id, linea_id))

    return asignaciones[:target]


# =============================================================================
# DATOS_VISITA — 25,000 registros
# DDL: id VARCHAR(20) PK, frecuencia VARCHAR(20), institucion_id FK→institucion
# =============================================================================


def generate_datos_visita(
    institucion_ids: list[str],
    n: int = 25_000,
) -> list[tuple]:
    """
    Genera 25,000 registros de datos de visita (frecuencia + institución).

    Args:
        institucion_ids: list de IDs VARCHAR de instituciones.
        n: cantidad de registros (default 25,000).

    Retorna: list[(id, frecuencia, institucion_id)]

    Reglas:
    - ID formato "DV_00001" a "DV_25000"
    - frecuencia: Mensual(30%), Trimestral(40%), Semestral(20%), Anual(10%)
    - institucion_id: selección aleatoria de instituciones existentes
    """
    datos: list[tuple] = []

    for i in range(n):
        dv_id = f"DV_{i + 1:05d}"
        frecuencia = random.choices(_FRECUENCIAS, weights=_FRECUENCIA_PESOS, k=1)[0]
        institucion_id = random.choice(institucion_ids)
        datos.append((dv_id, frecuencia, institucion_id))

    return datos


# =============================================================================
# CARTERA_MEDICA — 25,000 relaciones APM ↔ doctor ↔ datos_visita
# DDL: id VARCHAR(20) PK, apm_id FK→apm, doctor_id FK→doctor,
#      datos_visita_id FK→datos_visita, inactivo BOOLEAN DEFAULT false
# =============================================================================


def generate_cartera_medica(
    apm_ids: list[str],
    doctor_ids: list[str],
    datos_visita_ids: list[str],
    n: int = 25_000,
) -> list[tuple]:
    """
    Genera 25,000 registros de cartera médica (asignación APM ↔ doctor).

    Args:
        apm_ids: list de IDs VARCHAR de APMs (ej: ["APM_001", ...]).
        doctor_ids: list de IDs VARCHAR de doctores (ej: ["DOC_00001", ...]).
        datos_visita_ids: list de IDs VARCHAR de datos_visita (ej: ["DV_00001", ...]).
        n: cantidad de registros (default 25,000).

    Retorna: list[(id, apm_id, doctor_id, datos_visita_id, inactivo)]

    Reglas:
    - ID formato "CM_00001" a "CM_25000"
    - Cada APM tiene ~125 médicos (25,000 / 200 APMs)
    - ~5% con inactivo=True
    - No hay duplicados (mismo APM + doctor no se repite)
    - datos_visita_id asignado secuencialmente (1:1 con cartera)
    - Distribución realista: doctores repartidos entre APMs
    """
    n_apms = len(apm_ids)
    n_doctors = len(doctor_ids)
    n_datos_visita = len(datos_visita_ids)

    # Calcular doctores por APM (~125 promedio con variación ±20)
    docs_per_apm = n // n_apms  # ~125

    cartera: list[tuple] = []
    used_pairs: set = set()
    counter = 0

    # Barajar doctores para distribución aleatoria
    shuffled_doctors = list(doctor_ids)
    random.shuffle(shuffled_doctors)
    doctor_idx = 0

    for apm_id in apm_ids:
        # Variación ±20 en la cantidad de doctores por APM
        n_docs_for_apm = docs_per_apm + random.randint(-20, 20)
        n_docs_for_apm = max(80, min(170, n_docs_for_apm))

        for _ in range(n_docs_for_apm):
            if counter >= n:
                break

            # Tomar doctor del pool barajado (wrap-around si se agota)
            doctor_id = shuffled_doctors[doctor_idx % n_doctors]
            doctor_idx += 1

            pair = (apm_id, doctor_id)
            if pair in used_pairs:
                continue
            used_pairs.add(pair)

            counter += 1
            cm_id = f"CM_{counter:05d}"
            # Asignar datos_visita_id correspondiente (1:1)
            dv_id = datos_visita_ids[(counter - 1) % n_datos_visita]
            inactivo = random.random() < 0.05  # 5% inactivos

            cartera.append((cm_id, apm_id, doctor_id, dv_id, inactivo))

        if counter >= n:
            break

    # Rellenar si quedaron menos de n (por duplicados saltados)
    while len(cartera) < n:
        apm_id = random.choice(apm_ids)
        doctor_id = random.choice(doctor_ids)
        pair = (apm_id, doctor_id)
        if pair in used_pairs:
            continue
        used_pairs.add(pair)

        counter += 1
        cm_id = f"CM_{counter:05d}"
        dv_id = datos_visita_ids[(counter - 1) % n_datos_visita]
        inactivo = random.random() < 0.05

        cartera.append((cm_id, apm_id, doctor_id, dv_id, inactivo))

    return cartera[:n]
