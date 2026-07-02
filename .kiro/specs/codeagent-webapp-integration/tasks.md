# Implementation Plan: CodeAgent WebApp Integration

## Overview

Migrar el CodeAgent validado en POC (Aurora PostgreSQL, 21 tablas, 2M filas) a la webapp PharmAssist como un único runtime AgentCore. El plan se organiza en 4 streams: Agent Core (backend), Frontend UX (structured responses), Platform Features (Memory, Observability, Identity), e Integration & Deployment. Cada stream tiene checkpoints de validación.

## Tasks

- [x] 1. Agent Core — Project structure and toolkit
  - [x] 1.1 Create unified agent entry point and config
    - Create `agentcore/agent.py` with `BedrockAgentCoreApp` wrapper, `handle_invoke` entrypoint
    - Define `UnifiedAgentConfig` with env vars: BEDROCK_MODEL_ID, DB_SECRET_ARN, MINUTAS_TABLE_NAME, AGENTCORE_MEMORY_ID
    - Implement lazy agent initialization with Strands `Agent` and `BedrockModel`
    - _Requirements: 1.1, 18.1, 18.2_

  - [x] 1.2 Implement PharmaToolkit with query_db tool
    - Create `agentcore/toolkit.py` with `PharmaToolkit` class
    - Implement `execute_query(sql)`: SQL validation (SELECT/WITH only), statement_timeout=5000ms, SQLAlchemy QueuePool (pool_size=5, max_overflow=2, pool_pre_ping=True)
    - SSL/TLS with RDS CA bundle, credentials from Secrets Manager
    - Return DataFrame with max 50 rows text + 100 rows in structured metadata (JSON suffix `<!--STRUCTURED:...-->`)
    - _Requirements: 2.1, 2.2, 2.3, 2.6, 4.1, 4.2, 4.3, 4.4, 16.1, 16.2, 16.3_

  - [ ]* 1.3 Write property tests for SQL validation (Property 1)
    - **Property 1: SQL Validation Safety**
    - Test that query_db accepts only SELECT/WITH, rejects INSERT/UPDATE/DELETE/DROP/ALTER/CREATE
    - Test case-insensitivity and whitespace trimming
    - **Validates: Requirements 2.1, 2.2, 16.1**

  - [ ]* 1.4 Write property tests for row limit enforcement (Property 2)
    - **Property 2: Row Limit Enforcement**
    - Test that text output never exceeds 50 rows
    - Test that structured metadata rows never exceeds 100
    - **Validates: Requirements 2.6, 21.5**

  - [x] 1.5 Implement retry logic for failed SQL
    - In `handle_invoke`, wrap agent call with retry loop (max 2 retries)
    - On SQL error, append error message to prompt context for self-correction
    - On all retries exhausted, return user-friendly error in Spanish
    - Include retry count in response metadata
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 1.6 Write property test for retry bound (Property 3)
    - **Property 3: Retry Bound**
    - Test that retries field is always in {0, 1, 2}
    - Test that max 3 total attempts (1 initial + 2 retries)
    - **Validates: Requirements 3.2, 3.4**

  - [x] 1.7 Implement utility tools (buscar_info_publica, generar_brief, obtener_minutas, generar_mensaje_cumpleanos)
    - Migrate from `produccion-poc/agent/` adapting to new toolkit pattern
    - `buscar_info_publica`: DDGS web search by doctor name + specialty
    - `generar_brief`: combine Aurora data + web + DynamoDB minutas
    - `obtener_minutas`: DynamoDB query by doctor_id from MINUTAS_TABLE_NAME
    - `generar_mensaje_cumpleanos`: birthday message with Aurora doctor data
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

  - [x] 1.8 Implement system prompt with Aurora DDL and business rules
    - Create `agentcore/prompts/system_prompt.py` with template
    - Include optimized 21-table DDL (column names, types, relationships)
    - Include business rules: filter by APM's cartera (id_apm), ciclo_actual scoping
    - Include 5-10 example queries covering common patterns
    - Inject APM_ID and CICLO_ACTUAL as runtime variables
    - Total prompt size must not exceed 12000 tokens
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5_

  - [x] 1.9 Implement ResponseFormatter
    - Create `agentcore/response_formatter.py` with `ResponseFormatter` class
    - Parse `<!--STRUCTURED:...-->` from query_db results
    - Include `structured.table` when rows > 2, `structured.sql` always when query_db called
    - Implement `detect_chart_data`: detect temporal columns (fecha, mes, año) + numeric series → chart metadata
    - Implement `generate_suggestions`: produce 2-3 contextual follow-ups
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5_

  - [ ]* 1.10 Write property tests for response formatting (Properties 9, 11, 12)
    - **Property 9: Table Rendering Threshold** — table only when rows > 2
    - **Property 11: Suggestions Count Bound** — always 2-3 suggestions
    - **Property 12: Temporal Data Chart Detection** — chart when temporal + numeric
    - **Validates: Requirements 10.1, 13.4, 21.1, 21.2, 21.4**

  - [x] 1.11 Implement graceful error handling
    - Create `agentcore/error_handler.py` with error mapping
    - Aurora unreachable → "El sistema de datos no está disponible. Intentá en unos minutos."
    - Bedrock throttled → "El asistente está ocupado. Intentá en unos segundos."
    - Memory unavailable → proceed without memory (no user error)
    - Never expose hostnames, IPs, connection strings, stack traces
    - Log full error to CloudWatch, return user-friendly message
    - _Requirements: 4.5, 16.4, 17.5, 20.1, 20.2, 20.3, 20.4, 20.5_

  - [ ]* 1.12 Write property tests for error handling (Properties 4, 5)
    - **Property 4: No Sensitive Data Leakage** — no hostnames/IPs/creds in responses
    - **Property 5: Graceful Degradation** — always returns valid dict, never raises
    - **Validates: Requirements 4.5, 5.4, 6.4, 16.4, 17.5, 20.1-20.5**

  - [x] 1.13 Implement voice mode response filtering (Property 8)
    - When `mode == "voice"`, strip structured metadata from response
    - Return only {result, success, retries} for BidiAgent compatibility
    - _Requirements: 19.3, 19.4_

