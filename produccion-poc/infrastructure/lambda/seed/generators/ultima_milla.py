"""
Generadores de tablas "UltimaMilla" (datos CUP/IQVIA simulados).

Genera datos realistas para:
- UltimaMillaMedico (30,000 filas — 1 por doctor)
- UltimaMillaMarca (~1,500,000 filas — 30K doctors × ~50 marcas)
- UltimaMillaObjetivoMarcaMercado (500 filas)
- familia_APX_a_Marca_CUP (60 filas)
- detalle_promocion_producto (100 filas)

Distribuciones clave:
- ShareMarcaMercado: Pareto → >80% < 0.15, <5% > 0.40
- IEMarcaTrim: normal(μ=0, σ=0.1)
- idLaboratorio: ~30% = 'ELE', resto distribuido entre otros labs
- ShareMarcaTrim/ShareMarcaTrim_1: derivados de ShareMarcaMercado con variación

DDL Schema alignment:
- "UltimaMillaMedico"("idMedicoCUP", "idMedicoAPX", "IETrim", "ShareTrim", "ShareTrim_1", "ShareMes")
- "UltimaMillaMarca"("idMedicoCUP", "idMarca", "idMercado", "idLaboratorio", "marcaNombre",
                      "ShareMarcaMercado", "ShareMarcaMes", "IEMarcaTrim", "ShareMarcaTrim", "ShareMarcaTrim_1")
- "UltimaMillaObjetivoMarcaMercado"("idEspecialidad", "idMarca", "idMercado", "marcaNombre")
- familia_APX_a_Marca_CUP(id_familia_producto_apx, "codMarcaCUP")
- detalle_promocion_producto(id, id_familia_producto, id_grilla, id_categoria_promocion, id_ciclo)

Todas las funciones retornan list[tuple] listos para INSERT.
Usan random.seed(42) para reproducibilidad.
"""

import random

# Seed fijo para reproducibilidad
random.seed(42)


# =============================================================================
# CONSTANTES — Marcas CUP, Laboratorios, Mercados
# =============================================================================

# ~80 marcas CUP únicas (MRC_001 a MRC_080) con nombres farmacéuticos
_MARCA_NOMBRES = [
    "CARDIOXL", "NEUROPLEX", "GASTROFORT", "PNEUMOVIT", "DERMACALM",
    "HEPATOMAX", "OSTEOPLUS", "IMMUNOGEL", "ENDOFAST", "ONCORAP",
    "RENOVIT", "HEMATOFLEX", "PULMOCARE", "OFTALVIT", "GINEPLUS",
    "UROVIT", "REUMAFORT", "NUTRIVIT", "ANGIOMAX", "MIORELAX",
    "CARDIONEO", "NEUROPRO", "GASTROCAP", "PNEUMOLONG", "DERMANEO",
    "HEPATOFLEX", "OSTEOVIT", "IMMUNOPLUS", "ENDOFORT", "ONCOCARE",
    "RENOMAX", "HEMATOLONG", "PULMOVIT", "OFTALPRO", "GINEFORT",
    "UROMAX", "REUMANEO", "NUTRIMAX", "ANGIOFORT", "MIOCALM",
    "CARDIOFLEX", "NEUROFORT", "GASTROMAX", "PNEUMOPLUS", "DERMAFORT",
    "HEPATOPRO", "OSTEOMAX", "IMMUNOFORT", "ENDOPLUS", "ONCOMAX",
    "RENOFLEX", "HEMATOVIT", "PULMOFORT", "OFTALMAX", "GINEVIT",
    "UROPRO", "REUMAVIT", "NUTRIFORT", "ANGIOVIT", "MIOFORT",
    "CARDIOVIT", "NEUROPULS", "GASTROVIT", "PNEUMOMAX", "DERMAVIT",
    "HEPATOVIT", "OSTEOCAP", "IMMUNOCAP", "ENDOCAP", "ONCOFORT",
    "RENOCAP", "HEMATOCAP", "PULMOCAP", "OFTALCAP", "GINECAP",
    "UROCAP", "REUMACAP", "NUTRICAP", "ANGIOCAP", "MIOCAP",
]

# Build marca pool: (codMarcaCUP, marcaNombre)
_MARCA_POOL: list[tuple[str, str]] = [
    (f"MRC_{i+1:03d}", _MARCA_NOMBRES[i]) for i in range(80)
]

