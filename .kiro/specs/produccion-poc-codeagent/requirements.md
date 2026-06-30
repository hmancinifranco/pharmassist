# Requirements Document

## Introduction

Este documento define los requisitos para el POC de Producción de PharmAssist con CodeAgent. El sistema reemplaza 15+ tools con SQL hardcodeado por un `CodeAgent` con REPL persistente que genera SQL dinámicamente contra Aurora PostgreSQL Serverless v2, operando con el modelo de datos real del cliente farmacéutico (20+ tablas, 1.5M+ filas, JOINs de 5-6 niveles). El objetivo es demostrar factibilidad técnica con respuestas correctas en <6 segundos por interacción.

## Glossary

- **CodeAgent**: Agente basado en `strands-code-agent` que genera y ejecuta código Python/SQL en un REPL persistente
- **REPL**: Read-Eval-Print Loop — entorno de ejecución Python persistente entre interacciones
- **APM**: Agente de Propaganda Médica (visitador médico)
- **Aurora_DB**: Aurora PostgreSQL Serverless v2 con el modelo de datos del cliente
- **System_Prompt**: Prompt del sistema que incluye schema DDL, reglas de negocio y ejemplos SQL
- **Toolkit**: Conjunto de funciones (query_db, get_apm_id, get_ciclo_actual_id) expuestas al REPL
- **EVO_TRM**: Índice de Evolución Trimestral = ShareMarcaTrim - ShareMarcaTrim_1
- **Foco/Hiperfoco**: Categorías de promoción de productos (FC=Foco, HP=Hiperfoco) en un ciclo
- **Ciclo**: Período promocional temporal con grilla de productos asignados
- **UltimaMillaMarca**: Tabla analítica con 1.5M filas de prescripciones por médico y marca
- **Cartera_Medica**: Relación activa entre un APM y sus médicos asignados
- **CUP**: Sistema externo de datos de prescripción de mercado (IQVIA)
- **CDK_Stack**: Stack de AWS CDK que provisiona Aurora, VPC, Secrets Manager y Lambda de seed
- **SeedDataGenerator**: Lambda que genera y carga datos mocked con distribuciones realistas
- **Smoke_Test**: Suite de validación end-to-end con 14 preguntas tipo


## Requirements

### Requirement 1: CodeAgent con REPL Persistente

**User Story:** As an APM, I want to ask complex questions about prescriptions and promotions in natural language, so that I get accurate answers without needing pre-built tools for each question type.

#### Acceptance Criteria

1. WHEN an APM sends a natural language question, THE CodeAgent SHALL generate Python code with SQL queries and execute it in the REPL to produce a data-driven answer
2. WHEN a REPL session is initialized for an APM, THE Toolkit SHALL inject `APM_ID` (string) and `CICLO_ACTUAL` (integer) as global variables before any query executes
3. THE Toolkit SHALL expose exactly three functions to the REPL: `query_db(sql)`, `get_apm_id()`, and `get_ciclo_actual_id()`
4. WHEN `query_db` receives a SQL string, THE Toolkit SHALL validate that it starts with SELECT or WITH (CTE) and reject any other statement type
5. WHEN `query_db` receives a valid SELECT query, THE Toolkit SHALL execute it against Aurora_DB and return a pandas DataFrame
6. WHEN the LLM generates invalid SQL that causes a PostgreSQL error, THE CodeAgent SHALL retry up to 2 times with auto-corrected SQL before returning a fallback message to the user
7. THE CodeAgent SHALL use Amazon Bedrock Claude Sonnet 4 as the underlying LLM for code generation and response formatting


### Requirement 2: System Prompt con Schema y Reglas de Negocio

**User Story:** As a developer, I want the CodeAgent to have complete knowledge of the database schema and pharmaceutical business rules, so that it generates correct SQL without hallucinating table or column names.

#### Acceptance Criteria

