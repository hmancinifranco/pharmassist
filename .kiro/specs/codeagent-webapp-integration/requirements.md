# Requirements Document

## Introduction

Este documento define los requerimientos para integrar el CodeAgent validado en POC (Aurora PostgreSQL, 21 tablas, 2M filas) en la webapp PharmAssist como un único runtime de AgentCore. La integración reemplaza 7 tools de consulta basados en CSV/DynamoDB por un solo `query_db` contra Aurora, implementa features de plataforma AgentCore (Memory, Observability, Identity, Evaluations), y mejora la UX del frontend con respuestas estructuradas (tablas, gráficos, SQL toggle, suggestion chips).

## Glossary

- **Unified_Agent**: Runtime único de AgentCore que ejecuta 5 tools (query_db, buscar_info_publica, generar_brief, obtener_minutas, generar_mensaje_cumpleanos)
- **APM**: Agente de Propaganda Médica — usuario principal del sistema
- **query_db**: Tool principal que ejecuta SQL read-only contra Aurora PostgreSQL
- **STM**: Short-Term Memory — memoria de eventos por sesión
- **Semantic_Memory**: Memoria de largo plazo cross-session con búsqueda semántica
- **AgentCore_Memory**: Servicio de AgentCore que gestiona STM y Semantic Memory
- **AgentCore_Identity**: Servicio de autenticación que valida JWT de Cognito
- **ResponseFormatter**: Componente que transforma respuestas del agente en formato estructurado
- **Lambda_Proxy**: Lambda existente que valida JWT y routea al AgentCore runtime
- **StructuredResponse**: Componente frontend que renderiza tablas, gráficos, SQL y chips
- **BidiAgent**: Agente de voz bidireccional que delega al Unified Agent
- **DataGrid**: Componente MUI X para renderizar tablas con sort/filter/paginación
- **ChartRenderer**: Componente MUI X Charts para gráficos de tendencia
- **Evaluation_Suite**: Suite automatizada de 30+ preguntas para validar calidad del agente


## Requirements

### Requirement 1: Agent Tool Routing and Invocation

**User Story:** As an APM, I want to ask questions in natural language and have the agent select the correct tool automatically, so that I get accurate answers from the right data source without worrying about technical details.

#### Acceptance Criteria

1. WHEN an APM sends a data query (prescripciones, cartera, visitas, ventas), THE Unified_Agent SHALL invoke query_db with a valid SQL SELECT statement
2. WHEN an APM asks for public information about a doctor, THE Unified_Agent SHALL invoke buscar_info_publica with the doctor's name and specialty
3. WHEN an APM requests a pre-visit brief, THE Unified_Agent SHALL invoke generar_brief combining Aurora data, web search, and DynamoDB minutas
4. WHEN an APM asks about previous visit notes, THE Unified_Agent SHALL invoke obtener_minutas with the doctor's ID
5. WHEN an APM requests a birthday message, THE Unified_Agent SHALL invoke generar_mensaje_cumpleanos with the doctor's ID

### Requirement 2: SQL Execution Safety and Validation

**User Story:** As a system administrator, I want the agent to only execute read-only SQL queries with timeouts, so that the production database remains safe from mutations and runaway queries.

#### Acceptance Criteria

1. WHEN query_db receives a SQL string, THE Unified_Agent SHALL validate that it starts with SELECT or WITH (case-insensitive, trimmed)
2. IF query_db receives SQL that does not start with SELECT or WITH, THEN THE Unified_Agent SHALL reject it with a descriptive ValueError
3. THE query_db tool SHALL execute every query with statement_timeout set to 5000 milliseconds
4. IF a query exceeds the 5-second timeout, THEN THE Unified_Agent SHALL raise a TimeoutError and inform the user the query is too complex
5. THE query_db tool SHALL use a read-only database user that cannot execute INSERT, UPDATE, DELETE, or DDL statements
6. WHEN query_db completes successfully, THE Unified_Agent SHALL return the DataFrame results with a maximum of 50 rows in text format and 100 rows in structured metadata


### Requirement 3: Retry Logic for Failed SQL

**User Story:** As an APM, I want the agent to self-correct when it generates invalid SQL, so that I get answers without needing to rephrase my question.

#### Acceptance Criteria

1. WHEN query_db returns a database error (syntax error, invalid column), THE Unified_Agent SHALL retry with a corrected SQL statement including the error message in context
2. THE Unified_Agent SHALL attempt a maximum of 2 retries after the initial failed attempt
3. IF all retry attempts fail, THEN THE Unified_Agent SHALL return a user-friendly error message in Spanish explaining the query could not be completed
4. WHEN a retry succeeds, THE Unified_Agent SHALL include the retry count in the response metadata

