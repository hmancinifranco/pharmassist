"""Table definitions for the Maestros domain (pharmassist_maestros).

Contains 3 cross-source integration/master tables that unify data
from CRM, CloseUp, and IQVIA sources: unified doctor master,
product integrator, and internal family to CloseUp brand mapping.
"""

from table_definitions import ColumnDef, TableDef

MAESTROS_TABLES: list[TableDef] = [
    # 1. maestro_medicos — Maestro unificado de médicos (integra CRM + CloseUp)
    TableDef(
        name="maestro_medicos",
        description="Maestro unificado de médicos (integra CRM + CloseUp)",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único del registro"),
            ColumnDef(name="doctor_id_crm", type="int", comment="FK al doctor en CRM"),
            ColumnDef(name="cdgmedico_cup", type="int", comment="Código médico en CloseUp"),
            ColumnDef(name="matricula_nacional", type="string", comment="Matrícula nacional del médico"),
            ColumnDef(name="nombre", type="string", comment="Nombre del médico"),
            ColumnDef(name="apellido", type="string", comment="Apellido del médico"),
            ColumnDef(name="especialidad", type="string", comment="Especialidad médica"),
            ColumnDef(name="zona", type="string", comment="Zona geográfica asignada"),
            ColumnDef(name="localidad", type="string", comment="Localidad del médico"),
            ColumnDef(name="provincia", type="string", comment="Provincia"),
            ColumnDef(name="fuente_primaria", type="string", comment="Fuente de datos primaria (CRM o CloseUp)"),
            ColumnDef(name="fecha_actualizacion", type="timestamp", comment="Última fecha de actualización"),
            ColumnDef(name="activo", type="boolean", comment="Si el registro está activo"),
        ],
        partition_keys=[],
    ),
    # 2. maestro_integrador_producto — Maestro integrador de productos (mapea CRM → IQVIA)
    TableDef(
        name="maestro_integrador_producto",
        description="Maestro integrador de productos (mapea CRM → IQVIA)",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único del registro"),
            ColumnDef(name="producto_id_crm", type="int", comment="FK al producto en CRM"),
            ColumnDef(name="idpresentacion_iqvia", type="int", comment="ID presentación en IQVIA"),
            ColumnDef(name="cdgmarca_cup", type="int", comment="Código marca en CloseUp"),
            ColumnDef(name="nombre_interno", type="string", comment="Nombre interno del producto"),
            ColumnDef(name="nombre_iqvia", type="string", comment="Nombre del producto en IQVIA"),
            ColumnDef(name="nombre_cup", type="string", comment="Nombre del producto en CloseUp"),
            ColumnDef(name="familia", type="string", comment="Familia de producto"),
            ColumnDef(name="linea", type="string", comment="Línea comercial"),
            ColumnDef(name="activo", type="boolean", comment="Si el mapeo está activo"),
            ColumnDef(name="fecha_actualizacion", type="timestamp", comment="Última fecha de actualización"),
        ],
        partition_keys=[],
    ),
    # 3. familia_interno_a_marca_cup — Mapeo familia interna a marca CloseUp
    TableDef(
        name="familia_interno_a_marca_cup",
        description="Mapeo familia interna a marca CloseUp",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único del registro"),
            ColumnDef(name="familia_producto_id", type="int", comment="FK a familia de producto interna"),
            ColumnDef(name="cdgmarca_cup", type="int", comment="Código marca en CloseUp"),
            ColumnDef(name="nombre_familia", type="string", comment="Nombre de la familia interna"),
            ColumnDef(name="nombre_marca_cup", type="string", comment="Nombre de la marca en CloseUp"),
            ColumnDef(name="confianza_match", type="decimal(3,2)", comment="Nivel de confianza del match (0.00-1.00)"),
            ColumnDef(name="fecha_mapeo", type="date", comment="Fecha en que se estableció el mapeo"),
            ColumnDef(name="activo", type="boolean", comment="Si el mapeo está activo"),
        ],
        partition_keys=[],
    ),
]