- [x] 2. Checkpoint — Agent core unit tests pass locally
  - Ensure all unit/property tests pass with `pytest agentcore/tests/`
  - Verify query_db validation logic, retry bounds, error handling
  - Ask the user if questions arise

- [x] 3. Frontend UX — Structured response components
  - [x] 3.1 Define TypeScript types for AgentResponse
    - Create `frontend/src/types/agent.ts` with interfaces: AgentResponse, TableData, ChartData, StructuredData
    - Define WsServerChunk type with discriminated union (chunk | tool_step | complete | error)
    - _Requirements: 10.1, 11.1, 14.1, 14.2, 14.3, 14.4_

  - [x] 3.2 Implement StructuredResponse component
    - Create `frontend/src/components/Chat/StructuredResponse.tsx`
    - Render MUI DataGrid for `structured.table` (compact density, pagination 10/25, sortable)
    - Render MUI X LineChart for `structured.chart.type === "line"`, BarChart for "bar" (height 250px)
    - Render "Ver SQL" toggle with collapsible monospace section
    - Render suggestion chips as MUI Chip (horizontal, wrapped, clickeable)
    - _Requirements: 10.1-10.5, 11.1-11.4, 12.1-12.3, 13.1-13.3_

  - [x] 3.3 Update ChatPanel to handle structured responses
    - Modify `frontend/src/components/Chat/ChatPanel.tsx`
    - Parse WsServerChunk messages: accumulate "chunk" text, show "tool_step" indicator, render "complete" with StructuredResponse
    - On suggestion chip click, send chip text as new message
    - On "error" type, display user-friendly error message
    - _Requirements: 13.3, 14.1, 14.2, 14.3, 14.4_

  - [x] 3.4 Update WebSocket client for streaming protocol
    - Update `frontend/src/api/websocket.ts` to handle new message types
    - Parse `type: "chunk"` for progressive rendering
    - Parse `type: "tool_step"` for tool activity indicator (e.g., "Consultando base de datos...")
    - Parse `type: "complete"` to finalize message with full AgentResponsePayload
    - Parse `type: "error"` for error display
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [ ]* 3.5 Write unit tests for StructuredResponse component
    - Test DataGrid renders when table has > 2 rows
    - Test LineChart renders for chart.type "line"
    - Test BarChart renders for chart.type "bar"
    - Test SQL toggle shows/hides
    - Test chips render and click handler fires
    - _Requirements: 10.1, 11.1, 11.2, 12.1, 12.2, 13.1, 13.3_

- [x] 4. Checkpoint — Frontend renders structured responses with mock data
  - Verify StructuredResponse renders tables, charts, SQL, and chips correctly
  - Use mock AgentResponse data to validate rendering
  - Ask the user if questions arise

