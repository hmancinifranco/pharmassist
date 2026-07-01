"""
Seed data generators for PharmAssist POC.

Catalogos module returns pandas DataFrames with VARCHAR string IDs.
Other modules return list[tuple] ready for bulk INSERT.
All generators use fixed seeds for reproducibility.
"""

from .catalogos import (
    generate_especialidades,
    generate_loyalty_doctor,
    generate_instituciones,
    generate_lineas,
    generate_ciclos,
    generate_categorias_promocion,
    generate_grillas,
    generate_familias_producto,
    generate_productos,
)

from .entities import (
    generate_apms,
    generate_doctors,
    generate_linea_apm,
    generate_datos_visita,
    generate_cartera_medica,
)

from .agenda import (
    generate_agenda,
    generate_agenda_producto,
)

from .ultima_milla import (
    generate_ultima_milla_medico,
    generate_ultima_milla_marca,
    generate_ultima_milla_objetivo,
    generate_familia_apx_a_marca_cup,
    generate_detalle_promocion_producto,
)

__all__ = [
    # Catálogos (tablas padre) — retornan pd.DataFrame
    "generate_especialidades",
    "generate_loyalty_doctor",
    "generate_instituciones",
    "generate_lineas",
    "generate_ciclos",
    "generate_categorias_promocion",
    "generate_grillas",
    "generate_familias_producto",
    "generate_productos",
    # Entidades dependientes
    "generate_apms",
    "generate_doctors",
    "generate_linea_apm",
    "generate_datos_visita",
    "generate_cartera_medica",
    # Agenda y productos de visita
    "generate_agenda",
    "generate_agenda_producto",
    # UltimaMilla (datos CUP/IQVIA)
    "generate_ultima_milla_medico",
    "generate_ultima_milla_marca",
    "generate_ultima_milla_objetivo",
    "generate_familia_apx_a_marca_cup",
    "generate_detalle_promocion_producto",
]
