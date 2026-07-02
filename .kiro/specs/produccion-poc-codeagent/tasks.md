# Implementation Plan: POC Producción — CodeAgent con Aurora PostgreSQL

## Overview

Implementar el POC completo de PharmAssist con CodeAgent usando `strands-code-agent`, Aurora PostgreSQL Serverless v2, y 1.5M+ filas de seed data. El plan sigue el orden: infraestructura CDK → seed data → CodeAgent + system prompt → validación E2E → deploy.

Lenguaje de implementación: **Python** (CDK, Lambda, Agent, Tests).

## Tasks

- [x] 1. CDK Stack — Skeleton + Entry Point
  - [x] 1.1 Crear skeleton del stack `ProduccionPocStack` con VPC, Aurora, Secrets Manager, Security Groups
    - Crear `produccion-poc/infrastructure/stacks/produccion_poc_stack.py`
    - Definir VPC con private subnets (2 AZs) + NAT Gateway
    - Crear Aurora PostgreSQL Serverless v2 cluster (0.5–4 ACU, versión 15.4)
    - Crear secret auto-generado en Secrets Manager
    - Crear Security Groups (Lambda → Aurora puerto 5432)
    - Database name: `pharmassist_poc`
    - RemovalPolicy.DESTROY en todos los recursos
    - Tags via CDK Aspects (Project, Environment, Owner)
    - CfnOutputs: AuroraEndpoint, AuroraSecretArn, VpcId
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.7, 5.8, 5.6_

  - [x] 1.2 Crear CDK entry point `produccion-poc/infrastructure/app.py`
    - Instanciar `ProduccionPocStack` con env (account + region desde .env)
    - Configurar `cdk.json` con app command
    - _Requirements: 5.6_

  - [x] 1.3 Agregar Lambda de seed data al stack
    - Runtime Python 3.12, timeout 15 min, memory 3008 MB
    - VPC access con el Security Group creado
    - Environment: DB_SECRET_ARN, DB_NAME
    - Dar permisos: secretsmanager:GetSecretValue sobre el secret de Aurora
    - CfnOutput: SeedLambdaArn
    - _Requirements: 5.5, 5.6_

- [x] 2. Checkpoint — cdk synth
  - Ejecutar `cdk synth` y verificar que genera template CloudFormation sin errores
  - Validar que los outputs esperados están presentes en el template
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Seed Data Generator — DDL y Generadores
  - [x] 3.1 Crear DDL completo (tablas + índices)
    - Crear `produccion-poc/infrastructure/lambda/seed/ddl.sql` con CREATE TABLE de todas las 21+ tablas
    - Incluir FKs, tipos VARCHAR/DECIMAL/BOOLEAN/TIMESTAMP según el design
    - Incluir tablas con comillas para nombres mixtos: `"UltimaMillaMedico"`, `"UltimaMillaMarca"`, `"UltimaMillaObjetivoMarcaMercado"`
    - Incluir tabla `familia_APX_a_Marca_CUP`
    - Incluir creación de índices de performance (8 índices según design)
    - Incluir creación del usuario read-only `codeagent_readonly`
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 4.8, 4.9, 7.2_

  - [x] 3.2 Crear generadores de tablas padre (catálogos)
    - Crear `produccion-poc/infrastructure/lambda/seed/generators/catalogos.py`
    - Generar: especialidad (50), loyalty_doctor (5), institucion (500), linea (5), ciclo (12), categoria_promocion (2), grilla (10), familia_producto (40), producto (150)
    - Volúmenes según spec de design
    - _Requirements: 4.6, 4.7_

  - [x] 3.3 Crear generadores de tablas dependientes (APMs, Doctors, Cartera)
    - Crear `produccion-poc/infrastructure/lambda/seed/generators/entities.py`
    - Generar: apm (200), doctor (30,000), linea_apm (300), datos_visita (25,000), cartera_medica (25,000)
    - FKs válidas apuntando a tablas padre ya generadas
    - _Requirements: 4.2, 4.6, 4.7_

  - [x] 3.4 Crear generador de agenda y agenda_producto
    - Crear `produccion-poc/infrastructure/lambda/seed/generators/agenda.py`
    - Generar: agenda (150,000), agenda_producto (300,000)
    - Fechas distribuidas en los últimos 12 meses
    - tipos de visita: Presencial/Virtual/Telefónica
    - ~2 productos por visita en agenda_producto
    - _Requirements: 4.6, 4.7_

  - [x] 3.5 Crear generador de UltimaMillaMarca (1.5M filas)
    - Crear `produccion-poc/infrastructure/lambda/seed/generators/ultima_milla.py`
    - Generar UltimaMillaMedico (30,000 filas — 1 por doctor)
    - Generar UltimaMillaMarca (~1,500,000 filas — 30K doctors × ~50 marcas)
    - ShareMarcaMercado con distribución Pareto (>80% debajo de 0.15, <5% arriba de 0.40)
    - IEMarcaTrim con distribución normal (μ=0, σ≈0.1)
    - ~30% de filas con idLaboratorio = 'ELE'
    - Generar UltimaMillaObjetivoMarcaMercado (500 filas)
    - Generar familia_APX_a_Marca_CUP (60 filas) con codMarcaCUP válidos
    - Generar detalle_promocion_producto (100 filas)
    - _Requirements: 4.1, 4.3, 4.4, 4.5_

  - [x] 3.6 Crear Lambda handler para seed data
    - Crear `produccion-poc/infrastructure/lambda/seed/seed_handler.py`
    - Obtener credenciales de Secrets Manager
    - Ejecutar DDL (crear tablas)
    - Ejecutar generadores en orden de dependencia (padres → hijos)
    - Bulk insert con COPY o batch INSERT para performance
    - Crear índices post-carga
    - Crear usuario read-only
    - Retornar conteos por tabla
    - _Requirements: 4.7, 4.8, 4.9_

  - [ ]* 3.7 Write property tests para seed data generators
    - **Property 3: Seed Data Referential Integrity** — ∀ fila en child table, FK existe en parent table
    - **Property 4: ShareMarcaMercado Follows Pareto Distribution** — >80% < 0.15, <5% > 0.40
    - **Property 5: ELE Laboratory Proportion** — entre 0.25 y 0.35
    - **Property 6: IEMarcaTrim Normal Distribution** — μ ∈ [-0.02, 0.02], σ ∈ [0.08, 0.12]
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**