- [x] 5. AgentCore Memory integration
  - [x] 5.1 Create AgentCore Memory resource
    - Create memory resource via AgentCore API/CLI with semantic memory strategy
    - Configure event_expiry_duration (e.g., 30 days)
    - Store AGENTCORE_MEMORY_ID in .env
    - _Requirements: 5.1, 6.1_

  - [x] 5.2 Implement MemoryManager class
    - Create `agentcore/memory_manager.py` with `MemoryManager`
    - `store_event(actor_id, session_id, messages)`: create event in STM
    - `retrieve_context(actor_id, query, top_k=3)`: semantic search cross-session
    - `get_session_history(actor_id, session_id)`: get current session events
    - actor_id format: "apm-{apm_id}" consistently
    - Graceful degradation: catch all exceptions, return empty, never fail request
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 5.3 Write property test for actor ID format (Property 6)
    - **Property 6: Actor ID Format Consistency**
    - Test that actor_id always matches "apm-{apm_id}" pattern
    - **Validates: Requirements 5.2, 6.5**

- [x] 6. AgentCore Identity — JWT validation flow
  - [x] 6.1 Update Lambda proxy for identity validation
    - Modify `infrastructure/` Lambda proxy to validate Cognito JWT via AgentCore Identity
    - Extract `custom:apm_id` from validated JWT claims
    - Pass `apm_id` and `session_id` (WebSocket connection ID) in agent payload
    - Return 401 via WebSocket on invalid/expired JWT
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

  - [x] 6.2 Configure AgentCore Identity with Cognito
    - Set up JWT validation configuration pointing to existing Cognito User Pool
    - Configure allowed clients and audience
    - _Requirements: 8.1, 8.5_

  - [x] 6.3 Implement APM data isolation in system prompt
    - Inject APM_ID into system prompt for SQL scoping
    - All queries on cartera_medica MUST filter by id_apm = authenticated APM
    - _Requirements: 8.4, 8.6_

- [x] 7. AgentCore Observability
  - [x] 7.1 Enable traces and metrics for the unified agent
    - Configure AgentCore Observability for the runtime (traces on every request)
    - Emit CloudWatch metrics: end-to-end latency, tool execution times (query_db, memory, LLM)
    - Include error type and message in trace spans on failure
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 7.2 Set up CloudWatch dashboard for GenAI metrics
    - Create dashboard with request volume, latency percentiles (p50, p95, p99), error rates
    - Add widgets for query_db duration, memory retrieval duration, LLM inference duration
    - _Requirements: 7.5, 15.1_

- [x] 8. Checkpoint — Platform features configured and agent invokeable locally
  - Memory resource created and accessible
  - Identity validation works with test JWT
  - Observability traces appear in CloudWatch
  - `agentcore dev` starts without errors
  - Ask the user if questions arise

- [x] 9. Integration — Lambda proxy and streaming
  - [x] 9.1 Update Lambda proxy for structured response streaming
    - Modify Lambda proxy to stream text chunks via WebSocket with `type: "chunk"`
    - Send `type: "tool_step"` with tool name and user-friendly label on tool invocation
    - Send `type: "complete"` with full AgentResponsePayload when done
    - Send `type: "error"` with Spanish message on failures
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [x] 9.2 Update BidiAgent ARN reference
    - Update `bidiagent/agent.py` TEXT_AGENT_ARN env var to point to new unified agent
    - Verify payload format unchanged: {prompt, apm_id, mode: "voice"}
    - Verify response format compatibility: {result, success, retries}
    - _Requirements: 19.1, 19.2, 19.3_

  - [ ]* 9.3 Write property test for response schema completeness (Property 7)
    - **Property 7: Response Schema Completeness**
    - Test that every response has result (str), success (bool), retries (int 0-2)
    - **Validates: Requirements 3.3, 19.3**

- [x] 10. Deployment — AgentCore runtime in VPC
  - [x] 10.1 Configure AgentCore runtime for VPC deployment
    - Set up container deployment with VPC mode (private subnet ENI)
    - Configure security group: egress → Aurora RDS:5432
    - Ensure Aurora SG accepts ingress from AgentCore SG
    - Configure environment variables: BEDROCK_MODEL_ID, AWS_REGION, DB_SECRET_ARN, MINUTAS_TABLE_NAME, AGENTCORE_MEMORY_ID
    - Set idle session timeout to 900 seconds (15 minutes)
    - _Requirements: 17.2, 17.3, 18.1, 18.2, 18.4_

  - [x] 10.2 Configure IAM execution role
    - Permissions: Bedrock InvokeModel/InvokeModelWithResponseStream
    - Permissions: DynamoDB GetItem/Query on minutas table
    - Permissions: Secrets Manager GetSecretValue for DB_SECRET_ARN
    - Permissions: AgentCore Memory read/write
    - Permissions: VPC ENI management (ec2:CreateNetworkInterface, etc.)
    - Permissions: CloudWatch Logs and Metrics
    - _Requirements: 17.4, 18.5_

  - [x] 10.3 Deploy unified agent to AgentCore
    - Run `agentcore deploy` with all required `-env` flags
    - Verify deployment completes without errors
    - Test with `agentcore invoke '{"prompt": "Hola", "apm_id": "test"}'`
    - _Requirements: 18.1, 18.3_

  - [x] 10.4 Update CDK stack IAM roles (if needed)
    - Add IAM permissions for Lambda proxy to invoke new AgentCore runtime
    - Update TEXT_AGENT_ARN in Lambda proxy environment variables
    - Deploy CDK changes with `cdk deploy`
    - _Requirements: 18.3, 18.5_

