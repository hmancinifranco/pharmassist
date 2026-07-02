# Implementation Plan: data-lake-foundation

## Overview

Implementar el CDK stack `DataLakeStack` que provisiona la infraestructura fundacional del data lake de PharmAssist: bucket S3 con prefijos por dominio, 4 Glue Databases con 51 tablas Iceberg registradas declarativamente, IAM roles con least privilege, y un Athena Workgroup para validación. Se usa un helper `register_iceberg_table()` para reducir boilerplate y centralizar la configuración Iceberg de las 51 tablas.

## Tasks

- [x] 1. Create data model and table definitions infrastructure
  - [x] 1.1 Create `TableDef` and `ColumnDef` dataclasses with `__init__.py`
    - Create `infrastructure/table_definitions/__init__.py`
    - Define `ColumnDef` dataclass with fields: name (str), type (str), comment (str)
    - Define `TableDef` dataclass with fields: name (str), columns (list[ColumnDef]), partition_keys (list[str]), description (str)
    - Export `ALL_TABLES` dict and individual domain lists
    - _Requirements: 3.6, 4.1, 5.1, 6.1_

  - [x] 1.2 Create table definitions for CRM domain (25 tables)
    - Create `infrastructure/table_definitions/crm_tables.py`
    - Define `CRM_TABLES: list[TableDef]` with all 25 tables: apm, doctor, zona, especialidad, cartera_medica, cartera_medica_estado, linea, linea_apm, familia_producto, catalogo_productos, ciclo, grilla, categoria, detalle_promocion_producto, agenda, agenda_producto, agenda_muestra, datos_visita, visita_planificada, tag, tag_doctor, ultima_milla_medico, ultima_milla_marca, ultima_milla_objetivo, linea_especializacion
    - Include full column definitions with PostgreSQL→Iceberg type mapping
    - Set `partition_keys=["fecha_inicio"]` for `agenda` table
    - _Requirements: 3.1, 3.2, 3.6, 3.7_

  - [x] 1.3 Create table definitions for CloseUp domain (10 tables)
    - Create `infrastructure/table_definitions/cup_tables.py`
    - Define `CUP_TABLES: list[TableDef]` with all 10 tables: medico, marca, mercado, mercado_producto, representante, prescripcion, medico_rep_novisitado, medico_representante, medico_visitado, mercado_modulo_linea
    - Include full column definitions with type mapping
    - Set `partition_keys=["anio", "mes", "cdgreg_pmix"]` for `prescripcion` table
    - _Requirements: 4.1, 4.2, 4.5_

  - [x] 1.4 Create table definitions for IQVIA domain (13 tables)
    - Create `infrastructure/table_definitions/iqvia_tables.py`
    - Define `IQVIA_TABLES: list[TableDef]` with all 13 tables: dim_periodo, dim_droga, dim_forma_farmaceutica, dim_laboratorio, dim_clase_terapeutica, dim_presentacion, dim_geografia, dim_clase, dim_combinacion_droga, rel_presentacion_droga, rel_presentacion_forma, rel_producto_laboratorio, fact_mercado_valor
    - Include full column definitions with type mapping
    - Set `partition_keys=["idperiodo"]` for `fact_mercado_valor` table
    - _Requirements: 5.1, 5.2_

  - [x] 1.5 Create table definitions for Maestros domain (3 tables)
    - Create `infrastructure/table_definitions/maestros_tables.py`
    - Define `MAESTROS_TABLES: list[TableDef]` with 3 tables: maestro_medicos, maestro_integrador_producto, familia_interno_a_marca_cup
    - Include full column definitions with type mapping
    - All tables have empty `partition_keys` (low volume, no partitioning)
    - _Requirements: 6.1, 6.4_