### Requirement 4: Connection Pooling and Database Connectivity

**User Story:** As a system operator, I want the agent to manage database connections efficiently, so that concurrent APM requests are handled without exhausting connection limits.

#### Acceptance Criteria

1. THE Unified_Agent SHALL use SQLAlchemy QueuePool with pool_size of 5 and max_overflow of 2
2. THE Unified_Agent SHALL configure pool_pre_ping to detect and discard stale connections
3. THE Unified_Agent SHALL use SSL/TLS for all connections to Aurora PostgreSQL with the RDS CA bundle
4. THE Unified_Agent SHALL retrieve database credentials from AWS Secrets Manager using the DB_SECRET_ARN environment variable
5. WHEN a database connection fails, THE Unified_Agent SHALL return a user-friendly error in Spanish without exposing internal connection details

### Requirement 5: Short-Term Memory (STM) per Session

**User Story:** As an APM, I want the agent to remember what I said earlier in the same conversation, so that I can ask follow-up questions without repeating context.

#### Acceptance Criteria

1. WHEN the Unified_Agent completes a conversation turn, THE AgentCore_Memory SHALL store the user prompt and assistant response as an event
2. THE AgentCore_Memory SHALL associate each event with actor_id formatted as "apm-{apm_id}" and the current session_id
3. WHEN processing a new message, THE Unified_Agent SHALL retrieve the current session's event history for context
4. IF the AgentCore_Memory service is unavailable, THEN THE Unified_Agent SHALL proceed without session history and not fail the request


### Requirement 6: Semantic Memory (Cross-Session)

**User Story:** As an APM, I want the agent to recall relevant information from my past conversations, so that it provides increasingly personalized responses over time.

#### Acceptance Criteria

1. WHEN processing a new query, THE Unified_Agent SHALL perform a semantic search over the APM's cross-session memory records
2. THE Semantic_Memory retrieval SHALL return the top 3 most relevant records ordered by semantic similarity
3. THE Unified_Agent SHALL include retrieved memory context in the augmented prompt sent to the LLM
4. IF the Semantic_Memory retrieval fails or returns no results, THEN THE Unified_Agent SHALL proceed without cross-session context
5. THE AgentCore_Memory SHALL use the APM's actor_id as namespace for memory record storage and retrieval

### Requirement 7: Observability — Traces and Metrics

**User Story:** As a system operator, I want every agent request to generate traces and latency metrics, so that I can monitor performance and diagnose issues in production.

#### Acceptance Criteria

1. THE Unified_Agent SHALL emit a trace for each request including tool invocations, LLM calls, and memory operations
2. THE Unified_Agent SHALL record end-to-end latency as a CloudWatch metric for each invocation
3. THE Unified_Agent SHALL log tool execution time individually (query_db duration, memory retrieval duration, LLM inference duration)
4. WHEN an error occurs, THE Unified_Agent SHALL include the error type and message in the trace span
5. THE AgentCore Observability dashboard SHALL display request volume, latency percentiles (p50, p95, p99), and error rates

### Requirement 8: Identity — JWT Validation and Data Isolation

**User Story:** As a system administrator, I want each APM to only access their own data, so that patient and commercial information remains confidential between APM territories.

#### Acceptance Criteria

1. WHEN a WebSocket message arrives, THE Lambda_Proxy SHALL validate the Cognito JWT token via AgentCore_Identity
2. THE Lambda_Proxy SHALL extract the custom:apm_id claim from the validated JWT
3. THE Lambda_Proxy SHALL pass apm_id and session_id in the agent invocation payload
4. THE Unified_Agent SHALL inject APM_ID into the system prompt to scope all SQL queries to the APM's cartera
5. IF the JWT is invalid or expired, THEN THE Lambda_Proxy SHALL return a 401 error via WebSocket and the frontend SHALL redirect to login
6. THE Unified_Agent SHALL ensure all queries against cartera_medica filter by id_apm matching the authenticated APM


### Requirement 9: Evaluation Suite

**User Story:** As a product owner, I want an automated evaluation suite that validates agent quality across 30+ questions, so that regressions are caught before deployment.

#### Acceptance Criteria

1. THE Evaluation_Suite SHALL contain at least 30 questions covering cartera, prescripciones, visitas, ventas, briefs, and cross-domain queries
2. THE Evaluation_Suite SHALL measure accuracy with a target of at least 85% of questions producing correct, relevant answers
3. THE Evaluation_Suite SHALL measure end-to-end latency with a target of less than 6 seconds per question
4. WHEN evaluating a response, THE Evaluation_Suite SHALL verify that success equals true, the response contains the expected data type, and no data isolation violation occurred
5. THE Evaluation_Suite SHALL verify that every generated SQL query is syntactically valid and executes without runtime errors