- [x] 11. Checkpoint — Agent deployed and responding in cloud
  - Invoke agent via `agentcore invoke` with real APM query
  - Verify SQL executes against Aurora successfully
  - Verify memory events are created
  - Verify traces appear in CloudWatch
  - Ask the user if questions arise

- [x] 12. Evaluation suite
  - [x] 12.1 Create evaluation question set (30+ questions)
    - Create `agentcore/evaluations/eval_questions.json` with 30+ questions
    - Cover: cartera (5+), prescripciones (5+), visitas (5+), ventas (5+), briefs (3+), cross-domain (5+)
    - Each question includes: prompt, expected_data_type, validation_criteria
    - _Requirements: 9.1_

  - [x] 12.2 Implement evaluation runner
    - Create `agentcore/evaluations/run_eval.py`
    - Invoke agent for each question, measure latency, validate response
    - Check: success==True, response contains expected data type, no data isolation violation
    - Check: generated SQL is syntactically valid
    - Report accuracy rate and latency stats (p50, p95)
    - _Requirements: 9.2, 9.3, 9.4, 9.5_

  - [ ]* 12.3 Write integration tests for evaluation baseline
    - Run evaluation suite against deployed agent
    - Validate ≥85% accuracy target
    - Validate <6s latency for p95
    - _Requirements: 9.2, 9.3, 15.1_

- [x] 13. End-to-end integration testing
  - [x] 13.1 Test full flow: frontend → WebSocket → Lambda → Agent → Aurora → response
    - Send message from frontend, verify structured response renders (table, chart, SQL, chips)
    - Verify streaming chunks arrive progressively
    - Verify tool_step indicator shows during query execution
    - _Requirements: 14.1, 14.2, 14.3, 15.1_

  - [x] 13.2 Test voice mode end-to-end
    - Invoke via BidiAgent payload format: {prompt, apm_id, mode: "voice"}
    - Verify response has only {result, success, retries} — no structured metadata
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

  - [x] 13.3 Test error scenarios end-to-end
    - Test invalid JWT → 401 + redirect
    - Test complex query timeout → user-friendly error
    - Test agent with unknown table → retry + error
    - _Requirements: 8.5, 20.1, 20.3, 20.4_

- [x] 14. Final checkpoint — Full system operational
  - All tests pass (unit, property, integration)
  - Agent deployed and responding to real APM queries
  - Frontend renders structured responses correctly
  - BidiAgent voice mode works with new agent
  - Evaluation suite achieves ≥85% accuracy
  - Ensure all tests pass, ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each major stream
- Property tests validate universal correctness properties from the design
- Unit tests validate specific examples and edge cases
- **Stream parallelism**: Frontend (tasks 3.x) can be developed in parallel with Agent Core (tasks 1.x) once response types are defined
- **Memory is additive**: tasks 5.x can be done after agent is working — not blocking
- **Evaluation last**: tasks 12.x require a deployed, working agent
- **BidiAgent update is a simple ARN swap** (task 9.2) — do after agent is deployed
- **Deploy is mandatory** before closing this spec (task 10.3)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "1.8", "3.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "1.5", "1.7", "3.3", "3.4"] },
    { "id": 3, "tasks": ["1.6", "1.9", "3.5"] },
    { "id": 4, "tasks": ["1.10", "1.11", "1.13", "5.1"] },
    { "id": 5, "tasks": ["1.12", "5.2", "6.1", "6.2"] },
    { "id": 6, "tasks": ["5.3", "6.3", "7.1"] },
    { "id": 7, "tasks": ["7.2", "9.1"] },
    { "id": 8, "tasks": ["10.1", "10.2"] },
    { "id": 9, "tasks": ["10.3"] },
    { "id": 10, "tasks": ["10.4", "9.2", "9.3"] },
    { "id": 11, "tasks": ["12.1"] },
    { "id": 12, "tasks": ["12.2", "13.1"] },
    { "id": 13, "tasks": ["12.3", "13.2", "13.3"] }
  ]
}
```