# Mercado IDs — 10 segmentos de mercado
_MERCADOS = [
    "MER_001", "MER_002", "MER_003", "MER_004", "MER_005",
    "MER_006", "MER_007", "MER_008", "MER_009", "MER_010",
]

# Map each marca to a mercado (deterministic: marca index % 10)
_MARCA_TO_MERCADO: dict[str, str] = {
    marca[0]: _MERCADOS[i % len(_MERCADOS)]
    for i, marca in enumerate(_MARCA_POOL)
}

# Laboratorios
_LABORATORIOS_OTROS = ["LAB_A", "LAB_B", "LAB_C", "LAB_D", "LAB_E"]


# =============================================================================
# HELPERS — Distribuciones estadísticas (solo stdlib)
# =============================================================================


def _pareto_share() -> float:
    """
    Genera ShareMarcaMercado con distribución Pareto.
    Usa np.random.pareto(a=2.0) * 0.05 equivalente con stdlib.
    Resultado: >80% de valores < 0.15, <5% de valores > 0.40.
    Clip a [0, 0.95].
    """
    # Pareto(alpha=2): X = U^(-1/alpha) - 1 donde U ~ Uniform(0,1)
    u = random.random()
    if u == 0:
        u = 1e-10
    x = (1.0 / u) ** (1.0 / 2.0) - 1.0  # Pareto(2) distribution
    val = x * 0.05  # Scale down
    return max(0.0, min(0.95, val))


def _normal_variate(mu: float, sigma: float) -> float:
    """Genera un valor de distribución normal."""
    return random.gauss(mu, sigma)


def _random_laboratorio() -> str:
    """~30% = 'ELE', 70% distribuido entre otros labs."""
    if random.random() < 0.30:
        return "ELE"
    return random.choice(_LABORATORIOS_OTROS)


# =============================================================================
# UltimaMillaMedico — 30,000 filas (1 por doctor)
# DDL: "idMedicoCUP" VARCHAR(20) PK, "idMedicoAPX" VARCHAR(20) FK→doctor(id),
#      "IETrim" DECIMAL, "ShareTrim" DECIMAL, "ShareTrim_1" DECIMAL, "ShareMes" DECIMAL
# =============================================================================


def generate_ultima_milla_medico(doctor_ids: list[str]) -> list[tuple]:
    """
    Genera 30,000 filas de UltimaMillaMedico (1 por doctor).

    Args:
        doctor_ids: list de IDs de doctor (e.g. ["DOC_00001", ..., "DOC_30000"]).

    Returns:
        list[(idMedicoCUP, idMedicoAPX, IETrim, ShareTrim, ShareTrim_1, ShareMes)]

    Mapping: idMedicoCUP = f"CUP_{doctor_id}" (simple prefix mapping)
    """
    rows: list[tuple] = []

    for doc_id in doctor_ids:
        cup_id = f"CUP_{doc_id}"
        ie_trim = round(_normal_variate(0.0, 0.1), 4)
        share_trim = round(random.uniform(0.01, 0.35), 4)
        share_trim_1 = round(share_trim + _normal_variate(0.0, 0.02), 4)
        share_mes = round(share_trim * random.uniform(0.85, 1.15), 4)

        rows.append((cup_id, doc_id, ie_trim, share_trim, share_trim_1, share_mes))

    return rows


# =============================================================================
# UltimaMillaMarca — ~1,500,000 filas (30K doctors × ~50 marcas)
# DDL: "idMedicoCUP" VARCHAR(20), "idMarca" VARCHAR(20), "idMercado" VARCHAR(20),
#      "idLaboratorio" VARCHAR(10), "marcaNombre" VARCHAR(100),
#      "ShareMarcaMercado" DECIMAL, "ShareMarcaMes" DECIMAL, "IEMarcaTrim" DECIMAL,
#      "ShareMarcaTrim" DECIMAL, "ShareMarcaTrim_1" DECIMAL
# PK: ("idMedicoCUP", "idMarca")
# =============================================================================