### Requirement 10: Frontend — Structured Table Rendering

**User Story:** As an APM, I want to see query results as interactive tables with sorting and filtering, so that I can explore the data without asking follow-up questions.

#### Acceptance Criteria

1. WHEN the agent response includes structured.table with more than 2 rows, THE StructuredResponse component SHALL render a MUI DataGrid
2. THE DataGrid SHALL display columns with headers derived from the query result column names
3. THE DataGrid SHALL support sorting by clicking column headers
4. THE DataGrid SHALL support pagination with page sizes of 10 and 25 rows
5. THE DataGrid SHALL use compact density to maximize data visibility in the chat panel

### Requirement 11: Frontend — Chart Rendering

**User Story:** As an APM, I want to see temporal trends as line or bar charts, so that I can quickly understand evolution patterns (prescriptions, shares, sales over time).

#### Acceptance Criteria

1. WHEN the agent response includes structured.chart with type "line", THE StructuredResponse component SHALL render a MUI X LineChart
2. WHEN the agent response includes structured.chart with type "bar", THE StructuredResponse component SHALL render a MUI X BarChart
3. THE chart SHALL display the x-axis label and series labels from the structured data
4. THE chart SHALL render with a height of 250 pixels within the chat message container


### Requirement 12: Frontend — SQL Toggle

**User Story:** As an APM with technical curiosity, I want to optionally see the SQL query the agent generated, so that I can understand and verify the data source.

#### Acceptance Criteria

1. WHEN the agent response includes structured.sql, THE StructuredResponse component SHALL display a "Ver SQL" toggle button
2. WHEN the APM clicks the toggle, THE StructuredResponse component SHALL expand a collapsible section showing the SQL in monospace font
3. THE SQL display SHALL use a subtle background color and small font size to avoid dominating the chat

### Requirement 13: Frontend — Suggestion Chips

**User Story:** As an APM, I want to see contextual follow-up suggestions after each response, so that I can explore related topics with a single click.

#### Acceptance Criteria

1. WHEN the agent response includes structured.suggestions, THE StructuredResponse component SHALL render them as MUI Chip components
2. THE suggestion chips SHALL be displayed in a horizontal row with wrapping
3. WHEN an APM clicks a suggestion chip, THE StructuredResponse component SHALL send the chip text as a new message to the agent
4. THE Unified_Agent SHALL generate 2 to 3 contextual follow-up suggestions based on the current response

### Requirement 14: Frontend — Streaming Response

**User Story:** As an APM, I want to see the agent's response appear progressively, so that I know the system is working and don't wait for the full response.

#### Acceptance Criteria

1. WHEN the agent begins responding, THE Lambda_Proxy SHALL stream text chunks via WebSocket with type "chunk"
2. WHEN the agent invokes a tool, THE Lambda_Proxy SHALL send a message with type "tool_step" including the tool name and user-friendly label
3. WHEN the agent completes the response, THE Lambda_Proxy SHALL send a message with type "complete" including the full AgentResponsePayload
4. IF an error occurs during processing, THEN THE Lambda_Proxy SHALL send a message with type "error" with a user-friendly message in Spanish

### Requirement 15: Performance — End-to-End Latency

**User Story:** As an APM, I want responses within 6 seconds, so that the assistant feels responsive and doesn't interrupt my workflow.

#### Acceptance Criteria

1. THE Unified_Agent SHALL complete end-to-end request processing in less than 6000 milliseconds for 95% of requests
2. THE query_db tool SHALL complete SQL execution in less than 1000 milliseconds for indexed queries
3. THE Semantic_Memory retrieval SHALL complete in less than 200 milliseconds
4. THE JWT validation SHALL complete in less than 50 milliseconds


### Requirement 16: Security — SQL Injection Mitigation

**User Story:** As a security engineer, I want the system to prevent any database mutation even if the LLM generates malicious SQL, so that the production database integrity is guaranteed.

#### Acceptance Criteria

1. THE query_db tool SHALL reject any SQL statement that does not begin with SELECT or WITH after trimming and uppercasing
2. THE database user configured for query_db SHALL have only SELECT permissions (no INSERT, UPDATE, DELETE, CREATE, DROP, ALTER)
3. THE query_db tool SHALL execute queries with statement_timeout to prevent resource exhaustion attacks
4. THE Unified_Agent SHALL never expose raw database error messages to the end user

### Requirement 17: Security — Secrets and VPC Isolation

**User Story:** As a security engineer, I want all sensitive credentials managed via Secrets Manager and the agent running in VPC, so that there is no exposed attack surface.

