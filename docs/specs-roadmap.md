# Specs Roadmap — PharmAssist Road to Prod

> Evolución del prototipo PharmAssist hacia un MLP productivo con data lake, carriles de respuesta diferenciados y experiencia async.
> Basado en el diseño de `docs/road-to-prod.md`.

## Leyenda de status

| Emoji | Estado |
|-------|--------|
| 🔴 | Not started |
| 🟡 | In progress |
| 🟢 | Completed |
| ⚪ | On hold |
| ⚫ | Cancelled |

## Specs

| # | Spec | Fase | Status | Dependencias | Notas |
|---|------|------|--------|-------------|-------|
| 1 | `data-sources-simulation` | 1 | 🟢 | — | VPC "externa" + RDS con schemas CRM, CloseUp, IQVIA + datos sintéticos. Incluye tablas UltimaMilla |
| 2 | `data-lake-foundation` | 1 | 🟢 | #1 | S3 bucket lake + Glue Catalog + Iceberg tables base |
| 3 | `ingestion-dms` | 1 | 🟢 | #1, #2 | DMS Serverless: RDS → S3 Parquet → Glue ETL → Iceberg |
| 4 | `maestros-integration` | 1 | 🟢 | #2 | Tablas maestras de integración (producto, médicos, familia→marca CUP). Validación cross-source |
| 5 | `athena-cross-source` | 2 | 🔴 | #3, #4 | Athena workgroup + 15 queries de validación priorizadas por el cliente |
| 6 | `dynamo-refill-nightly` | 2 | 🔴 | #5 | Glue ETL nocturno: Iceberg → DynamoDB (hot path). Incluye UltimaMilla. EventBridge schedule |
| 7 | `semantic-layer` | 3 | 🔴 | #5 | `semantic_layer.yaml`: ontología, entidades, métricas (EVO TRM, shares), queries canónicas, reglas |
| 8 | `agent-warm-tools` | 3 | 🔴 | #5, #7 | Tools del agente que queryean Athena. Carril conversacional. Routing por tipo de pregunta |
| 9 | `redis-warm-cache` | 3 | 🔴 | #6, #8 | ElastiCache Serverless + KPIs pre-computados (UltimaMilla). Fallback Redis → Athena |
| 10 | `semantic-graph-neptune` | 3+ | 🔴 | #7 | Migrar ontología YAML a Neptune Analytics. Grafo de entidades + datasets. openCypher |
| 11 | `async-analysis` | 4 | 🔴 | #8, #9 | SQS + Lambda worker + tool `despachar_analisis_profundo` |
| 12 | `async-notifications` | 4 | 🔴 | #11 | WebSocket push + UI: chip "en curso", panel de resultados |
| 13 | `model-routing` | 5 | 🔴 | #8, #9 | Escalonamiento de modelos por carril + prompt caching |
| 14 | `observability-lake` | 5 | 🔴 | #11 | Métricas por carril, alertas CloudWatch, dashboards operativos |
| 15 | `load-testing` | 5 | 🔴 | #14 | Perfil de carga 50-200 APMs, validación de SLOs |

## Fases

| Fase | Nombre | Duración est. | Objetivo |
|------|--------|---------------|----------|
| 1 | Ingesta y Lake | 3-4 semanas | Datos reales (simulados) en S3 Iceberg, queryeables con Athena |
| 2 | Hot path productivo | 2 semanas | Agente actual funciona con datos del lake (via DynamoDB refill) |
| 3 | Carril conversacional | 3 semanas | Agente responde preguntas cross-source con Athena + Redis |
| 3+ | Grafo semántico | 2-3 semanas | Migrar ontología YAML a Neptune Analytics (opcional, no bloquea Fase 4) |
| 4 | Carril async | 3 semanas | Análisis profundos sin bloquear al APM |
| 5 | Hardening | 2 semanas | Observabilidad, load testing, optimización de costos |

## CDK Stacks

| Stack | Contenido | Lifecycle |
|-------|-----------|-----------|
| `DataSourcesStack` | VPC externa + RDS (simulación de warehouses) | Se destruye cuando ya no se necesite simular |
| `DataLakeStack` | S3, Glue, DMS, Athena, ElastiCache, SQS, Neptune Analytics | Permanente |
| `PharmAssistStack` | DynamoDB, Lambda, API, CloudFront, AgentCore (existente) | Permanente |

## Documentos de referencia

- `docs/road-to-prod.md` — diseño arquitectónico completo
- `docs/research-external-schemas.md` — schemas de las 3 fuentes + maestros + queries de validación + actualización con datos reales del cliente
- `docs/DescripcionesTablas.docx` — estructura real de tablas por fuente (del cliente)
- `docs/Preguntas con Prioridades y Origen - Comentarios.docx` — 15 preguntas priorizadas con fuentes y carriles