1. THE System_Prompt SHALL include the complete DDL of all tables (names, columns, types, foreign keys, indices)
2. THE System_Prompt SHALL document the EVO_TRM calculation rule: `EVO_TRM = ShareMarcaTrim - ShareMarcaTrim_1`
3. THE System_Prompt SHALL document the Foco/Hiperfoco identification rule: products with `id_categoria_promocion IN ('1', '2')` in `detalle_promocion_producto` for the current cycle
4. THE System_Prompt SHALL document the APX-to-CUP cross-reference path: `familia_producto.id` → `familia_APX_a_Marca_CUP.id_familia_producto_apx` → `codMarcaCUP` → `UltimaMillaMarca.idMarca`
5. THE System_Prompt SHALL include at least 5 SQL query examples as few-shot patterns for common question types
6. THE System_Prompt SHALL instruct the CodeAgent to respond in Argentine Spanish with concrete data (not generic responses)
7. THE System_Prompt SHALL inform the CodeAgent that `APM_ID` and `CICLO_ACTUAL` are pre-loaded variables in the REPL


### Requirement 3: Aurora PostgreSQL Serverless v2 con Modelo de Datos Completo

**User Story:** As a developer, I want a fully provisioned Aurora PostgreSQL database with the complete client data model, so that the CodeAgent can execute complex JOINs against realistic data volumes.

#### Acceptance Criteria

1. THE Aurora_DB SHALL contain at least 20 tables matching the client's relational model including: apm, doctor, cartera_medica, agenda, agenda_producto, familia_producto, detalle_promocion_producto, UltimaMillaMedico, UltimaMillaMarca, UltimaMillaObjetivoMarcaMercado, familia_APX_a_Marca_CUP, linea, linea_apm, ciclo, grilla, categoria_promocion, especialidad, loyalty_doctor, institucion, datos_visita, producto
2. THE Aurora_DB SHALL enforce foreign key constraints between all related tables
3. THE Aurora_DB SHALL be configured as Serverless v2 with minimum 0.5 ACU and maximum 4 ACU
4. THE Aurora_DB SHALL include performance indices on: `cartera_medica(apm_id)`, `agenda(apm_id, inicio)`, `UltimaMillaMarca(idMedicoCUP, idMarca)`, `UltimaMillaMarca(idLaboratorio)`, `detalle_promocion_producto(id_ciclo, id_categoria_promocion)`, `linea_apm(id_apm)`, `agenda_producto(id_agenda)`, `UltimaMillaMedico(idMedicoAPX)`
5. THE Aurora_DB SHALL use partial indices with `WHERE inactivo = false` on cartera_medica and agenda tables
6. WHEN a query is executed, THE Aurora_DB SHALL enforce a statement_timeout of 5000ms


### Requirement 4: Seed Data con Volúmenes y Distribuciones Realistas

**User Story:** As a developer, I want realistic mock data loaded into Aurora, so that the CodeAgent can be validated against data volumes and distributions similar to production.

#### Acceptance Criteria

1. THE SeedDataGenerator SHALL produce at least 1,500,000 rows in the UltimaMillaMarca table (30,000 doctors × ~50 brands per doctor)
2. THE SeedDataGenerator SHALL produce data with valid foreign key references across all tables (no orphan references)
3. THE SeedDataGenerator SHALL generate ShareMarcaMercado values following a Pareto distribution (few brands dominate, most have low share)
4. THE SeedDataGenerator SHALL assign approximately 30% of UltimaMillaMarca rows with `idLaboratorio = 'ELE'` (own products)
5. THE SeedDataGenerator SHALL generate IEMarcaTrim values following a normal distribution centered at 0 with standard deviation ~0.1
6. THE SeedDataGenerator SHALL produce the following minimum volumes: 200 APMs, 30,000 doctors, 25,000 cartera_medica records, 150,000 agenda entries, 300,000 agenda_producto records
7. THE SeedDataGenerator SHALL load tables in dependency order (parents before children) to maintain referential integrity
8. THE SeedDataGenerator SHALL create performance indices after bulk data loading completes
9. WHEN seed data generation completes, THE SeedDataGenerator SHALL create a read-only PostgreSQL user for the CodeAgent with SELECT-only permissions


### Requirement 5: CDK Infrastructure Stack

**User Story:** As a developer, I want a single CDK stack that provisions all required AWS infrastructure, so that the POC can be deployed and torn down reproducibly.

#### Acceptance Criteria

