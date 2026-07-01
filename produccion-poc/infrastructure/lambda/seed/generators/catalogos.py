"""
Generadores de tablas padre (catálogos sin dependencias de FK).

Genera DataFrames con datos realistas de contexto farmacéutico argentino:
- especialidad (50) — especialidades médicas reales
- loyalty_doctor (5) — niveles de lealtad
- institucion (500) — hospitales/clínicas/sanatorios
- linea (5) — líneas farmacéuticas
- ciclo (12) — ciclos promocionales mensuales (últimos 12 meses)
- categoria_promocion (2) — HP=Hiperfoco, FC=Foco
- grilla (10) — grillas promocionales (FK→linea)
- familia_producto (40) — familias con principio_activo y accion_terapeutica
- producto (150) — productos individuales (FK→linea)

Todas las funciones retornan pd.DataFrame con IDs VARCHAR string.
Usan numpy random con seed fijo para reproducibilidad.
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta

# Seed fijo para reproducibilidad
_RNG = np.random.default_rng(42)


# =============================================================================
# ESPECIALIDAD — 50 especialidades médicas reales (contexto argentino)
# =============================================================================

_ESPECIALIDADES = [
    "Cardiología", "Dermatología", "Gastroenterología", "Neurología",
    "Endocrinología", "Neumología", "Reumatología", "Nefrología",
    "Oncología", "Hematología", "Infectología", "Urología",
    "Ginecología", "Obstetricia", "Pediatría", "Geriatría",
    "Psiquiatría", "Oftalmología", "Otorrinolaringología", "Traumatología",
    "Cirugía General", "Cirugía Cardiovascular", "Neurocirugía",
    "Medicina Interna", "Medicina Familiar", "Clínica Médica",
    "Diabetología", "Alergología", "Anestesiología", "Terapia Intensiva",
    "Medicina del Dolor", "Hepatología", "Proctología", "Flebología",
    "Mastología", "Medicina Estética", "Nutrición", "Fisiatría",
    "Medicina Laboral", "Toxicología", "Genética Médica", "Neonatología",
    "Medicina Nuclear", "Radioterapia", "Anatomía Patológica",
    "Medicina Legal", "Medicina Deportiva", "Inmunología",
    "Farmacología Clínica", "Cuidados Paliativos",
]


def generate_especialidades(n: int = 50) -> pd.DataFrame:
    """
    Genera DataFrame de especialidades médicas.

    Columns: id (VARCHAR(10)), nombre (VARCHAR(100))
    IDs: ESP_001, ESP_002, ..., ESP_050
    """
    nombres = _ESPECIALIDADES[:n]
    ids = [f"ESP_{i+1:03d}" for i in range(n)]
    return pd.DataFrame({"id": ids, "nombre": nombres})


# =============================================================================
# LOYALTY_DOCTOR — 5 niveles de lealtad
# =============================================================================

_LOYALTY_LEVELS = [
    ("LOY_01", "Platino"),
    ("LOY_02", "Oro"),
    ("LOY_03", "Plata"),
    ("LOY_04", "Bronce"),
    ("LOY_05", "Estándar"),
]


def generate_loyalty_doctor() -> pd.DataFrame:
    """
    Genera DataFrame con 5 niveles de lealtad de médicos.

    Columns: id (VARCHAR(10)), nombre (VARCHAR(50))
    IDs: LOY_01 a LOY_05
    """
    ids = [x[0] for x in _LOYALTY_LEVELS]
    nombres = [x[1] for x in _LOYALTY_LEVELS]
    return pd.DataFrame({"id": ids, "nombre": nombres})


# =============================================================================
# INSTITUCION — 500 hospitales/clínicas/sanatorios
# =============================================================================

_TIPOS_INSTITUCION = [
    "Hospital", "Clínica", "Sanatorio", "Centro Médico",
    "Instituto", "Fundación", "Centro de Salud",
]

_NOMBRES_BASE = [
    "San Martín", "Rivadavia", "Argerich", "Fernández", "Pirovano",
    "Durand", "Ramos Mejía", "Álvarez", "Santojanni", "Gutiérrez",
    "Italiano", "Alemán", "Británico", "Francés", "Austral",
    "CEMIC", "Favaloro", "Fleni", "Los Arcos", "Trinidad",
    "Anchorena", "Bazterrica", "Otamendi", "Finochietto", "Del Sol",
    "Central", "Municipal", "Provincial", "Regional", "Universitario",
    "San Juan", "San José", "Santa María", "San Lucas", "San Camilo",
    "Del Norte", "Del Sur", "Del Oeste", "Del Este", "Modelo",
    "Garrahan", "Posadas", "Centenario", "Eva Perón", "Penna",
    "Rawson", "Moyano", "Borda", "Tornú", "Muñiz",
]


def generate_instituciones(n: int = 500) -> pd.DataFrame:
    """
    Genera DataFrame de instituciones de salud argentinas.

    Columns: id (VARCHAR(20)), nombre (VARCHAR(200))
    IDs: INST_0001, INST_0002, ..., INST_0500
    """
    nombres: list[str] = []
    seen: set[str] = set()

    idx = 0
    while len(nombres) < n:
        tipo = _TIPOS_INSTITUCION[_RNG.integers(0, len(_TIPOS_INSTITUCION))]
        base = _NOMBRES_BASE[_RNG.integers(0, len(_NOMBRES_BASE))]

        # Agregar sufijo numérico si es necesario para unicidad
        nombre = f"{tipo} {base}"
        if nombre in seen:
            nombre = f"{tipo} {base} {_RNG.integers(1, 100)}"

        if nombre not in seen:
            seen.add(nombre)
            nombres.append(nombre)
        idx += 1

    ids = [f"INST_{i+1:04d}" for i in range(n)]
    return pd.DataFrame({"id": ids, "nombre": nombres})


# =============================================================================
# LINEA — 5 líneas farmacéuticas
# =============================================================================

_LINEAS = [
    ("LIN_01", "Línea Cardio", "CAR"),
    ("LIN_02", "Línea Gastro", "GAS"),
    ("LIN_03", "Línea Dolor", "DOL"),
    ("LIN_04", "Línea Respiratoria", "RES"),
    ("LIN_05", "Línea SNC", "SNC"),
]


def generate_lineas(n: int = 5) -> pd.DataFrame:
    """
    Genera DataFrame de líneas farmacéuticas.

    Columns: id (VARCHAR(10)), nombre (VARCHAR(100)), abreviatura (VARCHAR(10))
    IDs: LIN_01 a LIN_05
    """
    data = _LINEAS[:n]
    return pd.DataFrame(data, columns=["id", "nombre", "abreviatura"])


# =============================================================================
# CICLO — 12 ciclos mensuales (últimos 12 meses desde hoy)
# =============================================================================

_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def generate_ciclos(n: int = 12) -> pd.DataFrame:
    """
    Genera DataFrame de ciclos promocionales mensuales.
    Cubre los últimos 12 meses desde la fecha actual.

    Columns: id (VARCHAR(10)), inicio (DATE), fin (DATE), nombre (VARCHAR(50))
    IDs: CIC_01 a CIC_12
    """
    today = date.today()
    ciclos: list[dict] = []

    for i in range(n):
        # Calcular mes: desde 11 meses atrás hasta el mes actual
        months_back = n - 1 - i
        # Usar date arithmetic para retroceder meses
        year = today.year
        month = today.month - months_back
        while month <= 0:
            month += 12
            year -= 1

        inicio = date(year, month, 1)
        # Fin: último día del mes
        if month == 12:
            fin = date(year, 12, 31)
        else:
            fin = date(year, month + 1, 1) - timedelta(days=1)

        nombre = f"Ciclo {_MESES[month - 1]} {year}"
        ciclos.append({
            "id": f"CIC_{i+1:02d}",
            "inicio": inicio,
            "fin": fin,
            "nombre": nombre,
        })

    return pd.DataFrame(ciclos)


# =============================================================================
# CATEGORIA_PROMOCION — exactamente 2 (HP=Hiperfoco, FC=Foco)
# =============================================================================


def generate_categorias_promocion() -> pd.DataFrame:
    """
    Genera DataFrame con exactamente 2 categorías de promoción.

    - id='1', abreviatura='HP', nombre_categoria='Hiperfoco'
    - id='2', abreviatura='FC', nombre_categoria='Foco'

    Columns: id (VARCHAR(5)), abreviatura (VARCHAR(5)), nombre_categoria (VARCHAR(50))
    """
    return pd.DataFrame({
        "id": ["1", "2"],
        "abreviatura": ["HP", "FC"],
        "nombre_categoria": ["Hiperfoco", "Foco"],
    })


# =============================================================================
# GRILLA — 10 grillas promocionales (FK→linea)
# =============================================================================


def generate_grillas(lineas_df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """
    Genera DataFrame de grillas promocionales vinculadas a líneas.

    Columns: id (VARCHAR(20)), nombre_grilla (VARCHAR(100)), id_linea (FK→linea)
    IDs: GRI_001, GRI_002, ..., GRI_010
    """
    linea_ids = lineas_df["id"].tolist()

    nombres_base = [
        "Grilla Primaria", "Grilla Secundaria", "Grilla Refuerzo",
        "Grilla Lanzamiento", "Grilla Especial", "Grilla Intensiva",
        "Grilla Mantenimiento", "Grilla Estacional", "Grilla Premium",
        "Grilla Consolidación",
    ]

    grillas: list[dict] = []
    for i in range(n):
        nombre = nombres_base[i] if i < len(nombres_base) else f"Grilla {i+1}"
        # Distribuir grillas entre las líneas (round-robin con algo de aleatoriedad)
        id_linea = linea_ids[i % len(linea_ids)]
        grillas.append({
            "id": f"GRI_{i+1:03d}",
            "nombre_grilla": nombre,
            "id_linea": id_linea,
        })

    return pd.DataFrame(grillas)


# =============================================================================
# FAMILIA_PRODUCTO — 40 familias con principio_activo y accion_terapeutica
# =============================================================================

_FAMILIAS_DATA = [
    # (nombre, principio_activo, accion_terapeutica) — agrupadas por línea
    # Línea Cardio (8 familias)
    ("Atenolol", "Atenolol", "Antihipertensivo beta-bloqueante"),
    ("Losartán", "Losartán potásico", "Antihipertensivo ARA-II"),
    ("Enalapril", "Enalapril maleato", "Inhibidor de la ECA"),
    ("Amlodipina", "Amlodipina besilato", "Bloqueante cálcico"),
    ("Valsartán", "Valsartán", "Antihipertensivo ARA-II"),
    ("Bisoprolol", "Bisoprolol fumarato", "Beta-bloqueante cardioselectivo"),
    ("Rosuvastatina", "Rosuvastatina cálcica", "Hipolipemiante estatina"),
    ("Atorvastatina", "Atorvastatina cálcica", "Hipolipemiante estatina"),
    # Línea Gastro (8 familias)
    ("Omeprazol", "Omeprazol", "Inhibidor de bomba de protones"),
    ("Pantoprazol", "Pantoprazol sódico", "Inhibidor de bomba de protones"),
    ("Esomeprazol", "Esomeprazol magnésico", "Inhibidor de bomba de protones"),
    ("Domperidona", "Domperidona", "Procinético antidopaminérgico"),
    ("Metoclopramida", "Metoclopramida", "Antiemético procinético"),
    ("Mesalazina", "Mesalazina", "Antiinflamatorio intestinal"),
    ("Sucralfato", "Sucralfato", "Protector de mucosa gástrica"),
    ("Dimeticona", "Dimeticona + Simeticona", "Antiflatulento"),
    # Línea Dolor (8 familias)
    ("Ibuprofeno", "Ibuprofeno", "AINE analgésico"),
    ("Diclofenac", "Diclofenac sódico", "AINE antiinflamatorio"),
    ("Meloxicam", "Meloxicam", "AINE inhibidor COX-2"),
    ("Ketorolac", "Ketorolac trometamina", "AINE analgésico potente"),
    ("Tramadol", "Tramadol clorhidrato", "Analgésico opioide débil"),
    ("Pregabalina", "Pregabalina", "Anticonvulsivante/analgésico neuropático"),
    ("Ciclobenzaprina", "Ciclobenzaprina", "Relajante muscular"),
    ("Naproxeno", "Naproxeno sódico", "AINE analgésico prolongado"),
    # Línea Respiratoria (8 familias)
    ("Salbutamol", "Salbutamol sulfato", "Broncodilatador beta-2 agonista"),
    ("Budesonida", "Budesonida", "Corticoide inhalatorio"),
    ("Montelukast", "Montelukast sódico", "Antagonista de leucotrienos"),
    ("Loratadina", "Loratadina", "Antihistamínico no sedante"),
    ("Cetirizina", "Cetirizina diclorhidrato", "Antihistamínico segunda gen."),
    ("Fluticasona", "Fluticasona propionato", "Corticoide inhalatorio"),
    ("Ipratropio", "Bromuro de ipratropio", "Anticolinérgico broncodilatador"),
    ("Desloratadina", "Desloratadina", "Antihistamínico tercera gen."),
    # Línea SNC (8 familias)
    ("Sertralina", "Sertralina clorhidrato", "Antidepresivo ISRS"),
    ("Escitalopram", "Escitalopram oxalato", "Antidepresivo ISRS"),
    ("Quetiapina", "Quetiapina fumarato", "Antipsicótico atípico"),
    ("Clonazepam", "Clonazepam", "Ansiolítico benzodiazepínico"),
    ("Alprazolam", "Alprazolam", "Ansiolítico benzodiazepínico"),
    ("Lamotrigina", "Lamotrigina", "Anticonvulsivante/estabilizador"),
    ("Levetiracetam", "Levetiracetam", "Anticonvulsivante"),
    ("Venlafaxina", "Venlafaxina clorhidrato", "Antidepresivo IRSN"),
]


def generate_familias_producto(n: int = 40) -> pd.DataFrame:
    """
    Genera DataFrame de familias de producto con principio activo y acción terapéutica.

    Columns: id (VARCHAR(20)), nombre (VARCHAR(100)),
             principio_activo (VARCHAR(200)), accion_terapeutica (VARCHAR(200))
    IDs: FAM_001, FAM_002, ..., FAM_040
    """
    data = _FAMILIAS_DATA[:n]
    ids = [f"FAM_{i+1:03d}" for i in range(len(data))]
    nombres = [x[0] for x in data]
    principios = [x[1] for x in data]
    acciones = [x[2] for x in data]

    return pd.DataFrame({
        "id": ids,
        "nombre": nombres,
        "principio_activo": principios,
        "accion_terapeutica": acciones,
    })


# =============================================================================
# PRODUCTO — 150 productos individuales (FK→linea)
# =============================================================================

_MARCAS_COMERCIALES = [
    "PAMOXET", "KLOSIDOL", "TAFIROL", "IBUEVANOL", "MIGRAL",
    "BAYASPIRINA", "SERTAL", "NEXIUM", "GASTEC", "ULCOZOL",
    "CARDIOL", "LOTRIAL", "ATENOVIT", "COZAAR", "NORVASC",
    "VENTOLIN", "PULMICORT", "SINGULAIR", "CLARITYNE", "AERIUS",
    "ZOLOFT", "LEXAPRO", "SEROQUEL", "RIVOTRIL", "ALPLAX",
    "LAMICTAL", "KEPPRA", "EFEXOR", "LYRICA", "DICLOFENAC",
    "VOLTAREN", "MELOXICAM", "KETOROL", "TRAMAL", "NAPROX",
    "OMEPRAL", "PANTOLOC", "DOMPER", "RELIVERAN", "MESACOL",
    "LIPITOR", "CRESTOR", "CONCOR", "ATENOL", "ENALAPRIL",
    "LOSARTAN", "VALSARTAN", "AMLOD", "BISOPROL", "ROSUVA",
]

_PRESENTACIONES = [
    "Comp. 10mg x30", "Comp. 20mg x30", "Comp. 50mg x30",
    "Comp. 100mg x30", "Comp. 10mg x60", "Comp. 20mg x60",
    "Caps. 20mg x28", "Caps. 40mg x28", "Caps. 75mg x28",
    "Susp. 200ml", "Gotas 30ml", "Jarabe 120ml",
    "Iny. 50mg/ml x5", "Iny. 100mg/ml x3",
    "Crema 30g", "Gel 50g",
    "Inh. 200 dosis", "Neb. 2.5mg/ml x20",
    "Parche 5mg/24h x7", "Sobres 10mg x20",
]

# Mapeo de líneas a índices de marcas (para que los nombres sean coherentes)
_MARCAS_POR_LINEA = {
    "LIN_01": _MARCAS_COMERCIALES[20:30],   # Cardio
    "LIN_02": _MARCAS_COMERCIALES[30:40],   # Gastro
    "LIN_03": _MARCAS_COMERCIALES[0:10],    # Dolor
    "LIN_04": _MARCAS_COMERCIALES[15:20] + _MARCAS_COMERCIALES[40:45],  # Respiratoria
    "LIN_05": _MARCAS_COMERCIALES[20:30],   # SNC - reusar con variantes
}


def generate_productos(lineas_df: pd.DataFrame, n: int = 150) -> pd.DataFrame:
    """
    Genera DataFrame de productos individuales vinculados a líneas.

    Columns: id (VARCHAR(20)), nombre (VARCHAR(100)), id_linea (FK→linea)
    IDs: PROD_001, PROD_002, ..., PROD_150
    """
    linea_ids = lineas_df["id"].tolist()
    productos: list[dict] = []
    seen_names: set[str] = set()

    # Distribuir productos entre líneas (~30 por línea)
    productos_por_linea = n // len(linea_ids)
    remainder = n % len(linea_ids)

    idx = 0
    for li, linea_id in enumerate(linea_ids):
        count = productos_por_linea + (1 if li < remainder else 0)
        marcas_pool = _MARCAS_POR_LINEA.get(linea_id, _MARCAS_COMERCIALES[:10])

        for _ in range(count):
            # Generar nombre único: MARCA + presentación
            attempts = 0
            while attempts < 50:
                marca = marcas_pool[_RNG.integers(0, len(marcas_pool))]
                pres = _PRESENTACIONES[_RNG.integers(0, len(_PRESENTACIONES))]
                nombre = f"{marca} {pres}"
                if nombre not in seen_names:
                    seen_names.add(nombre)
                    break
                attempts += 1
            else:
                # Fallback con sufijo numérico
                nombre = f"{marca} {pres} #{idx}"
                seen_names.add(nombre)

            productos.append({
                "id": f"PROD_{idx+1:03d}",
                "nombre": nombre,
                "id_linea": linea_id,
            })
            idx += 1

    return pd.DataFrame(productos)