## Notas

- Actualizar este archivo al arrancar, pausar, completar o cancelar cualquier spec
- Agregar filas cuando se descubran specs nuevos durante el desarrollo
- Las dependencias indican qué specs deben estar 🟢 antes de arrancar
- Cada spec sigue la metodología: `requirements.md` → `design.md` → `tasks.md`
- Al completar un spec, agregar entrada en "Notas de cierre" abajo

---

## Notas de cierre por spec

### #1 `data-sources-simulation` — cerrado

**Decisiones tomadas:**
- Un solo RDS PostgreSQL con 4 schemas (no 3 instancias separadas) — ahorra costo, suficiente para simulación
- VPC isolated + VPC Endpoints para SSM (no NAT gateway) — ahorra ~$45/mes
- Bastion t4g.nano con SSM Session Manager — acceso seguro sin SSH keys ni IP pública
- Modo `light` vs `full` en config.py — permite validación rápida (~77s) o volúmenes productivos

**Desvíos del plan original:**
- `executemany` de psycopg2 es inaceptablemente lento via túnel SSM (~80s para 500 rows). Se migró todo a `execute_values` (bulk insert) que es 50x más rápido
- Se creó `app_datasources.py` como entry point CDK separado porque `PharmAssistStack` falla en synth sin `pip` disponible (Lambda bundling)
- Se agregó `kill_connections.py` como utilidad para limpiar conexiones zombie antes de DROP SCHEMA

**Gotchas para specs siguientes:**
- El túnel SSM tiene idle timeout — mantener conexión activa durante operaciones largas
- Para el spec #3 (DMS), el RDS ya tiene datos. DMS necesita VPC Peering entre la VPC externa (10.100.0.0/16) y la VPC donde viva el lake
- Los volúmenes en modo `light` son suficientes para validar queries pero no para medir performance de Athena. Usar modo `full` cuando se necesite benchmarking real
- `dim_clase` de IQVIA y `dim_clase_terapeutica` son tablas distintas (una para fact_mercado_valor, otra para dim_presentacion)

### #2 `data-lake-foundation` — cerrado

**Decisiones tomadas:**
- Directorio `infrastructure/constructs/` renombrado a `infrastructure/cdk_constructs/` — `constructs` es el nombre del paquete CDK de Python y tener un directorio local con ese nombre causa namespace collision
- Helper `register_iceberg_table()` como función pura (no construct class) — más simple para 51 tablas, sin overhead de Construct lifecycle
- Tablas Iceberg registradas declarativamente con `CfnTable` (L1) — no requiere Athena runtime ni crawlers para crear el catálogo
- `partition_keys` separados del StorageDescriptor — Glue/Iceberg requiere que las partition columns NO aparezcan en la lista de columns del StorageDescriptor
- Glue Catalog `resources=["*"]` en IAM policies — los ARNs de Glue Catalog son a nivel cuenta/región, no se pueden scoper a una database sin conocer el ARN completo en deploy time

**Desvíos del plan original:**
- `infrastructure/constructs/` → `infrastructure/cdk_constructs/` por colisión de namespace con el paquete `constructs` v10.x
- Import paths en `table_definitions/*.py` cambiados de `infrastructure.table_definitions` a `table_definitions` — CDK se ejecuta desde `infrastructure/` como working directory
- Se agregaron imports de `aws_iam` y `aws_athena` al stack desde el inicio (task 5.1 los necesitaba para el full implementation)

**Gotchas para specs siguientes:**
- El bucket NO tiene datos aún — las tablas Iceberg están registradas pero vacías. Spec #3 (DMS) llenará los datos
- `metadata_location` apunta a `s3://{bucket}/{domain}/{table}/metadata/` — DMS/ETL debe escribir los snapshots Iceberg ahí
- El Athena workgroup tiene límite de 100MB scan — suficiente para validación, pero queries de producción necesitarán otro workgroup
- Los IAM roles (`GlueCrawlerRole`, `GlueEtlRole`) están listos para ser usados por DMS y Glue ETL en spec #3
- El entry point es `app_datalake.py` (no `app.py`) — deploy con `cdk deploy --app '.venv/bin/python3 app_datalake.py'`

### #3 `ingestion-dms` — cerrado