1. THE CDK_Stack SHALL create a VPC with private subnets in at least 2 Availability Zones and one NAT Gateway
2. THE CDK_Stack SHALL create an Aurora PostgreSQL Serverless v2 cluster in the private subnets with database name `pharmassist_poc`
3. THE CDK_Stack SHALL create a secret in Secrets Manager with auto-generated credentials for the Aurora cluster
4. THE CDK_Stack SHALL create Security Groups that allow Lambda access to Aurora on port 5432
5. THE CDK_Stack SHALL create a Lambda function for seed data generation with 15-minute timeout, 3008 MB memory, VPC access, and the DB secret ARN as environment variable
6. THE CDK_Stack SHALL export CloudFormation outputs: AuroraEndpoint, AuroraSecretArn, VpcId, SeedLambdaArn
7. THE CDK_Stack SHALL set RemovalPolicy.DESTROY on all resources for easy teardown of the POC
8. THE CDK_Stack SHALL apply consistent tags (Project, Environment, Owner) to all resources via CDK Aspects


### Requirement 6: End-to-End Validation

**User Story:** As a product owner, I want automated validation of 14 representative questions answered correctly in under 6 seconds each, so that we can prove the POC meets accuracy and performance targets.

#### Acceptance Criteria

1. THE Smoke_Test SHALL execute all 14 predefined questions against the deployed CodeAgent
2. WHEN a question is executed, THE Smoke_Test SHALL measure total latency from invocation to response completion
3. WHEN the Smoke_Test completes, THE Smoke_Test SHALL report: number passed, number failed, average latency, and per-question details (question, response, latency_ms, SQL generated, success boolean)
4. THE Smoke_Test SHALL consider the POC successful when at least 12 of 14 questions are answered correctly (≥85% accuracy)
5. THE Smoke_Test SHALL consider the POC successful when average latency is below 6000ms
6. THE Smoke_Test SHALL consider the POC successful when no single question exceeds 10000ms latency
7. WHEN evaluating correctness, THE Smoke_Test SHALL verify that responses contain concrete numerical data (not generic or error messages)
8. THE Smoke_Test SHALL cover three question categories: prescriptions/foco products (6 questions), promotion analysis (4 questions), and visit management (4 questions)


### Requirement 7: Security — Read-Only SQL and Network Isolation

**User Story:** As a security architect, I want the CodeAgent to operate with minimum privileges and network isolation, so that LLM-generated code cannot modify data or access unauthorized resources.

#### Acceptance Criteria

1. THE Toolkit SHALL reject any SQL statement that does not start with SELECT or WITH (blocking INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE)
2. THE Aurora_DB SHALL have a dedicated read-only PostgreSQL user with only SELECT permissions on all tables used by the CodeAgent
3. THE Aurora_DB SHALL be deployed in a private VPC subnet with no direct internet access
4. THE Aurora_DB credentials SHALL be stored exclusively in AWS Secrets Manager (never in code or environment variables as plaintext)
5. WHEN the CodeAgent connects to Aurora_DB, THE Toolkit SHALL use SSL/TLS encryption for the database connection
6. THE CDK_Stack SHALL configure Security Groups to allow inbound PostgreSQL traffic (port 5432) only from the Lambda/AgentCore security group

### Requirement 8: Performance — Sub-6-Second Latency

**User Story:** As an APM, I want responses to my questions in less than 6 seconds, so that the conversation feels natural and I can work efficiently.

#### Acceptance Criteria

1. WHEN the CodeAgent processes a question, THE CodeAgent SHALL complete the full cycle (LLM reasoning + SQL execution + response generation) in less than 6000ms
2. THE Aurora_DB SHALL maintain minimum 0.5 ACU capacity to avoid cold start delays
3. THE Toolkit SHALL configure a SQLAlchemy connection pool with pool_size=5 and max_overflow=2 to reuse database connections
4. THE Toolkit SHALL set a 5000ms statement_timeout on every database query to prevent runaway queries from exceeding the latency budget
5. WHEN the CodeAgent generates SQL, THE System_Prompt SHALL instruct it to always filter by `apm_id` early in the query to reduce the scan scope from 30,000 doctors to ~125 (the APM's active portfolio)
