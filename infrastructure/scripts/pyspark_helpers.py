"""
Funciones puras extraídas del script PySpark para testing.

Este módulo contiene lógica de negocio que puede testearse sin
dependencias de PySpark, Glue ni AWS. Importable desde tests unitarios
y property-based tests.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional


# --- Schema mapping: RDS schema → Glue database ---
SCHEMA_MAP: dict[str, str] = {
    "crm_interno": "pharmassist_crm",
    "closeup": "pharmassist_cup",
    "iqvia": "pharmassist_iqvia",
    "maestros": "pharmassist_maestros",
}


def get_glue_database(schema_name: str) -> Optional[str]:
    """Mapea un schema de RDS al nombre de Glue Database correspondiente.

    Args:
        schema_name: Nombre del schema en RDS (ej: "crm_interno").

    Returns:
        Nombre del Glue Database (ej: "pharmassist_crm"), o None si el
        schema no está en el mapping.
    """
    return SCHEMA_MAP.get(schema_name)


def build_s3_read_path(bucket: str, schema_name: str, table_name: str) -> str:
    """Construye el path S3 de lectura para una tabla en la landing zone.

    Sigue la convención: s3://{bucket}/raw/{schema_name}/{table_name}/

    Args:
        bucket: Nombre del bucket S3 del data lake.
        schema_name: Nombre del schema RDS (ej: "crm_interno").
        table_name: Nombre de la tabla (ej: "doctor").

    Returns:
        Path S3 completo con trailing slash.
    """
    return f"s3://{bucket}/raw/{schema_name}/{table_name}/"


def determine_write_mode(partition_keys: list[str]) -> str:
    """Decide la estrategia de escritura Iceberg según partition keys.

    - Si la tabla tiene partition keys → "overwritePartitions"
      (reemplaza solo particiones presentes en el DataFrame)
    - Si la tabla NO tiene partition keys → "overwrite"
      (reemplazo completo de la tabla)

    Args:
        partition_keys: Lista de nombres de columnas de partición.
                       Lista vacía indica tabla sin particiones.

    Returns:
        "overwritePartitions" o "overwrite" según corresponda.
    """
    if partition_keys:
        return "overwritePartitions"
    return "overwrite"


# --- Column mapping: RDS columns → Glue Catalog columns ---
COLUMN_MAPPING: dict[str, dict[str, str]] = {
    "maestros.maestro_medicos": {
        "cod_interno": "doctor_id_crm",
        "cod_closeup": "cdgmedico_cup",
        "nombre_verificado": "nombre",
        "fecha_mapeo": "fecha_actualizacion",
    },
    "maestros.maestro_integrador_producto": {
        "cod_interno": "producto_id_crm",
        "cod_closeup": "cdgmarca_cup",
        "cod_iqvia": "idpresentacion_iqvia",
        "nombre_unificado": "nombre_interno",
        "fecha_mapeo": "fecha_actualizacion",
    },
    "maestros.familia_interno_a_marca_cup": {
        "cod_interno": "familia_producto_id",
        "codigo_marca": "cdgmarca_cup",
        "relacion": "confianza_match",
    },
}

# Transformación de valores para la columna `relacion` → `confianza_match`
_RELACION_TO_CONFIANZA: dict[str, Decimal] = {
    "exacta": Decimal("1.00"),
    "parcial": Decimal("0.70"),
    "generico": Decimal("0.40"),
}


def apply_column_mapping(
    df: "DataFrame",
    schema_name: str,
    table_name: str,
) -> "DataFrame":
    """Aplica renombrado de columnas según COLUMN_MAPPING.

    Args:
        df: DataFrame PySpark con columnas originales de RDS.
        schema_name: Schema RDS (ej: "maestros").
        table_name: Nombre de la tabla (ej: "maestro_medicos").

    Returns:
        DataFrame con columnas renombradas según el mapping.
        Columnas sin mapping se descartan.
        Columnas destino sin origen se agregan como NULL.

    Raises:
        ValueError: Si una columna fuente del mapping no existe en el DataFrame.
    """
    from pyspark.sql import functions as F
    from pyspark.sql.types import DecimalType

    key = f"{schema_name}.{table_name}"
    mapping = COLUMN_MAPPING.get(key)

    if mapping is None:
        # No hay mapping definido para esta tabla — retornar sin cambios
        return df

    # Validar que todas las columnas fuente del mapping existen en el DataFrame
    df_columns = set(df.columns)
    for source_col in mapping:
        if source_col not in df_columns:
            raise ValueError(
                f"Columna fuente '{source_col}' no existe en tabla "
                f"'{key}'. Columnas disponibles: {sorted(df_columns)}"
            )

    # Aplicar renombrado y transformaciones
    select_exprs = []
    for source_col, dest_col in mapping.items():
        if source_col == "relacion" and dest_col == "confianza_match":
            # Transformación especial: string → decimal
            expr = (
                F.when(F.col(source_col) == "exacta", F.lit(_RELACION_TO_CONFIANZA["exacta"]))
                .when(F.col(source_col) == "parcial", F.lit(_RELACION_TO_CONFIANZA["parcial"]))
                .when(F.col(source_col) == "generico", F.lit(_RELACION_TO_CONFIANZA["generico"]))
                .otherwise(F.lit(None))
                .cast(DecimalType(3, 2))
                .alias(dest_col)
            )
        else:
            expr = F.col(source_col).alias(dest_col)
        select_exprs.append(expr)

    return df.select(select_exprs)


def detect_schema_drift(
    df: "DataFrame",
    schema_name: str,
    table_name: str,
) -> dict[str, list[str]]:
    """Detecta drift entre el schema actual del DataFrame y el mapping documentado.

    Compara las columnas presentes en el DataFrame contra las columnas fuente
    registradas en COLUMN_MAPPING para la tabla indicada. Identifica columnas
    no documentadas (extra) y columnas documentadas pero ausentes (missing).

    Args:
        df: DataFrame PySpark con columnas actuales.
        schema_name: Schema RDS (ej: "maestros").
        table_name: Nombre de la tabla (ej: "maestro_medicos").

    Returns:
        Dict con:
        - 'extra_columns': columnas en el DataFrame que no están en el mapping (como fuente)
        - 'missing_columns': columnas en el mapping (fuente) que no están en el DataFrame
    """
    table_key = f"{schema_name}.{table_name}"

    if table_key not in COLUMN_MAPPING:
        return {"extra_columns": [], "missing_columns": []}

    mapping = COLUMN_MAPPING[table_key]
    mapped_source_columns = set(mapping.keys())
    actual_columns = set(df.columns)

    extra_columns = sorted(actual_columns - mapped_source_columns)
    missing_columns = sorted(mapped_source_columns - actual_columns)

    return {"extra_columns": extra_columns, "missing_columns": missing_columns}
