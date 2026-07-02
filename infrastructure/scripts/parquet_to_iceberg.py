"""
PySpark script para conversión Parquet → Iceberg.

Lee archivos Parquet de la landing zone (raw/) en S3 y escribe
en tablas Iceberg registradas en Glue Catalog.

Ejecutado por AWS Glue ETL Job (Spark 3.3, Glue 4.0).
"""
import sys
import time

from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql.utils import AnalysisException

from pyspark_helpers import (
    SCHEMA_MAP,
    apply_column_mapping,
    build_s3_read_path,
    determine_write_mode,
    get_glue_database,
)

# --- Argumentos del job ---
args = getResolvedOptions(sys.argv, ["lake_bucket", "JOB_NAME"])
lake_bucket = args["lake_bucket"]

# --- SparkSession con Iceberg + Glue Catalog ---
spark = (
    SparkSession.builder
    .config("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog")
    .config(
        "spark.sql.catalog.glue_catalog.catalog-impl",
        "org.apache.iceberg.aws.glue.GlueCatalog",
    )
    .config("spark.sql.catalog.glue_catalog.warehouse", f"s3://{lake_bucket}/")
    .config(
        "spark.sql.extensions",
        "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    )
    .getOrCreate()
)

# --- Resultados de procesamiento ---
results = {"success": [], "skipped": [], "failed": []}

# --- Procesar cada schema ---
for schema_name, glue_db in SCHEMA_MAP.items():
    print(f"\n{'='*60}")
    print(f"Procesando schema: {schema_name} → database: {glue_db}")
    print(f"{'='*60}")

    # Descubrir tablas del Glue Catalog (no hardcoded)
    try:
        tables = spark.catalog.listTables(f"glue_catalog.{glue_db}")
    except AnalysisException as e:
        print(f"WARNING: No se pudo listar tablas de {glue_db}: {e}")
        continue

    for table in tables:
        table_fqn = f"{glue_db}.{table.name}"
        raw_path = build_s3_read_path(lake_bucket, schema_name, table.name)
        start_time = time.time()

        try:
            # Leer Parquet desde landing zone
            df = spark.read.parquet(raw_path)

            # Verificar si hay datos
            if df.head(1) is None:
                elapsed = time.time() - start_time
                print(f"WARNING: {table_fqn} - sin datos en {raw_path} ({elapsed:.1f}s)")
                results["skipped"].append(table_fqn)
                continue

            # Eliminar columna fecha_carga (agregada por DMS, no existe en Iceberg)
            if "fecha_carga" in df.columns:
                df = df.drop("fecha_carga")

            # Aplicar column mapping para tablas del schema maestros
            if schema_name == "maestros":
                df = apply_column_mapping(df, schema_name, table.name)

            # Escribir en tabla Iceberg
            # overwritePartitions() funciona para ambos casos:
            # - Tablas particionadas: reemplaza solo particiones presentes
            # - Tablas sin particiones: equivale a overwrite completo
            # La función determine_write_mode() documenta esta lógica para tests.
            iceberg_table_id = f"glue_catalog.{glue_db}.{table.name}"
            df.writeTo(iceberg_table_id).overwritePartitions()

            row_count = df.count()
            elapsed = time.time() - start_time
            print(f"OK: {table_fqn} - {row_count} registros ({elapsed:.1f}s)")
            results["success"].append(f"{table_fqn} ({row_count} rows)")

        except AnalysisException as e:
            # Tabla sin archivos Parquet en la landing zone
            elapsed = time.time() - start_time
            error_msg = str(e)
            if "Path does not exist" in error_msg or "Unable to infer schema" in error_msg:
                print(f"WARNING: {table_fqn} - no existen archivos Parquet ({elapsed:.1f}s)")
                results["skipped"].append(table_fqn)
            else:
                print(f"ERROR: {table_fqn} - {error_msg} ({elapsed:.1f}s)")
                results["failed"].append(f"{table_fqn}: {error_msg}")

        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            print(f"ERROR: {table_fqn} - {error_msg} ({elapsed:.1f}s)")
            results["failed"].append(f"{table_fqn}: {error_msg}")


# --- Resumen final ---
print(f"\n{'='*60}")
print("RESUMEN DE EJECUCIÓN")
print(f"{'='*60}")
print(f"SUCCESS: {len(results['success'])} tablas")
print(f"SKIPPED: {len(results['skipped'])} tablas (sin datos)")
print(f"FAILED:  {len(results['failed'])} tablas")

if results["success"]:
    print("\nTablas exitosas:")
    for s in results["success"]:
        print(f"  ✓ {s}")

if results["skipped"]:
    print("\nTablas omitidas (sin datos):")
    for s in results["skipped"]:
        print(f"  ⊘ {s}")

if results["failed"]:
    print("\nTablas con error:")
    for f in results["failed"]:
        print(f"  ✗ {f}")

# --- Exit code: 1 si hay al menos un fallo ---
if results["failed"]:
    print(f"\nJob FAILED: {len(results['failed'])} tabla(s) con error.")
    sys.exit(1)
else:
    print("\nJob SUCCEEDED: todas las tablas procesadas correctamente.")
    sys.exit(0)
