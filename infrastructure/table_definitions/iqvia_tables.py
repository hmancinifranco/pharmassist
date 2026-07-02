"""Table definitions for the IQVIA domain (pharmassist_iqvia).

Contains 13 tables representing the pharmaceutical market data star schema from IQVIA:
dimension tables (período, droga, forma farmacéutica, laboratorio, clase terapéutica,
presentación, geografía, clase, combinación droga), relationship tables (presentación-droga,
presentación-forma, producto-laboratorio), and the fact table (mercado valor).
"""

from table_definitions import ColumnDef, TableDef

IQVIA_TABLES: list[TableDef] = [
    # 1. dim_periodo — Dimensión período
    TableDef(
        name="dim_periodo",
        description="Dimensión período temporal para análisis de mercado IQVIA",
        columns=[
            ColumnDef(name="idperiodo", type="int", comment="Identificador único del período"),
            ColumnDef(name="anio", type="int", comment="Año del período"),
            ColumnDef(name="mes", type="int", comment="Mes del período (1-12)"),
            ColumnDef(name="trimestre", type="int", comment="Trimestre del período (1-4)"),
            ColumnDef(name="semestre", type="int", comment="Semestre del período (1-2)"),
            ColumnDef(name="nombre_mes", type="string", comment="Nombre del mes en español"),
            ColumnDef(name="fecha_inicio", type="date", comment="Fecha de inicio del período"),
            ColumnDef(name="fecha_fin", type="date", comment="Fecha de fin del período"),
        ],
        partition_keys=[],
    ),
    # 2. dim_droga — Dimensión droga/principio activo
    TableDef(
        name="dim_droga",
        description="Dimensión droga/principio activo farmacéutico",
        columns=[
            ColumnDef(name="iddroga", type="int", comment="Identificador único de la droga"),
            ColumnDef(name="nombre", type="string", comment="Nombre del principio activo"),
            ColumnDef(name="descripcion", type="string", comment="Descripción de la droga"),
            ColumnDef(name="grupo_quimico", type="string", comment="Grupo químico al que pertenece"),
            ColumnDef(name="activo", type="boolean", comment="Si la droga está activa en el catálogo"),
        ],
        partition_keys=[],
    ),
    # 3. dim_forma_farmaceutica — Dimensión forma farmacéutica
    TableDef(
        name="dim_forma_farmaceutica",
        description="Dimensión forma farmacéutica (comprimido, jarabe, inyectable, etc.)",
        columns=[
            ColumnDef(name="idforma", type="int", comment="Identificador único de la forma"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la forma farmacéutica"),
            ColumnDef(name="descripcion", type="string", comment="Descripción de la forma"),
            ColumnDef(name="via_administracion", type="string", comment="Vía de administración (oral, IV, IM, etc.)"),
        ],
        partition_keys=[],
    ),
    # 4. dim_laboratorio — Dimensión laboratorio
    TableDef(
        name="dim_laboratorio",
        description="Dimensión laboratorio farmacéutico",
        columns=[
            ColumnDef(name="idlaboratorio", type="int", comment="Identificador único del laboratorio"),
            ColumnDef(name="nombre", type="string", comment="Nombre del laboratorio"),
            ColumnDef(name="pais_origen", type="string", comment="País de origen del laboratorio"),
            ColumnDef(name="tipo", type="string", comment="Tipo de laboratorio (nacional, multinacional)"),
            ColumnDef(name="activo", type="boolean", comment="Si el laboratorio está activo"),
        ],
        partition_keys=[],
    ),
    # 5. dim_clase_terapeutica — Dimensión clase terapéutica
    TableDef(
        name="dim_clase_terapeutica",
        description="Dimensión clase terapéutica (clasificación ATC/IQVIA)",
        columns=[
            ColumnDef(name="idclase_terapeutica", type="int", comment="Identificador único de la clase"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la clase terapéutica"),
            ColumnDef(name="nivel1", type="string", comment="Nivel 1 de clasificación"),
            ColumnDef(name="nivel2", type="string", comment="Nivel 2 de clasificación"),
            ColumnDef(name="nivel3", type="string", comment="Nivel 3 de clasificación"),
            ColumnDef(name="nivel4", type="string", comment="Nivel 4 de clasificación"),
        ],
        partition_keys=[],
    ),
    # 6. dim_presentacion — Dimensión presentación
    TableDef(
        name="dim_presentacion",
        description="Dimensión presentación comercial del producto farmacéutico",
        columns=[
            ColumnDef(name="idpresentacion", type="int", comment="Identificador único de la presentación"),
            ColumnDef(name="nombre", type="string", comment="Nombre comercial de la presentación"),
            ColumnDef(name="idlaboratorio", type="int", comment="FK al laboratorio fabricante"),
            ColumnDef(name="concentracion", type="string", comment="Concentración del principio activo"),
            ColumnDef(name="unidades_envase", type="int", comment="Cantidad de unidades por envase"),
            ColumnDef(name="forma_farmaceutica", type="string", comment="Forma farmacéutica de la presentación"),
            ColumnDef(name="activo", type="boolean", comment="Si la presentación está activa"),
        ],
        partition_keys=[],
    ),
    # 7. dim_geografia — Dimensión geografía
    TableDef(
        name="dim_geografia",
        description="Dimensión geográfica para análisis de mercado por zona",
        columns=[
            ColumnDef(name="idgeografia", type="int", comment="Identificador único de la geografía"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la localidad/zona"),
            ColumnDef(name="provincia", type="string", comment="Provincia"),
            ColumnDef(name="region", type="string", comment="Región geográfica"),
            ColumnDef(name="zona", type="string", comment="Zona comercial"),
        ],
        partition_keys=[],
    ),
    # 8. dim_clase — Dimensión clase
    TableDef(
        name="dim_clase",
        description="Dimensión clase jerárquica de productos",
        columns=[
            ColumnDef(name="idclase", type="int", comment="Identificador único de la clase"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la clase"),
            ColumnDef(name="nivel", type="int", comment="Nivel jerárquico de la clase"),
            ColumnDef(name="padre_id", type="int", comment="FK a la clase padre (jerárquica)"),
            ColumnDef(name="activo", type="boolean", comment="Si la clase está activa"),
        ],
        partition_keys=[],
    ),
    # 9. dim_combinacion_droga — Dimensión combinación de drogas
    TableDef(
        name="dim_combinacion_droga",
        description="Dimensión combinación de drogas/principios activos",
        columns=[
            ColumnDef(name="idcombinacion", type="int", comment="Identificador único de la combinación"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la combinación"),
            ColumnDef(name="drogas", type="string", comment="Lista de drogas que componen la combinación"),
            ColumnDef(name="cantidad_componentes", type="int", comment="Cantidad de componentes activos"),
        ],
        partition_keys=[],
    ),
    # 10. rel_presentacion_droga — Relación presentación-droga
    TableDef(
        name="rel_presentacion_droga",
        description="Relación entre presentaciones y drogas/principios activos",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único de la relación"),
            ColumnDef(name="idpresentacion", type="int", comment="FK a la presentación"),
            ColumnDef(name="iddroga", type="int", comment="FK a la droga"),
            ColumnDef(name="concentracion", type="string", comment="Concentración de la droga en la presentación"),
            ColumnDef(name="es_principal", type="boolean", comment="Si es el principio activo principal"),
        ],
        partition_keys=[],
    ),
    # 11. rel_presentacion_forma — Relación presentación-forma
    TableDef(
        name="rel_presentacion_forma",
        description="Relación entre presentaciones y formas farmacéuticas",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único de la relación"),
            ColumnDef(name="idpresentacion", type="int", comment="FK a la presentación"),
            ColumnDef(name="idforma", type="int", comment="FK a la forma farmacéutica"),
        ],
        partition_keys=[],
    ),
    # 12. rel_producto_laboratorio — Relación producto-laboratorio
    TableDef(
        name="rel_producto_laboratorio",
        description="Relación entre productos/presentaciones y laboratorios",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único de la relación"),
            ColumnDef(name="idpresentacion", type="int", comment="FK a la presentación"),
            ColumnDef(name="idlaboratorio", type="int", comment="FK al laboratorio"),
            ColumnDef(name="marca_comercial", type="string", comment="Marca comercial del producto"),
            ColumnDef(name="fecha_lanzamiento", type="date", comment="Fecha de lanzamiento al mercado"),
        ],
        partition_keys=[],
    ),
    # 13. fact_mercado_valor — Fact table de mercado (PARTITIONED by idperiodo)
    TableDef(
        name="fact_mercado_valor",
        description="Fact table de valores de mercado farmacéutico IQVIA, particionada por período",
        columns=[
            ColumnDef(name="id", type="bigint", comment="Identificador único del registro"),
            ColumnDef(name="idperiodo", type="int", comment="FK al período (partition key)"),
            ColumnDef(name="idpresentacion", type="int", comment="FK a la presentación"),
            ColumnDef(name="idgeografia", type="int", comment="FK a la geografía"),
            ColumnDef(name="idclase_terapeutica", type="int", comment="FK a la clase terapéutica"),
            ColumnDef(name="unidades", type="bigint", comment="Unidades vendidas en el período"),
            ColumnDef(name="valores", type="decimal(15,2)", comment="Valor de ventas en moneda local"),
            ColumnDef(name="valores_usd", type="decimal(15,2)", comment="Valor de ventas en USD"),
            ColumnDef(name="market_share", type="decimal(5,2)", comment="Participación de mercado (%)"),
            ColumnDef(name="crecimiento_yoy", type="decimal(5,2)", comment="Crecimiento año contra año (%)"),
        ],
        partition_keys=["idperiodo"],
    ),
]
