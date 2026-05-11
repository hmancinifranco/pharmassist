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
| 2 | `data-lake-foundation` | 1 | 🔴 | #1 | S3 bucket lake + Glue Catalog + Iceberg tables base |
| 3 | `ingestion-dms` | 1 | 🔴 | #1, #2 | DMS Serverless: RDS → S3 Parquet → Glue ETL → Iceberg |
| 4 | `maestros-integration` | 1 | 🔴 | #2 | Tablas maestras de integración (producto, médicos, familia→marca CUP). Validación cross-source |
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