- [x] 2. Create helper function and stack skeleton
  - [x] 2.1 Create helper function `register_iceberg_table()` in `infrastructure/constructs/iceberg_table.py`
    - Implement function that receives `scope`, `database_name`, `bucket`, `domain_prefix`, `table_def`
    - Generate `CfnTable` with full Iceberg configuration: table_type=ICEBERG, format-version=2, metadata_location, Iceberg InputFormat/OutputFormat/SerDe
    - Separate partition key columns from storage descriptor columns
    - Use construct ID pattern `{domain_prefix}-{table_name}-table` to avoid duplicates
    - _Requirements: 3.3, 3.4, 3.5, 7.1, 7.2, 7.3, 7.4_

  - [x] 2.2 Create skeleton `DataLakeStack` class in `infrastructure/stacks/data_lake_stack.py`
    - Define class inheriting from `aws_cdk.Stack`
    - Accept constructor params: `tag_project`, `tag_environment`, `tag_owner`
    - Apply tags via `Tags.of(self).add()` including `ManagedBy=cdk`
    - Leave method stubs for `_create_bucket()`, `_create_databases()`, `_register_tables()`, `_create_iam_roles()`, `_create_athena_workgroup()`, `_create_outputs()`
    - _Requirements: 10.1, 10.6_

  - [x] 2.3 Create entry point `infrastructure/app_datalake.py`
    - Instantiate `DataLakeStack` with `cdk.Environment` from `.env` vars
    - Load config via `dotenv` from project root
    - Pass `tag_project`, `tag_environment`, `tag_owner` from env vars with defaults
    - Call `app.synth()`
    - _Requirements: 10.2, 10.3, 10.5, 10.7_

- [x] 3. Checkpoint — Validate empty stack synthesizes
  - Run `cdk synth --app '.venv/bin/python3 app_datalake.py'` from `infrastructure/`
  - Ensure exit code 0 and valid CloudFormation template is generated
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement S3 bucket and Glue databases
  - [x] 4.1 Implement S3 bucket with full configuration
    - Create bucket with SSE-S3 encryption, versioning enabled, block all public access
    - Add 3 lifecycle rules: archive tagged objects after 365d, delete noncurrent versions after 90d, abort incomplete multipart after 7d
    - Set removal_policy=DESTROY and auto_delete_objects=True for dev environment
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.10_

  - [x] 4.2 Implement 4 Glue Databases (CRM, CloseUp, IQVIA, Maestros)
    - Create `CfnDatabase` for each domain with correct name, description, and location_uri
    - Use `catalog_id=cdk.Aws.ACCOUNT_ID`
    - Location URIs: `s3://{bucket}/crm/`, `s3://{bucket}/cup/`, `s3://{bucket}/iqvia/`, `s3://{bucket}/maestros/`
    - Include source and cadence in description
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 5. Register all 51 Iceberg tables
  - [x] 5.1 Register 25 CRM Iceberg tables using helper
    - Loop over `CRM_TABLES` and call `register_iceberg_table()` for each
    - Use `domain_prefix="crm"` and `database_name="pharmassist_crm"`
    - Verify `agenda` table gets partition key `fecha_inicio`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 5.2 Register 10 CloseUp Iceberg tables using helper
    - Loop over `CUP_TABLES` and call `register_iceberg_table()` for each
    - Use `domain_prefix="cup"` and `database_name="pharmassist_cup"`
    - Verify `prescripcion` table gets partition keys `anio, mes, cdgreg_pmix`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 5.3 Register 13 IQVIA Iceberg tables using helper
    - Loop over `IQVIA_TABLES` and call `register_iceberg_table()` for each
    - Use `domain_prefix="iqvia"` and `database_name="pharmassist_iqvia"`
    - Verify `fact_mercado_valor` table gets partition key `idperiodo`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 5.4 Register 3 Maestros Iceberg tables using helper
    - Loop over `MAESTROS_TABLES` and call `register_iceberg_table()` for each
    - Use `domain_prefix="maestros"` and `database_name="pharmassist_maestros"`
    - Verify no partition keys are set
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 6. Implement IAM roles and Athena workgroup
  - [x] 6.1 Implement IAM roles (GlueCrawlerRole + GlueEtlRole)
    - Create `GlueCrawlerRole` with trust policy for `glue.amazonaws.com`, managed policy `AWSGlueServiceRole`, S3 read-only on lake bucket, Glue Catalog write permissions
    - Create `GlueEtlRole` with trust policy for `glue.amazonaws.com`, managed policy `AWSGlueServiceRole`, S3 read-write on lake bucket, Glue Catalog read-write permissions
    - Scope S3 permissions to bucket ARN and `{bucket_arn}/*`
    - No wildcard actions in any policy statement
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 6.2 Implement Athena Workgroup (pharmassist-validation)
    - Create `CfnWorkGroup` named `pharmassist-validation` in ENABLED state
    - Configure output location to `s3://{bucket}/athena-results/`
    - Set bytes_scanned_cutoff_per_query to 104,857,600 (100 MB)
    - Enable enforce_work_group_configuration=True
    - Set engine version to "Athena engine version 3"
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 6.3 Add CfnOutputs (6 outputs)
    - Export: LakeBucketName, CrmDatabaseName, CupDatabaseName, IqviaDatabaseName, MaestrosDatabaseName, AthenaWorkgroupName
    - _Requirements: 10.4_

