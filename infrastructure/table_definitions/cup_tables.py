"""Table definitions for the CloseUp domain (pharmassist_cup).

Contains 10 tables representing pharmaceutical prescription/sales data
from CloseUp International: doctors, brands, markets, representatives,
prescriptions, and visit tracking.
"""

from table_definitions import ColumnDef, TableDef

CUP_TABLES: list[TableDef] = [
    # 1. medico — Médico en CloseUp
    TableDef(
        name="medico",
        description="Médico en CloseUp",
        columns=[
            ColumnDef(name="cdgmedico", type="int", comment="Código único del médico en CloseUp"),
            ColumnDef(name="nombre", type="string", comment="Nombre del médico"),
            ColumnDef(name="apellido", type="string", comment="Apellido del médico"),
            ColumnDef(name="especialidad", type="string", comment="Especialidad médica"),
            ColumnDef(name="zona", type="string", comment="Zona geográfica"),
            ColumnDef(name="localidad", type="string", comment="Localidad"),
            ColumnDef(name="provincia", type="string", comment="Provincia"),
            ColumnDef(name="activo", type="boolean", comment="Si el médico está activo"),
        ],
        partition_keys=[],
    ),
    # 2. marca — Marca farmacéutica
    TableDef(
        name="marca",
        description="Marca farmacéutica",
        columns=[
            ColumnDef(name="cdgmarca", type="int", comment="Código único de la marca"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la marca"),
            ColumnDef(name="laboratorio", type="string", comment="Laboratorio propietario"),
            ColumnDef(name="clase_terapeutica", type="string", comment="Clase terapéutica"),
            ColumnDef(name="activo", type="boolean", comment="Si la marca está activa"),
        ],
        partition_keys=[],
    ),
    # 3. mercado — Mercado/segmento
    TableDef(
        name="mercado",
        description="Mercado/segmento farmacéutico",
        columns=[
            ColumnDef(name="cdgmercado", type="int", comment="Código único del mercado"),
            ColumnDef(name="nombre", type="string", comment="Nombre del mercado"),
            ColumnDef(name="descripcion", type="string", comment="Descripción del mercado"),
            ColumnDef(name="activo", type="boolean", comment="Si el mercado está activo"),
        ],
        partition_keys=[],
    ),
    # 4. mercado_producto — Relación mercado-producto
    TableDef(
        name="mercado_producto",
        description="Relación mercado-producto",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="cdgmercado", type="int", comment="FK al mercado"),
            ColumnDef(name="cdgmarca", type="int", comment="FK a la marca"),
            ColumnDef(name="participacion", type="decimal(5,2)", comment="Participación de mercado (%)"),
            ColumnDef(name="activo", type="boolean", comment="Si la relación está activa"),
        ],
        partition_keys=[],
    ),
    # 5. representante — Representante/visitador
    TableDef(
        name="representante",
        description="Representante/visitador médico",
        columns=[
            ColumnDef(name="cdgrep", type="int", comment="Código único del representante"),
            ColumnDef(name="nombre", type="string", comment="Nombre del representante"),
            ColumnDef(name="apellido", type="string", comment="Apellido del representante"),
            ColumnDef(name="laboratorio", type="string", comment="Laboratorio al que pertenece"),
            ColumnDef(name="zona", type="string", comment="Zona asignada"),
            ColumnDef(name="activo", type="boolean", comment="Si el representante está activo"),
        ],
        partition_keys=[],
    ),
    # 6. prescripcion — Prescripciones (PARTITIONED by anio, mes, cdgreg_pmix)
    TableDef(
        name="prescripcion",
        description="Prescripciones médicas — tabla de alto volumen particionada",
        columns=[
            ColumnDef(name="id", type="bigint", comment="Identificador único de prescripción"),
            ColumnDef(name="cdgmedico", type="int", comment="FK al médico prescriptor"),
            ColumnDef(name="cdgmarca", type="int", comment="FK a la marca prescripta"),
            ColumnDef(name="cdgmercado", type="int", comment="FK al mercado"),
            ColumnDef(name="cdgrep", type="int", comment="FK al representante"),
            ColumnDef(name="anio", type="int", comment="Año de la prescripción"),
            ColumnDef(name="mes", type="int", comment="Mes de la prescripción"),
            ColumnDef(name="cdgreg_pmix", type="int", comment="Código de región PMIX"),
            ColumnDef(name="unidades", type="int", comment="Unidades prescriptas"),
            ColumnDef(name="valores", type="decimal(12,2)", comment="Valor monetario"),
            ColumnDef(name="recetas", type="int", comment="Cantidad de recetas"),
            ColumnDef(name="fecha_proceso", type="date", comment="Fecha de procesamiento"),
        ],
        partition_keys=["anio", "mes", "cdgreg_pmix"],
    ),
    # 7. medico_rep_novisitado — Médicos no visitados por rep
    TableDef(
        name="medico_rep_novisitado",
        description="Médicos no visitados por representante",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="cdgmedico", type="int", comment="FK al médico"),
            ColumnDef(name="cdgrep", type="int", comment="FK al representante"),
            ColumnDef(name="anio", type="int", comment="Año del registro"),
            ColumnDef(name="mes", type="int", comment="Mes del registro"),
            ColumnDef(name="motivo", type="string", comment="Motivo de no visita"),
        ],
        partition_keys=[],
    ),
    # 8. medico_representante — Relación médico-representante
    TableDef(
        name="medico_representante",
        description="Relación médico-representante",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="cdgmedico", type="int", comment="FK al médico"),
            ColumnDef(name="cdgrep", type="int", comment="FK al representante"),
            ColumnDef(name="fecha_asignacion", type="date", comment="Fecha de asignación"),
            ColumnDef(name="activo", type="boolean", comment="Si la relación está activa"),
        ],
        partition_keys=[],
    ),
    # 9. medico_visitado — Médicos visitados
    TableDef(
        name="medico_visitado",
        description="Médicos visitados por representante",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="cdgmedico", type="int", comment="FK al médico"),
            ColumnDef(name="cdgrep", type="int", comment="FK al representante"),
            ColumnDef(name="anio", type="int", comment="Año del registro"),
            ColumnDef(name="mes", type="int", comment="Mes del registro"),
            ColumnDef(name="cantidad_visitas", type="int", comment="Cantidad de visitas realizadas"),
            ColumnDef(name="ultima_visita", type="date", comment="Fecha de última visita"),
        ],
        partition_keys=[],
    ),
    # 10. mercado_modulo_linea — Relación mercado-módulo-línea
    TableDef(
        name="mercado_modulo_linea",
        description="Relación mercado-módulo-línea",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="cdgmercado", type="int", comment="FK al mercado"),
            ColumnDef(name="modulo", type="string", comment="Módulo"),
            ColumnDef(name="linea", type="string", comment="Línea"),
            ColumnDef(name="activo", type="boolean", comment="Si la relación está activa"),
        ],
        partition_keys=[],
    ),
]
