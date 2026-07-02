# Implementation Plan: ingestion-dms

## Overview

Pipeline de ingesta completo: VPC Peering → DMS Serverless (RDS→S3 Parquet) → Glue ETL (Parquet→Iceberg) → Step Functions (orquestación) → EventBridge (schedule). Implementado como CDK stack en Python con entry point independiente, PySpark script para ETL, y tests con CDK assertions + hypothesis PBT.

## Tasks

- [x] 1. Skeleton del stack y entry point
  - [x] 1.1 Crear skeleton de IngestionStack con constructor y parámetros
    - Crear `infrastructure/stacks/ingestion_stack.py` con la clase `IngestionStack(cdk.Stack)` vacía
    - Constructor recibe: `rds_secret_arn`, `datasources_vpc_id`, `lake_bucket_name`, `glue_database_names`, `tag_project`, `tag_environment`, `tag_owner`
    - Aplicar tags con `Tags.of(self).add()` incluyendo `ManagedBy=cdk`
    - _Requirements: 10.1, 10.4, 10.7_

  - [x] 1.2 Crear entry point `app_ingestion.py`
    - Crear `infrastructure/app_ingestion.py` que cargue `.env` via `dotenv`
    - Leer variables: `AWS_ACCOUNT_ID`, `AWS_REGION`, `TAG_PROJECT`, `TAG_ENVIRONMENT`, `TAG_OWNER`, `RDS_SECRET_ARN`, `DATASOURCES_VPC_ID`, `LAKE_BUCKET_NAME`, `GLUE_DB_CRM`, `GLUE_DB_CUP`, `GLUE_DB_IQVIA`, `GLUE_DB_MAESTROS`
    - Validar que ningún parámetro obligatorio sea None o vacío — raise ValueError con nombre de la variable faltante
    - Instanciar `IngestionStack` con los parámetros y `env=cdk.Environment(account, region)`
    - _Requirements: 10.2, 10.8, 10.10_

- [x] 2. Checkpoint — Validar synth del skeleton
  - Ejecutar `cdk synth --app '.venv/bin/python3 app_ingestion.py'` desde `infrastructure/`
  - Verificar que genera template CloudFormation válido (vacío pero sin errores)
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. VPC Peering y conectividad de red
  - [x] 3.1 Implementar VPC Peering Connection
    - Importar VPC de DataSources con `ec2.Vpc.from_lookup(vpc_id=datasources_vpc_id)`
    - Importar VPC default con `ec2.Vpc.from_lookup(is_default=True)`
    - Crear `ec2.CfnVPCPeeringConnection` entre ambas VPCs con auto-accept
    - Habilitar DNS resolution en la conexión de peering
    - _Requirements: 1.1, 1.6_

  - [x] 3.2 Configurar rutas en ambas VPCs
    - Agregar rutas en route tables de subnets isolated de DataSources VPC → destino CIDR VPC default, target peering
    - Agregar rutas en todas las route tables de VPC default → destino 10.100.0.0/16, target peering
    - Iterar sobre `subnet.route_table` de cada subnet para agregar `ec2.CfnRoute`
    - _Requirements: 1.2, 1.3_

  - [x] 3.3 Configurar Security Group para RDS
    - Importar o crear Security Group que permita ingress TCP/5432 desde CIDR de VPC default (172.31.0.0/16)
    - Usar `ec2.CfnSecurityGroupIngress` o `security_group.add_ingress_rule()`
    - _Requirements: 1.4_

- [x] 4. IAM Roles para DMS
  - [x] 4.1 Crear DmsServerlessRole
    - Trust policy para `dms.amazonaws.com`
    - Inline policy S3Access: `s3:PutObject`, `s3:DeleteObject` sobre `arn:aws:s3:::{bucket}/raw/*`; `s3:ListBucket`, `s3:GetBucketLocation` sobre bucket ARN con condition `s3:prefix=raw/*`
    - Inline policy SecretsAccess: `secretsmanager:GetSecretValue`, `secretsmanager:DescribeSecret` sobre `rds_secret_arn`
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 4.2 Crear dms-vpc-role (service-linked)
    - Crear IAM Role `dms-vpc-role` con trust policy `dms.amazonaws.com`
    - Adjuntar managed policy `AmazonDMSVPCManagementRole`
    - Usar `custom_resource` o condición para crearlo solo si no existe
    - _Requirements: 9.6_