def generate_ultima_milla_marca(
    medico_cup_ids: list[str],
    n_marcas_per_doctor: int = 50,
) -> list[tuple]:
    """
    Genera ~1,500,000 filas de UltimaMillaMarca.
    Cada doctor recibe un subset aleatorio de 30-70 marcas del pool de 80.

    Args:
        medico_cup_ids: list de CUP IDs (e.g. ["CUP_DOC_00001", ...]).
        n_marcas_per_doctor: promedio de marcas por doctor (default 50).

    Returns:
        list[(idMedicoCUP, idMarca, idMercado, idLaboratorio, marcaNombre,
              ShareMarcaMercado, ShareMarcaMes, IEMarcaTrim,
              ShareMarcaTrim, ShareMarcaTrim_1)]

    Distributions:
        - ShareMarcaMercado: Pareto (>80% < 0.15, <5% > 0.40)
        - IEMarcaTrim: Normal(0, 0.1)
        - idLaboratorio: ~30% = 'ELE'
        - ShareMarcaTrim/ShareMarcaTrim_1: derived from ShareMarcaMercado ± variation
        - Number of marcas per doctor: Normal(50, 10) clamped to [30, 70]
    """
    rows: list[tuple] = []
    marca_pool = _MARCA_POOL  # 80 marcas

    for cup_id in medico_cup_ids:
        # Each doctor gets 30-70 marcas (normal distribution centered at 50)
        n_marcas = int(round(_normal_variate(n_marcas_per_doctor, 10)))
        n_marcas = max(30, min(70, n_marcas))
        n_marcas = min(n_marcas, len(marca_pool))

        # Random subset of marcas for this doctor
        selected = random.sample(marca_pool, n_marcas)

        for cod_marca, nombre_marca in selected:
            id_mercado = _MARCA_TO_MERCADO[cod_marca]
            id_lab = _random_laboratorio()

            # ShareMarcaMercado — Pareto distribution
            share_mercado = round(_pareto_share(), 4)

            # ShareMarcaMes — similar to share_mercado with small variation
            share_mes = round(share_mercado * random.uniform(0.80, 1.20), 4)
            share_mes = max(0.0, min(0.95, share_mes))

            # IEMarcaTrim — Normal(0, 0.1)
            ie_marca_trim = round(_normal_variate(0.0, 0.1), 4)

            # ShareMarcaTrim — derived from share_mercado with small variation
            share_trim = round(share_mercado * random.uniform(0.90, 1.10), 4)
            share_trim = max(0.0, min(0.95, share_trim))

            # ShareMarcaTrim_1 — previous period, small variation from trim
            share_trim_1 = round(share_trim * random.uniform(0.85, 1.15), 4)
            share_trim_1 = max(0.0, min(0.95, share_trim_1))

            rows.append((
                cup_id,
                cod_marca,
                id_mercado,
                id_lab,
                nombre_marca,
                share_mercado,
                share_mes,
                ie_marca_trim,
                share_trim,
                share_trim_1,
            ))

    return rows


# =============================================================================
# UltimaMillaObjetivoMarcaMercado — 500 filas
# DDL: "idEspecialidad" VARCHAR(10) FK→especialidad(id),
#      "idMarca" VARCHAR(20), "idMercado" VARCHAR(20), "marcaNombre" VARCHAR(100)
# PK: ("idEspecialidad", "idMarca", "idMercado")
# =============================================================================


def generate_ultima_milla_objetivo(
    especialidad_ids: list[str],
    marca_ids: list[str] | None = None,
) -> list[tuple]:
    """
    Genera 500 filas de objetivos de share por especialidad × marca × mercado.

    Args:
        especialidad_ids: list de IDs de especialidad (e.g. ["ESP_001", ..., "ESP_050"]).
        marca_ids: optional list of marca IDs to use. If None, uses _MARCA_POOL.

    Returns:
        list[(idEspecialidad, idMarca, idMercado, marcaNombre)]
    """
    rows: list[tuple] = []
    used_combos: set[tuple[str, str, str]] = set()

    marca_pool = _MARCA_POOL
    if marca_ids is not None:
        # Filter pool to only include provided marca_ids
        marca_pool = [(cod, nom) for cod, nom in _MARCA_POOL if cod in set(marca_ids)]
        if not marca_pool:
            marca_pool = _MARCA_POOL

    while len(rows) < 500:
        id_esp = random.choice(especialidad_ids)
        cod_marca, nombre_marca = random.choice(marca_pool)
        id_mercado = _MARCA_TO_MERCADO[cod_marca]

        combo = (id_esp, cod_marca, id_mercado)
        if combo in used_combos:
            continue
        used_combos.add(combo)

        rows.append((id_esp, cod_marca, id_mercado, nombre_marca))

    return rows


