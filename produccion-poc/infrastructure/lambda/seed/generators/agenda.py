"""
Generadores de tablas agenda y agenda_producto.

Genera datos realistas para:
- agenda (150,000 registros) — Visitas realizadas y planificadas por APMs a doctores
- agenda_producto (300,000 registros) — Productos presentados en cada visita (~2 por visita)

Todas las funciones reciben las tablas padre como parámetro
para garantizar integridad referencial.
Retornan list[tuple] listos para INSERT.
Usan random con seed fijo (42) para reproducibilidad.

IDs generados con formato VARCHAR:
- agenda: "AGN_000001" a "AGN_150000"
- agenda_producto: "AP_000001" a "AP_300000"

DDL target:
  agenda(id, inicio, fin, apm_id, doctor_id, visita_exitosa, observaciones, visita_tipo, inactivo)
  agenda_producto(id, id_agenda, id_producto)
"""

import random
from datetime import datetime, timedelta

# Seed fijo para reproducibilidad
random.seed(42)


# =============================================================================
# DATOS REALISTAS — Observaciones de visita
# =============================================================================

_OBSERVACIONES_TEMPLATES = [
    "Consulta sobre presentación nueva",
    "Seguimiento de tratamiento con producto",
    "Entrega de muestras médicas",
    "Revisión de dosificación con pacientes",
    "Presentación de estudio clínico reciente",
    "Actualización de ficha técnica",
    "Consulta sobre efectos secundarios reportados",
    "Feedback de pacientes sobre tolerancia",
    "Solicitud de material bibliográfico",
    "Discusión de caso clínico complejo",
    "Revisión de protocolo de tratamiento",
    "Consulta por disponibilidad en farmacia",
    "Presentación de nueva indicación aprobada",
    "Seguimiento post-evento médico",
    "Coordinación para charla en hospital",
    None,
]

# Tipos de visita con distribución: Presencial 60%, Virtual 25%, Telefónica 15%
_TIPOS_VISITA = ["Presencial", "Virtual", "Telefónica"]
_TIPOS_VISITA_PESOS = [0.60, 0.25, 0.15]


# =============================================================================
# AGENDA — 150,000 visitas realizadas/planificadas
# =============================================================================


def generate_agenda(
    cartera_records: list[tuple],
    n: int = 150_000,
) -> list[tuple]:
    """
    Genera 150,000 entries de agenda (visitas realizadas y planificadas).

    Args:
        cartera_records: output de generate_cartera_medica() — list of tuples:
            (cm_id, apm_id, doctor_id, dv_id, inactivo)
        n: cantidad de registros de agenda a generar (default 150,000).

    Returns:
        list[(id, inicio, fin, apm_id, doctor_id, visita_exitosa,
              observaciones, visita_tipo, inactivo)]

    Reglas de negocio:
    - id: formato "AGN_000001" a "AGN_150000"
    - inicio: timestamps distribuidos uniformemente en últimos 12 meses
              (no más de 7 días a futuro)
    - fin: inicio + 15–45 minutos
    - apm_id, doctor_id: tomados de pares en cartera_medica (FK válidas)
    - visita_exitosa: ~90% True, ~10% False
    - observaciones: texto corto o NULL
    - visita_tipo: Presencial(60%), Virtual(25%), Telefónica(15%)
    - inactivo: ~3% True
    """
    random.seed(42)

    # Filtrar solo carteras activas para generar visitas
    active_cartera = [
        (cm_id, apm_id, doctor_id, dv_id, inactivo)
        for cm_id, apm_id, doctor_id, dv_id, inactivo in cartera_records
        if not inactivo
    ]

    # Si no hay cartera activa, usar todas
    if not active_cartera:
        active_cartera = list(cartera_records)

    n_cartera = len(active_cartera)

    # Fecha base: hoy a medianoche
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    max_future_days = 7
    days_back = 365  # 12 meses hacia atrás
    total_window = days_back + max_future_days  # 372 días totales

    agenda: list[tuple] = []

    for i in range(n):
        # ID secuencial con formato VARCHAR
        agenda_id = f"AGN_{i + 1:06d}"

        # Seleccionar par (apm_id, doctor_id) de cartera_medica (round-robin + random)
        cartera_entry = active_cartera[i % n_cartera]
        _, apm_id, doctor_id, _, _ = cartera_entry

        # Fecha inicio: distribuida uniformemente en ventana de 372 días
        # Desde -365 (hace 1 año) hasta +7 (próxima semana)
        # offset_days: 0 = +7 futuro, 372 = -365 pasado
        day_offset = random.randint(0, total_window - 1)
        target_date = now + timedelta(days=max_future_days) - timedelta(days=day_offset)

        hora = random.randint(8, 18)  # Horario laboral 8:00-18:00
        minuto = random.choice([0, 15, 30, 45])
        inicio = target_date.replace(hour=hora, minute=minuto, second=0, microsecond=0)

        # Fin: inicio + 15–45 minutos
        duracion_minutos = random.randint(15, 45)
        fin = inicio + timedelta(minutes=duracion_minutos)

        # Visita exitosa: ~90% True
        visita_exitosa = random.random() < 0.90

        # Observaciones: ~60% tienen texto, ~40% NULL
        if random.random() < 0.60:
            observaciones = random.choice(
                [o for o in _OBSERVACIONES_TEMPLATES if o is not None]
            )
        else:
            observaciones = None

        # Tipo de visita con distribución ponderada
        visita_tipo = random.choices(
            _TIPOS_VISITA, weights=_TIPOS_VISITA_PESOS, k=1
        )[0]

        # Inactivo: ~3%
        inactivo = random.random() < 0.03

        agenda.append((
            agenda_id,
            inicio,
            fin,
            apm_id,
            doctor_id,
            visita_exitosa,
            observaciones,
            visita_tipo,
            inactivo,
        ))

    return agenda