- [x] 4. Checkpoint — Seed Data
  - Verificar que los generadores pueden crear DataFrames con los volúmenes esperados (test local sin BD)
  - Verificar integridad referencial en los DataFrames generados
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. CodeAgent — Toolkit y System Prompt
  - [x] 5.1 Crear PharmaToolkit con query_db, get_apm_id, get_ciclo_actual_id
    - Crear `produccion-poc/agent/toolkit.py`
    - `query_db(sql)`: valida SELECT/WITH, ejecuta con statement_timeout=5000ms, retorna DataFrame
    - `get_apm_id()`: retorna APM_ID de la sesión
    - `get_ciclo_actual_id()`: query para obtener ciclo vigente
    - Conexión via SQLAlchemy Engine con pool_size=5, max_overflow=2, pool_pre_ping=True
    - Credenciales de Secrets Manager (boto3)
    - SSL/TLS obligatorio en la conexión PostgreSQL
    - _Requirements: 1.3, 1.4, 1.5, 7.1, 7.5, 8.3, 8.4_

  - [ ]* 5.2 Write property test para SQL validation
    - **Property 1: SQL Validation Rejects Non-Read Queries** — cualquier SQL que no empieza con SELECT/WITH es rechazado
    - **Property 7: Statement Timeout Enforcement** — statement_timeout=5000 se setea antes de cada query
    - **Validates: Requirements 1.4, 7.1, 8.4, 3.6**

  - [x] 5.3 Crear SystemPromptBuilder
    - Crear `produccion-poc/agent/system_prompt.py`
    - Sección 1: Identidad (sos un asistente para APMs de farmacéutica argentina)
    - Sección 2: Schema DDL completo (todas las 21+ tablas con columnas, tipos, FKs)
    - Sección 3: Reglas de negocio (EVO TRM, Foco/Hiperfoco, ciclos, cruce APX→CUP)
    - Sección 4: Ejemplos de queries SQL (≥5 patrones few-shot)
    - Sección 5: Instrucciones (español argentino, datos concretos, APM_ID/CICLO_ACTUAL disponibles)
    - Total estimado: 8,000-12,000 tokens
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 5.4 Write property test para System Prompt completeness
    - **Property 2: System Prompt Contains All Schema Tables** — ∀ tabla en el schema, su nombre aparece en el prompt
    - **Validates: Requirement 2.1**

  - [x] 5.5 Crear entry point del agente con CodeAgent
    - Crear `produccion-poc/agent/agent.py`
    - Instanciar BedrockModel (Claude Sonnet 4, us-east-1)
    - Instanciar Toolkit con authorized_imports=[pandas, numpy]
    - init_code que carga APM_ID y CICLO_ACTUAL
    - Crear CodeAgent con model + system_prompt + toolkit
    - Función `invoke(message, apm_id)` que procesa la pregunta
    - Manejar retry (hasta 2 reintentos si el LLM genera SQL inválido)
    - Wrapping con BedrockAgentCoreApp para deploy (o standalone)
    - _Requirements: 1.1, 1.2, 1.6, 1.7_

  - [x] 5.6 Crear archivos de prompts estáticos
    - Crear `produccion-poc/agent/prompts/schema.md` — DDL documentado con comentarios
    - Crear `produccion-poc/agent/prompts/business_rules.md` — reglas EVO TRM, Foco, ciclos, CUP
    - Crear `produccion-poc/agent/prompts/query_examples.md` — ≥5 ejemplos SQL para preguntas frecuentes
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 6. Checkpoint — Agent Local
  - Verificar que el CodeAgent se instancia correctamente sin errores de import
  - Verificar que SystemPromptBuilder genera un prompt con las 5 secciones
  - Verificar que el prompt contiene las 21+ tablas del schema
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Deploy a AWS
  - [x] 7.1 CDK deploy del stack completo
    - Ejecutar `cdk deploy ProduccionPocStack --profile $AWS_PROFILE --require-approval never`
    - Verificar que Aurora cluster está en estado `available`
    - Verificar que Lambda de seed está creada
    - Guardar outputs (AuroraEndpoint, AuroraSecretArn, VpcId, SeedLambdaArn) en .env
    - Si falla: diagnosticar, corregir, y re-intentar
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [x] 7.2 Invocar Lambda de seed data
    - Ejecutar Lambda de seed via AWS CLI (`aws lambda invoke`)
    - Esperar hasta 15 minutos (timeout de la Lambda)
    - Verificar que retorna conteos correctos (UltimaMillaMarca ≈ 1.5M)
    - Si falla por timeout: verificar logs en CloudWatch, ajustar batch sizes
    - _Requirements: 4.1, 4.6, 4.7, 4.8, 4.9_

  - [x] 7.3 Validación post-seed
    - Conectar a Aurora y ejecutar queries de validación:
      - `SELECT COUNT(*) FROM "UltimaMillaMarca"` → ≈ 1,500,000
      - `SELECT COUNT(*) FROM cartera_medica WHERE inactivo = false` → ≈ 25,000
      - `SELECT COUNT(*) FROM agenda` → ≈ 150,000
    - Verificar que el usuario read-only existe y puede hacer SELECT
    - Verificar que los índices están creados
    - _Requirements: 3.1, 3.4, 3.5, 7.2_

  - [x] 7.4 Deploy del CodeAgent
    - Opción A: `agentcore deploy` con env vars (DB_SECRET_ARN, etc.)
    - Opción B: Lambda + API Gateway como proxy (si strands-code-agent no es compatible con AgentCore)
    - Verificar que el agente responde a una pregunta simple: "¿Cuántos médicos tengo en mi cartera?"
    - Si falla: diagnosticar compatibilidad, ajustar approach
    - _Requirements: 1.1, 1.7_