**Decisiones tomadas:**
- IngestionStack como stack CDK independiente (no dentro de DataLakeStack) — permite deploy/destroy independiente sin afectar el lake
- DMS Serverless (no classic) — sin gestión de instancias, auto-scaling 1-4 DCU
- Full-load (no CDC) — volúmenes de simulación pequeños, simplicidad operativa, idempotencia natural
- VPC dedicada para DMS (10.200.0.0/16) en lugar de VPC default — la cuenta no tiene VPC default
- VPC Peering entre DataSources VPC (10.100.0.0/16) y DMS VPC (10.200.0.0/16)
- `dms-vpc-role` importado por nombre (ya existía en la cuenta) — no se crea dentro del stack
- Compresión NONE en DMS Target (no SNAPPY) — DMS con Parquet solo soporta GZIP o NONE
- Regional service principal `dms.us-east-1.amazonaws.com` para trust policies de DMS
- PySpark script con funciones puras extraídas a `pyspark_helpers.py` — testabilidad sin dependencias de Spark
- Step Functions con polling pattern (no callbacks) — más simple, sin Lambda intermedias
- EventBridge Schedule DISABLED por defecto en dev — previene ejecuciones automáticas no deseadas

**Desvíos del plan original:**
- El diseño original asumía VPC default existente — se creó VPC dedicada para DMS (10.200.0.0/16)
- `dms-vpc-role` se importa con `from_role_name` en lugar de crearse con AwsCustomResource — el approach con custom resources era frágil y causaba race conditions
- Compresión cambiada de SNAPPY a NONE — DMS no soporta SNAPPY con formato Parquet
- Trust policy de DMS usa regional principal (`dms.us-east-1.amazonaws.com`) no global
- Se agregó `StartReplicationType: "reload-target"` al ASL de Step Functions — requerido por la API

**Gotchas para specs siguientes:**
- El pipeline está desplegado pero NO ejecutado aún — las tablas Iceberg siguen vacías hasta que se ejecute la State Machine
- Para ejecutar manualmente: `aws stepfunctions start-execution --state-machine-arn arn:aws:states:us-east-1:709578350924:stateMachine:pharmassist-ingestion-pipeline --input '{}' --profile hmancini+demos-Admin`
- El Glue ETL Job necesita que el GlueEtlRole (de DataLakeStack) tenga permisos sobre el bucket de CDK assets (para leer el script)
- DMS Serverless tarda ~5 min en provisionar la primera vez que se ejecuta
- El Athena workgroup `pharmassist-validation` tiene 100MB scan limit — suficiente para validación pero no para queries de producción
- Para spec #5 (athena-cross-source): ejecutar el pipeline primero para llenar las tablas Iceberg

### #4 `maestros-integration` — cerrado

**Decisiones tomadas:**
- Column mapping como diccionario declarativo en `pyspark_helpers.py` (no config externo) — simple, versionado con el código, fácil de testear
- Transformación `relacion` → `confianza_match` como mapeo de valores discretos (exacta=1.00, parcial=0.70, generico=0.40) — no se usa ML ni scoring continuo
- Construct CDK `MaestrosValidationQueries` dentro de `IngestionStack` (no stack separado) — comparte workgroup Athena existente
- 6 named queries como `CfnNamedQuery` (L1) — no hay L2 construct para named queries en CDK
- SQL embebido en el construct Python (no archivos externos) — simplifica deploy, evita asset management
- Columnas derivadas (nombre, apellido, especialidad, etc.) se agregan como NULL — se poblarán en un paso posterior de enriquecimiento (fuera de scope)
- Property tests y CDK assertion tests marcados como opcionales (`*`) para MVP — se pueden agregar después

**Desvíos del plan original:**
- Los tests opcionales (1.4–1.7, 3.4) se omitieron para el MVP — el checkpoint final valida con CDK synth + archivos existentes
- Se corrigieron 2 tests pre-existentes de `test_ingestion_stack.py` (CompressionType SNAPPY→NONE, trust principal regional) que estaban desactualizados desde spec #3

**Gotchas para specs siguientes:**
- El pipeline de ingesta debe ejecutarse al menos 1 vez antes de que las queries de validación SQL retornen datos útiles
- Las named queries están en el workgroup `pharmassist-validation` (100MB scan limit) — queries de producción necesitan otro workgroup
- El `COLUMN_MAPPING` en `pyspark_helpers.py` debe actualizarse si el schema RDS cambia — `detect_schema_drift()` ayuda a detectar cambios
- Los scripts SQL en `infrastructure/scripts/validation/` son para ejecución manual en Athena — no están automatizados
- Para spec #5 (athena-cross-source): las 6 named queries ya están desplegadas, las queries prototipo en `preguntas_prototipo.sql` son el punto de partida
- La documentación del mapping está en `docs/etl-column-mapping-maestros.md` — referencia para cualquier cambio futuro en el ETL