#### Acceptance Criteria

1. THE Unified_Agent SHALL retrieve database credentials exclusively from AWS Secrets Manager
2. THE AgentCore runtime SHALL run in VPC mode with a private subnet ENI
3. THE Aurora PostgreSQL cluster SHALL only accept connections from the AgentCore security group on port 5432
4. THE Unified_Agent SHALL access Bedrock, DynamoDB, Secrets Manager, and CloudWatch via VPC endpoints or NAT gateway
5. THE Unified_Agent SHALL never include credentials, connection strings, or secrets in logs or error responses

### Requirement 18: Deployment — AgentCore Runtime Configuration

**User Story:** As a DevOps engineer, I want a single-command deployment for the unified agent with all required environment variables, so that deployments are reproducible and auditable.

#### Acceptance Criteria

1. THE Unified_Agent SHALL be deployed as a single AgentCore runtime in VPC mode using container deployment
2. THE deployment SHALL configure the following environment variables: BEDROCK_MODEL_ID, AWS_REGION, DB_SECRET_ARN, MINUTAS_TABLE_NAME, AGENTCORE_MEMORY_ID
3. THE deployment SHALL replace the existing text agent runtime (old CSV/DynamoDB-based agent)
4. THE AgentCore runtime SHALL use idle session timeout of 15 minutes (900 seconds)
5. THE deployment SHALL configure the execution role with permissions for Bedrock, DynamoDB, Secrets Manager, Aurora VPC access, and AgentCore Memory

### Requirement 19: BidiAgent Compatibility

**User Story:** As an APM using voice mode, I want the voice agent to continue working with the new unified agent, so that my voice experience is uninterrupted after the migration.

#### Acceptance Criteria

1. THE BidiAgent SHALL invoke the new Unified_Agent using the updated TEXT_AGENT_ARN environment variable
2. THE BidiAgent payload format SHALL remain unchanged: {prompt, apm_id, mode: "voice"}
3. THE Unified_Agent response format SHALL maintain backward compatibility: {result: str, success: bool, retries: int}
4. WHEN mode is "voice", THE Unified_Agent SHALL omit structured metadata (table, chart, sql, suggestions) and return only the text result


### Requirement 20: Graceful Error Handling

**User Story:** As an APM, I want the agent to always respond with a helpful message even when something fails, so that I never see cryptic errors or experience hanging requests.

#### Acceptance Criteria

1. IF Aurora PostgreSQL is unreachable, THEN THE Unified_Agent SHALL return "El sistema de datos no está disponible. Intentá en unos minutos." with success=False
2. IF AgentCore_Memory is unavailable, THEN THE Unified_Agent SHALL proceed without memory context and complete the request normally
3. IF Bedrock is throttled, THEN THE Unified_Agent SHALL return "El asistente está ocupado. Intentá en unos segundos." with success=False
4. THE Unified_Agent SHALL never raise an unhandled exception to the caller regardless of the failure type
5. WHEN an error occurs, THE Unified_Agent SHALL log the full error details to CloudWatch while returning only a user-friendly message to the APM

### Requirement 21: Response Formatting and Structured Metadata

**User Story:** As an APM, I want the agent to automatically present data in the most useful format (table, chart, or text), so that I can understand the answer at a glance.

#### Acceptance Criteria

1. WHEN query_db returns more than 2 rows, THE ResponseFormatter SHALL include structured.table in the response with columns and rows
2. WHEN query_db returns data with a temporal column (fecha, mes, año) and a numeric series, THE ResponseFormatter SHALL include structured.chart with type "line" or "bar"
3. THE ResponseFormatter SHALL always include structured.sql with the last SQL query executed by query_db
4. THE ResponseFormatter SHALL always generate structured.suggestions with 2 to 3 contextual follow-up questions
5. THE structured.table rows SHALL be limited to a maximum of 100 entries

### Requirement 22: System Prompt and Context Injection

**User Story:** As a product owner, I want the agent to understand the pharmaceutical business context and always scope queries to the authenticated APM, so that responses are accurate and data-isolated.

#### Acceptance Criteria

1. THE Unified_Agent system prompt SHALL include the complete Aurora schema DDL (21 tables) in optimized format
2. THE Unified_Agent system prompt SHALL include business rules for query scoping (filter by APM's cartera)
3. THE Unified_Agent system prompt SHALL include 5-10 example queries covering common patterns
4. THE Unified_Agent system prompt SHALL inject the authenticated APM_ID and CICLO_ACTUAL as runtime context variables
5. THE total system prompt size SHALL not exceed 12000 tokens to leave adequate context for conversation