- [x] 8. End-to-End Validation
  - [x] 8.1 Crear script de smoke test
    - Crear `produccion-poc/tests/e2e/run_smoke_test.py`
    - Lista de 14 preguntas del spec (3 categorías)
    - Invocar al agente con cada pregunta + apm_id de test
    - Medir latencia total por pregunta
    - Evaluar correctitud: respuesta tiene datos concretos, no errores, >50 chars
    - Generar reporte: passed/failed, latencia promedio, SQL generado
    - _Requirements: 6.1, 6.2, 6.3, 6.7, 6.8_

  - [x] 8.2 Ejecutar smoke test y validar resultados
    - Ejecutar `run_smoke_test.py` contra el agente desplegado
    - Verificar: ≥12/14 correctas (≥85%)
    - Verificar: latencia promedio < 6000ms
    - Verificar: ninguna pregunta > 10000ms
    - Si accuracy < 85%: ajustar system prompt (query examples, reglas) y re-testear
    - Generar reporte final con resultados
    - _Requirements: 6.4, 6.5, 6.6, 8.1_

- [x] 9. Final checkpoint
  - Verificar que el POC está desplegado y funcionando end-to-end
  - Verificar que el reporte muestra ≥85% accuracy y <6s latencia promedio
  - Actualizar .env y .env.example con outputs del deploy
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- CDK entry point (1.2) goes immediately after stack skeleton (per spec-methodology rules)
- `cdk synth` checkpoint (2) validates infrastructure before deploy
- Deploy (7) is MANDATORY before closing the spec (per deployment rules)
- If `strands-code-agent` is incompatible with AgentCore, fallback to Lambda + API Gateway proxy
- All code uses Python 3.12+ with type hints
- The seed Lambda uses bulk operations (COPY preferred, batch INSERT fallback) for 1.5M rows

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3"] },
    { "id": 4, "tasks": ["3.4", "3.5"] },
    { "id": 5, "tasks": ["3.6", "3.7"] },
    { "id": 6, "tasks": ["5.1", "5.3", "5.6"] },
    { "id": 7, "tasks": ["5.2", "5.4", "5.5"] },
    { "id": 8, "tasks": ["7.1"] },
    { "id": 9, "tasks": ["7.2"] },
    { "id": 10, "tasks": ["7.3"] },
    { "id": 11, "tasks": ["7.4"] },
    { "id": 12, "tasks": ["8.1"] },
    { "id": 13, "tasks": ["8.2"] }
  ]
}
```