# =============================================================================
# AGENDA_PRODUCTO — 300,000 productos presentados en visitas (~2 por visita)
# =============================================================================


def generate_agenda_producto(
    agenda_records: list[tuple],
    familia_producto_ids: list[str],
    n: int = 300_000,
) -> list[tuple]:
    """
    Genera 300,000 entries de agenda_producto (~2 productos por visita).

    Args:
        agenda_records: output de generate_agenda() — list of tuples:
            (id, inicio, fin, apm_id, doctor_id, visita_exitosa,
             observaciones, visita_tipo, inactivo)
        familia_producto_ids: list de IDs de familia_producto
            (ej: ["FAM_001", ..., "FAM_040"]).
        n: cantidad total de registros a generar (default 300,000).

    Returns:
        list[(id, id_agenda, id_producto)]

    Reglas de negocio:
    - id: formato "AP_000001" a "AP_300000"
    - id_agenda: referencia a agenda.id (FK válida)
    - id_producto: referencia a familia_producto.id (FK válida)
    - Cada visita tiene entre 1 y 3 productos (promedio ~2)
    - No se repite el mismo producto dentro de la misma visita
    - Distribución: 20% tiene 1 producto, 60% tiene 2, 20% tiene 3
    """
    random.seed(42)

    n_agenda = len(agenda_records)
    n_productos = len(familia_producto_ids)

    # Extraer solo los IDs de agenda
    agenda_ids = [record[0] for record in agenda_records]

    # Pre-asignar cantidad de productos por visita para alcanzar exactamente n
    # Distribución: 1(20%), 2(60%), 3(20%) → promedio 2.0
    productos_per_visita = random.choices(
        [1, 2, 3], weights=[0.20, 0.60, 0.20], k=n_agenda
    )

    # Ajustar para alcanzar el target exacto
    current_total = sum(productos_per_visita)
    diff = n - current_total

    if diff > 0:
        # Necesitamos más productos: promover 1→2 o 2→3
        indices = [i for i, v in enumerate(productos_per_visita) if v < 3]
        random.shuffle(indices)
        for idx in indices:
            if diff <= 0:
                break
            productos_per_visita[idx] += 1
            diff -= 1
    elif diff < 0:
        # Necesitamos menos productos: degradar 3→2 o 2→1
        indices = [i for i, v in enumerate(productos_per_visita) if v > 1]
        random.shuffle(indices)
        for idx in indices:
            if diff >= 0:
                break
            productos_per_visita[idx] -= 1
            diff += 1

    # Generar los registros
    agenda_producto: list[tuple] = []
    counter = 0

    for visita_idx in range(n_agenda):
        agenda_id = agenda_ids[visita_idx]
        n_prods = productos_per_visita[visita_idx]

        # Seleccionar productos sin repetición dentro de la misma visita
        selected = random.sample(familia_producto_ids, min(n_prods, n_productos))

        for prod_id in selected:
            counter += 1
            ap_id = f"AP_{counter:06d}"
            agenda_producto.append((ap_id, agenda_id, prod_id))

    # Truncar al target exacto si excedimos por el ajuste
    return agenda_producto[:n]