- [x] 5. DMS Endpoints y Replication Config
  - [x] 5.1 Crear DMS Source Endpoint (RDS PostgreSQL)
    - `dms.CfnEndpoint` tipo `source`, engine `postgres`
    - Configurar `PostgreSqlSettings` con `secrets_manager_secret_id` y `secrets_manager_access_role_arn`
    - `database_name="pharmassist"`, `ssl_mode="require"`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 5.2 Crear DMS Target Endpoint (S3 Parquet)
    - `dms.CfnEndpoint` tipo `target`, engine `s3`
    - S3Settings: `bucket_name`, `bucket_folder="raw"`, `data_format="parquet"`, `parquet_version="PARQUET_2_0"`, `encoding_type="PLAIN_DICTIONARY"`, `compression_type="SNAPPY"`, `add_column_name=True`, `timestamp_column_name="fecha_carga"`
    - `service_access_role_arn` apuntando a DmsServerlessRole
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 5.3 Crear DMS Replication Config (Serverless full-load)
    - `dms.CfnReplicationConfig` con `replication_type="full-load"`
    - Table mappings JSON con 4 selection rules (crm_interno, closeup, iqvia, maestros) con `table-name="%"`
    - Compute config: min_capacity=1, max_capacity=4, multi_az=False
    - Subnet group con subnets de VPC default, security group con egress al RDS
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 6. Glue ETL Job y PySpark script
  - [x] 6.1 Escribir script PySpark `parquet_to_iceberg.py`
    - Crear `infrastructure/scripts/parquet_to_iceberg.py`
    - Configurar SparkSession con Iceberg + Glue Catalog
    - Implementar SCHEMA_MAP: `crm_interno→pharmassist_crm`, `closeup→pharmassist_cup`, `iqvia→pharmassist_iqvia`, `maestros→pharmassist_maestros`
    - Iterar schemas, descubrir tablas del Glue Catalog, leer Parquet de `raw/{schema}/{table}/`
    - Escribir con `overwritePartitions()` para tablas particionadas, overwrite completo para no particionadas
    - Manejar tablas sin datos (skip + log warning), tablas con error (log + continue)
    - Imprimir resumen final (success/skipped/failed counts)
    - Exit code 1 si hay al menos un fallo, 0 si todo ok
    - _Requirements: 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 5.2, 5.3, 5.11, 5.12, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 6.2 Crear Glue ETL Job en CDK
    - `glue.CfnJob` con nombre `pharmassist-parquet-to-iceberg`
    - Worker type G.1X, workers=2, Glue version 4.0, timeout 60 min
    - Job bookmark DISABLED, max retries 0
    - Script location via CDK Asset (S3 deploy del archivo local)
    - Role: GlueEtlRole (de spec #2, importado por nombre)
    - Default arguments: `--lake_bucket` con el nombre del bucket
    - _Requirements: 5.1, 5.8, 5.9, 5.10, 11.1, 11.2_

- [x] 7. Step Functions State Machine
  - [-] 7.1 Implementar State Machine con ASL
    - Crear `sfn.CfnStateMachine` tipo STANDARD con nombre `pharmassist-ingestion-pipeline`
    - Definir ASL con estados: StartDmsReplication → WaitForDms (60s) → CheckDmsStatus → IsDmsComplete → CheckDmsStopReason → StartGlueJob → WaitForGlue (30s) → CheckGlueStatus → IsGlueComplete → PipelineSucceeded/PipelineFailed
    - Timeout global 3600 segundos
    - Catch en StartDmsReplication y StartGlueJob → PipelineFailed
    - Choice states para detectar DMS failed y Glue FAILED/TIMEOUT/ERROR
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.10_

  - [x] 7.2 Crear StepFunctionsRole (IAM)
    - Trust policy para `states.amazonaws.com`
    - Permisos: `dms:StartReplication`, `dms:DescribeReplications` sobre replication config ARN
    - Permisos: `glue:StartJobRun`, `glue:GetJobRun` sobre el Glue Job ARN
    - Sin wildcards en Action
    - _Requirements: 7.9_

- [x] 8. EventBridge Schedule
  - [x] 8.1 Crear EventBridge Scheduler Schedule
    - `scheduler.CfnSchedule` con nombre `pharmassist-ingestion-schedule`
    - Expression: `cron(0 2 * * ? *)`, timezone UTC
    - Target: State Machine ARN con input `{}`
    - State: DISABLED (dev)
    - Retry policy: max 2 retries, 60 min max event age
    - Flexible time window OFF
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6, 8.7_

  - [x] 8.2 Crear SchedulerRole (IAM)
    - Trust policy para `scheduler.amazonaws.com`
    - Permiso `states:StartExecution` limitado al ARN de la State Machine
    - _Requirements: 8.5_

- [x] 9. CloudFormation Outputs
  - [x] 9.1 Agregar CfnOutputs al stack
    - Output `StateMachineArn`: ARN de la State Machine
    - Output `GlueJobName`: `pharmassist-parquet-to-iceberg`
    - Output `ScheduleArn`: ARN del EventBridge Schedule
    - Exactamente 3 outputs
    - _Requirements: 10.6_

- [x] 10. Checkpoint — Validar synth completo
  - Ejecutar `cdk synth --app '.venv/bin/python3 app_ingestion.py'` desde `infrastructure/`
  - Verificar que el template contiene todos los recursos: VPC Peering, Routes, SG, DMS Endpoints, Replication Config, Glue Job, State Machine, Schedule, IAM Roles, Outputs
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. CDK Assertion Tests
  - [x] 11.1 Crear test file y fixtures
    - Crear `infrastructure/tests/unit/test_ingestion_stack.py`
    - Fixture que sintetiza IngestionStack con parámetros mock
    - Importar `aws_cdk.assertions.Template`
    - _Requirements: 10.3_

  - [x] 11.2 Escribir CDK assertion tests (13 tests)
    - Test VPC Peering Connection existe con CIDRs correctos
    - Test rutas en ambas VPCs con destinos correctos
    - Test Security Group ingress TCP/5432 desde 172.31.0.0/16
    - Test DMS Source Endpoint: engine=postgres, SSL=require, SecretsManager config
    - Test DMS Target Endpoint: engine=s3, Parquet, SNAPPY, bucket folder=raw
    - Test Replication Config: full-load, capacity 1-4, multi_az=false
    - Test Glue Job: nombre, worker G.1X, workers=2, version 4.0, timeout 60min
    - Test State Machine: tipo STANDARD, timeout 3600s
    - Test EventBridge Schedule: cron, state=DISABLED, target=state machine
    - Test IAM no wildcards: ninguna policy tiene Action="*"
    - Test IAM DmsServerlessRole: trust policy y permisos específicos
    - Test Outputs: exactamente 3 CfnOutputs
    - Test Tags: Project, Environment, Owner, ManagedBy en recursos
    - _Requirements: 9.5, 10.3, 10.6_

- [x] 12. Property-Based Tests (PySpark logic)
  - [x] 12.1 Extraer funciones puras del script PySpark para testing
    - Extraer `get_glue_database(schema_name)` como función importable
    - Extraer `build_s3_read_path(bucket, schema_name, table_name)` como función importable
    - Extraer lógica de decisión de particionado como función importable
    - Crear módulo `infrastructure/scripts/pyspark_helpers.py` con las funciones puras
    - Actualizar `parquet_to_iceberg.py` para importar desde `pyspark_helpers`
    - _Requirements: 11.4, 11.5_

  - [ ]* 12.2 Write property test: Schema-to-database mapping
    - **Property 1: Schema-to-database mapping is correct and complete**
    - Test con `st.sampled_from(["crm_interno", "closeup", "iqvia", "maestros"])` para válidos
    - Test con `st.text()` filtrado para strings inválidos → debe retornar None o raise
    - **Validates: Requirements 5.4, 5.5, 5.6, 5.7, 11.4**

  - [ ]* 12.3 Write property test: S3 read path construction
    - **Property 2: S3 read path construction follows convention**
    - Generar schema_name y table_name como strings no vacíos sin path separators
    - Verificar patrón `s3://{bucket}/raw/{schema}/{table}/` exacto
    - **Validates: Requirements 5.2, 11.4**

  - [ ]* 12.4 Write property test: Idempotent write
    - **Property 3: Idempotent write produces identical results**
    - Mock del writer Iceberg, verificar que dos ejecuciones producen mismo estado
    - **Validates: Requirements 5.3, 6.1, 6.7**

  - [ ]* 12.5 Write property test: Partition strategy selection
    - **Property 4: Partition strategy selection matches table definition**
    - Generar metadata de tablas con/sin partition keys
    - Verificar que se usa `overwritePartitions()` vs overwrite completo según corresponda
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5**

  - [ ]* 12.6 Write property test: Resilient processing
    - **Property 5: Resilient processing continues despite individual failures**
    - Generar lista de N tablas con K fallos aleatorios inyectados
    - Verificar que (N-K) tablas se procesan exitosamente
    - **Validates: Requirements 5.11, 5.12, 11.6, 11.8**

  - [ ]* 12.7 Write property test: Exit code reflects failure state
    - **Property 6: Exit code reflects failure state**
    - Generar combinaciones de success/failure, verificar exit code 1 si hay fallos, 0 si no
    - **Validates: Requirements 11.9**

  - [ ]* 12.8 Write property test: Progress logging
    - **Property 7: Progress logging contains required fields**
    - Generar resultados de procesamiento, verificar que log contiene database.table, row count, tiempo
    - **Validates: Requirements 11.7**

  - [ ]* 12.9 Write property test: Missing parameter validation
    - **Property 8: Missing parameter validation fails fast**
    - Generar combinaciones de parámetros con al menos uno None/vacío
    - Verificar que raise ValueError con nombre de la variable faltante
    - **Validates: Requirements 10.10**

- [x] 13. Checkpoint — Ejecutar todos los tests
  - Ejecutar `pytest infrastructure/tests/unit/test_ingestion_stack.py -v` — 13 CDK assertion tests
  - Ejecutar `pytest infrastructure/tests/unit/test_pyspark_logic.py -v` — 8 property tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Integration tests (post-deploy)
  - [ ]* 14.1 Escribir integration tests
    - Crear `infrastructure/tests/integration/test_ingestion_pipeline.py`
    - Test DMS connectivity: `dms:TestConnection` al source endpoint
    - Test full pipeline run: StartExecution, wait for SUCCEEDED
    - Test row count validation: comparar RDS COUNT(*) vs Athena COUNT(*) para tablas clave
    - Test partition pruning: query con WHERE en columna de partición, verificar scan reducido
    - Test idempotency: ejecutar pipeline dos veces, verificar mismos row counts
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [x] 15. Final checkpoint
  - Verificar `cdk synth` exitoso
  - Verificar todos los unit tests pasan
  - Verificar todos los property tests pasan
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- CDK assertion tests validate infrastructure correctness via template inspection
- Integration tests (task 14) require a deployed stack — run after `cdk deploy`
- El entry point va en task 1.2 (temprano) para habilitar `cdk synth` en checkpoint 2
- El PySpark script (task 6.1) extrae funciones puras a `pyspark_helpers.py` (task 12.1) para testabilidad

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["3.1", "4.1", "4.2"] },
    { "id": 2, "tasks": ["3.2", "3.3", "5.1", "5.2"] },
    { "id": 3, "tasks": ["5.3", "6.1"] },
    { "id": 4, "tasks": ["6.2", "7.1", "7.2"] },
    { "id": 5, "tasks": ["8.1", "8.2"] },
    { "id": 6, "tasks": ["9.1"] },
    { "id": 7, "tasks": ["11.1", "12.1"] },
    { "id": 8, "tasks": ["11.2", "12.2", "12.3", "12.4", "12.5", "12.6", "12.7", "12.8", "12.9"] },
    { "id": 9, "tasks": ["14.1"] }
  ]
}
```