- [x] 7. Checkpoint — Validate full stack synthesizes correctly
  - Run `cdk synth --app '.venv/bin/python3 app_datalake.py'` from `infrastructure/`
  - Verify template contains: 1 S3 bucket, 4 Glue databases, 51 CfnTable resources, 2 IAM roles, 1 Athena workgroup, 6 outputs
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Write CDK assertion tests and property-based tests
  - [x] 8.1 Write CDK assertion tests (unit tests)
    - Create `infrastructure/tests/unit/test_data_lake_stack.py`
    - Test bucket has SSE-S3 encryption
    - Test bucket blocks all public access
    - Test bucket has 3 lifecycle rules
    - Test exactly 4 Glue databases exist
    - Test total of 51 CfnTable resources
    - Test CRM has 25 tables, CloseUp has 10, IQVIA has 13, Maestros has 3
    - Test `agenda` table has partition key `fecha_inicio`
    - Test `prescripcion` table has 3 partition keys
    - Test `fact_mercado_valor` table has partition key `idperiodo`
    - Test IAM roles have no wildcard actions
    - Test IAM S3 permissions scoped to lake bucket ARN
    - Test Athena workgroup has 100MB limit, enforce=true, engine v3
    - Test stack has exactly 6 CfnOutput resources
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1-2.7, 3.1-3.7, 4.1-4.5, 5.1-5.4, 6.1-6.4, 8.1-8.7, 9.1-9.5, 10.4_

  - [ ]* 8.2 Write property test: Iceberg Configuration Invariant
    - Create `infrastructure/tests/unit/test_iceberg_table_properties.py`
    - **Property 1: Iceberg Configuration Invariant**
    - Use `hypothesis` library with custom strategy for valid `TableDef` instances
    - Verify for any valid TableDef and domain: table_type=ICEBERG, format-version=2, correct metadata_location pattern, correct location pattern, Iceberg InputFormat/OutputFormat/SerDe, table_type=EXTERNAL_TABLE
    - Minimum 100 iterations
    - **Validates: Requirements 3.3, 3.4, 3.5, 4.3, 4.4, 5.3, 5.4, 6.2, 6.3, 7.1, 7.2, 7.3**

  - [ ]* 8.3 Write property test: Column Preservation
    - **Property 2: Column Preservation**
    - Verify for any valid TableDef with N columns: StorageDescriptor contains exactly the non-partition-key columns with correct names and types
    - Minimum 100 iterations
    - **Validates: Requirements 3.6**

  - [ ]* 8.4 Write property test: Partition Key Handling
    - **Property 3: Partition Key Handling**
    - Verify for any valid TableDef with non-empty partition_keys: partition_keys list contains correct columns with correct types, partition key columns do NOT appear in StorageDescriptor columns
    - Verify for any valid TableDef with empty partition_keys: output has partition_keys as None
    - Minimum 100 iterations
    - **Validates: Requirements 3.2, 3.7, 4.2, 5.2, 6.4, 7.4**

- [x] 9. Final checkpoint — Run all tests and validate
  - Run `pytest infrastructure/tests/` and ensure all tests pass
  - Run `cdk synth` one final time to confirm no regressions
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation — `cdk synth` is the primary validation mechanism
- Property tests validate the `register_iceberg_table()` helper with generated inputs (hypothesis library)
- CDK assertion tests validate the synthesized CloudFormation template structure
- The entry point (`app_datalake.py`) is created early (task 2.3) per steering rules to enable `cdk synth` at checkpoint 3
- Table definitions are large files (~200-500 lines each) — use chunked writes per large-file-writes steering
- Deploy to AWS (`cdk deploy`) and post-deploy validation are NOT included — they are manual operations outside this spec's coding scope

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3"] },
    { "id": 4, "tasks": ["4.1", "4.2"] },
    { "id": 5, "tasks": ["5.1", "5.2", "5.3", "5.4"] },
    { "id": 6, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 7, "tasks": ["8.1", "8.2", "8.3", "8.4"] }
  ]
}
```