# =============================================================================
# familia_APX_a_Marca_CUP — 60 filas (cross-reference APX → CUP)
# DDL: id_familia_producto_apx VARCHAR(20) FK→familia_producto(id),
#      "codMarcaCUP" VARCHAR(20)
# PK: (id_familia_producto_apx, "codMarcaCUP")
# =============================================================================


def generate_familia_apx_a_marca_cup(
    familia_producto_ids: list[str],
    marca_cup_ids: list[str] | None = None,
) -> list[tuple]:
    """
    Genera 60 filas de mapeo familia_producto → codMarcaCUP.

    Args:
        familia_producto_ids: list de IDs de familia_producto (e.g. ["FP_01", ..., "FP_40"]).
        marca_cup_ids: optional list of valid codMarcaCUP IDs.
                       If None, uses all marca IDs from _MARCA_POOL.

    Returns:
        list[(id_familia_producto_apx, codMarcaCUP)]

    The codMarcaCUP values MUST exist in UltimaMillaMarca table.
    """
    rows: list[tuple] = []
    used_combos: set[tuple[str, str]] = set()

    # Use provided marca_cup_ids or default to all marcas from pool
    valid_marcas = marca_cup_ids if marca_cup_ids else [m[0] for m in _MARCA_POOL]

    # Distribute: each familia maps to 1-3 marcas CUP
    shuffled_familias = list(familia_producto_ids)
    random.shuffle(shuffled_familias)

    for familia_id in shuffled_familias:
        if len(rows) >= 60:
            break

        # Each familia maps to 1-3 marcas
        n_marcas = random.choices([1, 2, 3], weights=[0.50, 0.35, 0.15], k=1)[0]

        for _ in range(n_marcas):
            if len(rows) >= 60:
                break

            cod_marca = random.choice(valid_marcas)
            combo = (familia_id, cod_marca)
            if combo in used_combos:
                continue
            used_combos.add(combo)

            rows.append((familia_id, cod_marca))

    return rows


# =============================================================================
# detalle_promocion_producto — 100 filas
# DDL: id VARCHAR(30) PK,
#      id_familia_producto VARCHAR(20) FK→familia_producto(id),
#      id_grilla VARCHAR(20) FK→grilla(id),
#      id_categoria_promocion VARCHAR(5) FK→categoria_promocion(id),
#      id_ciclo VARCHAR(10) FK→ciclo(id)
# =============================================================================


def generate_detalle_promocion_producto(
    familia_producto_ids: list[str],
    grilla_ids: list[str],
    categoria_promocion_ids: list[str],
    ciclo_ids: list[str],
    n: int = 100,
) -> list[tuple]:
    """
    Genera 100 filas de detalle de promoción de producto.

    Args:
        familia_producto_ids: list de IDs de familia_producto.
        grilla_ids: list de IDs de grilla.
        categoria_promocion_ids: list de IDs de categoria_promocion (e.g. ["1", "2"]).
        ciclo_ids: list de IDs de ciclo (e.g. ["CIC_01", ..., "CIC_12"]).
        n: number of rows to generate (default 100).

    Returns:
        list[(id, id_familia_producto, id_grilla, id_categoria_promocion, id_ciclo)]

    Rules:
        - id format: "DPP_001" to "DPP_100"
        - id_categoria_promocion: '1' (HP) ~40%, '2' (FC) ~60%
        - Should reference the LAST 3 ciclos for realism
    """
    rows: list[tuple] = []
    used_combos: set[tuple[str, str, str]] = set()

    # Use last 3 ciclos for realism (current + 2 previous)
    last_ciclos = ciclo_ids[-3:] if len(ciclo_ids) >= 3 else ciclo_ids

    idx = 0
    while len(rows) < n:
        idx += 1
        dpp_id = f"DPP_{idx:03d}"
        id_familia = random.choice(familia_producto_ids)
        id_grilla = random.choice(grilla_ids)
        id_ciclo = random.choice(last_ciclos)

        # Avoid duplicate (familia, grilla, ciclo) combos
        combo = (id_familia, id_grilla, id_ciclo)
        if combo in used_combos:
            continue
        used_combos.add(combo)

        # Categoría: 40% HP (1), 60% FC (2)
        id_categoria = "1" if random.random() < 0.40 else "2"

        rows.append((dpp_id, id_familia, id_grilla, id_categoria, id_ciclo))

    return rows
