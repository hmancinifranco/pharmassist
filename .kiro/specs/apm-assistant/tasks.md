# Implementation Plan: Asistente APM (PharmAssist)

## Overview

Full-stack prototype webapp for Megalabs Argentina APMs. Implementation follows foundation → data → backend → frontend → integration → polish order. Backend in Python 3.12+ (FastAPI + Strands Agents SDK), frontend in React 18 + TypeScript + Material UI v6. Tier 1 features (dashboard cards, chat, brief, cumpleaños + WhatsApp) are prioritized for demo wow-effect.

## Tasks

- [x] 1. Project scaffolding and shared models
  - [x] 1.1 Initialize frontend project with Vite + React + TypeScript
    - Run `npm create vite@latest frontend -- --template react-ts`
    - Install dependencies: `@mui/material`, `@mui/icons-material`, `zustand`, `axios`, `react-router-dom`
    - Create `frontend/src/theme.ts` with MUI v6 theme (es-AR locale)
    - Create `frontend/src/types/index.ts` with all TypeScript interfaces from design (Medico, VisitaPlanificada, CumpleañosEntry, AlertaSLA, ChatMessage, MinutaVisita)
    - _Requirements: 7.6_

  - [x] 1.2 Initialize backend project with FastAPI
    - Create `backend/requirements.txt` with: fastapi, uvicorn, strands-agents, strands-agents-tools, boto3, pydantic>=2.0, python-dotenv, pandas, ddgs
    - Create `backend/main.py` with FastAPI app skeleton, CORS middleware, and health endpoint
    - Create `backend/models/schemas.py` with all Pydantic models from design (Medico, Visita, VentaReportada, VisitaPlanificada, MinutaVisita, ChatRequest, ChatResponse)
    - Create `backend/.env.example` with all required env vars (BEDROCK_MODEL_ID, AWS_REGION, table names)
    - _Requirements: 8.1, 10.3_

  - [x] 1.3 Create reference data modules
    - Create `backend/data/product_catalog.py` with `ESPECIALIDAD_PRODUCTOS` dict and `CADENCIA_DIAS` dict from design
    - These are used by visit generation, SLA calculation, and product suggestion tools
    - _Requirements: 6.2, 9.1, 9.6_

- [x] 2. Data layer — CSV loading, DynamoDB schema, visit generation
  - [x] 2.1 Implement CSV → DynamoDB loader script
    - Create `backend/data/loader.py` that parses `crm_medicos.csv`, `apm_visitas.csv`, `ventas_reportadas.csv` with pandas
    - Transform to DynamoDB item format: composite keys (`Zona_Producto`, `Anio_Mes`, `APM_Fecha`) and type conversions
    - Implement `batch_write_item` to DynamoDB tables using boto3
    - Table names read from env vars (MEDICOS_TABLE_NAME, VISITAS_TABLE_NAME, VENTAS_TABLE_NAME, PLANIFICADAS_TABLE_NAME)
    - _Requirements: 9.5_

  - [x] 2.2 Implement visit generation algorithm
    - In `backend/data/loader.py` (or separate `backend/data/visit_generator.py`), implement the planned visits generator
    - For each médico: calculate visit frequency from Cadencia, distribute across Mon-Fri targeting 3-5 visits/day per APM
    - Set Tipo_Visita = "Virtual"/"Telefónica" for Cadencia == "Digital"
    - Populate Productos_Sugeridos from ESPECIALIDAD_PRODUCTOS mapping
    - Store generated visits in `visitas_planificadas` table with composite key `APM_Fecha#{Fecha_Planificada}` + SK `Medico_MN`
    - _Requirements: 1.5, 1.6, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 2.3 Write property test: Digital cadencia excludes presencial (Property 2)
    - **Property 2: Digital cadencia excludes presencial visits**
    - Use Hypothesis to generate random médicos with Cadencia="Digital", verify all generated visits have Tipo_Visita in {"Virtual", "Telefónica"}
    - **Validates: Requirements 1.5, 9.4**

  - [ ]* 2.4 Write property test: Visit distribution within daily bounds (Property 3)
    - **Property 3: Visit distribution within daily bounds**
    - Use Hypothesis to generate random CRM datasets, verify each APM has 3-5 visits per working day
    - **Validates: Requirements 1.6, 9.2**

  - [ ]* 2.5 Write property test: Visit generation cadencia frequency (Property 14)
    - **Property 14: Visit generation cadencia frequency**
    - Use Hypothesis to generate random médicos with each cadencia type, verify correct number of visits per period
    - **Validates: Requirements 9.1**

  - [ ]* 2.6 Write property test: Generated visit completeness and APM assignment (Property 15)
    - **Property 15: Generated visit completeness and APM assignment**
    - Use Hypothesis to verify all required fields are non-null and APM matches CRM
    - **Validates: Requirements 9.3, 9.5**

  - [ ]* 2.7 Write property test: Specialty to product mapping (Property 16)
    - **Property 16: Specialty to product mapping**
    - Use Hypothesis to verify Productos_Sugeridos matches ESPECIALIDAD_PRODUCTOS for each médico's specialty
    - **Validates: Requirements 9.6**

- [x] 3. Checkpoint — Data layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Backend utility functions (pure logic)
  - [x] 4.1 Implement SLA breach calculation utility
    - Create `backend/utils/sla_utils.py` with function to calculate days overdue given Cadencia and Fecha_Ultima_Visita
    - Use CADENCIA_DIAS mapping: Mensual=30, Trimestral=90, Semestral=180, Anual=365, Digital=60
    - Handle null Fecha_Ultima_Visita (always overdue, message "Sin visitas registradas")
    - Sort results by days overdue descending
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_

  - [ ]* 4.2 Write property test: SLA breach calculation and sorting (Property 13)
    - **Property 13: SLA breach calculation and sorting**
    - Use Hypothesis to generate random médicos with various cadencias and last visit dates (including null), verify breach detection and sorting
    - **Validates: Requirements 6.1, 6.2, 6.4, 6.6**

  - [x] 4.3 Implement birthday filtering and sorting utility
    - Create `backend/utils/birthday_utils.py` with function to filter médicos with birthdays in next 30 days from a reference date
    - Sort by days until birthday ascending (nearest first)
    - Handle year wrap-around (e.g., reference date Dec 15, birthday Jan 10)
    - _Requirements: 4.1, 4.3_

  - [ ]* 4.4 Write property test: Birthday filtering and proximity sorting (Property 8)
    - **Property 8: Birthday filtering and proximity sorting**
    - Use Hypothesis to generate random birth dates and reference dates, verify correct filtering and sorting
    - **Validates: Requirements 4.1, 4.3**

  - [x] 4.5 Implement phone cleaning and WhatsApp URL utilities
    - Create `frontend/src/utils/phoneUtils.ts` with `cleanPhone(phone: string): string` — removes all non-digit characters
    - Create `frontend/src/utils/whatsappUtils.ts` with `buildWhatsAppUrl(phone: string, message: string): string` — constructs `https://wa.me/{cleaned_phone}?text={encoded_message}`
    - Create `frontend/src/utils/mapsUtils.ts` with `buildGoogleMapsUrl(lat: number, lon: number): string` — constructs `https://www.google.com/maps/search/?api=1&query={lat},{lon}`
    - _Requirements: 1.3, 4.9, 4.10_

  - [ ]* 4.6 Write property test: Phone number cleaning (Property 9)
    - **Property 9: Phone number cleaning**
    - Use fast-check to generate random phone strings with digits, spaces, dashes, plus signs; verify output is digits-only and digit order preserved
    - **Validates: Requirements 4.9**

  - [ ]* 4.7 Write property test: WhatsApp deep link construction (Property 10)
    - **Property 10: WhatsApp deep link construction**
    - Use fast-check to verify URL format and that decoding recovers original message
    - **Validates: Requirements 4.10**

  - [ ]* 4.8 Write property test: Google Maps URL construction (Property 4)
    - **Property 4: Google Maps URL construction**
    - Use fast-check to generate random lat/lon floats, verify URL format matches `https://www.google.com/maps/search/?api=1&query={lat},{lon}`
    - **Validates: Requirements 1.3**

  - [x] 4.9 Implement declining sales filter utility
    - Create `backend/utils/ventas_utils.py` with function to filter sales records where Crecimiento_YoY_Pct < 0, sorted ascending
    - Create function to extract distinct zones for an APM from CRM data
    - _Requirements: 2.1, 2.2, 2.4_

  - [ ]* 4.10 Write property test: Declining sales filtering and sorting (Property 5)
    - **Property 5: Declining sales filtering and sorting**
    - Use Hypothesis to generate random sales records with mixed YoY values, verify only negative values returned and sorted ascending
    - **Validates: Requirements 2.2**

  - [ ]* 4.11 Write property test: APM zone extraction (Property 6)
    - **Property 6: APM zone extraction**
    - Use Hypothesis to generate random CRM datasets with multiple APMs/zones, verify extracted zones match distinct Zona values
    - **Validates: Requirements 2.4**

  - [x] 4.12 Implement visit history summary aggregation utility
    - Create `backend/utils/visitas_utils.py` with function to compute: total visit count, last visit date (max), distinct products presented, visit type distribution counts
    - _Requirements: 5.5_

  - [ ]* 4.13 Write property test: Visit history summary aggregation (Property 11)
    - **Property 11: Visit history summary aggregation**
    - Use Hypothesis to generate random visit histories, verify counts, max date, distinct products, and type distribution
    - **Validates: Requirements 5.5**

- [x] 5. Checkpoint — Utility functions and property tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Backend Strands tools (CRM, Visitas, Ventas)
  - [x] 6.1 Implement CRM/Médicos tools
    - Create `backend/tools/medicos_tools.py` with Strands `@tool` decorated functions:
      - `buscar_medico_por_nombre(nombre: str, apm_id: str)` — search CRM by name, filtered by APM
      - `buscar_medicos_por_zona(zona: str, apm_id: str)` — list médicos in a zone
      - `buscar_medicos_por_apm(apm_id: str)` — list all médicos for an APM
      - `obtener_perfil_medico(medico_mn: int, apm_id: str)` — full profile with access control
    - All tools query DynamoDB (table name from env var), return `{success, message, data}` pattern
    - Enforce APM data isolation: only return médicos where APM field matches requesting APM
    - Handle multiple matches (disambiguation) and not-found cases
    - _Requirements: 5.1, 5.2, 5.6, 5.7, 5.8, 10.1, 10.2, 10.4_

  - [ ]* 6.2 Write property test: APM data isolation (Property 12)
    - **Property 12: APM data isolation**
    - Use Hypothesis to generate multi-APM datasets, verify cross-APM queries return no data and sensitive fields are filtered
    - **Validates: Requirements 5.8, 7.7, 10.1, 10.2**

  - [x] 6.3 Implement Visitas tools
    - Create `backend/tools/visitas_tools.py` with Strands `@tool` decorated functions:
      - `obtener_visitas_por_medico(medico_mn: int, apm_id: str)` — visit history for a doctor
      - `obtener_visitas_planificadas_hoy(apm_id: str)` — today's planned visits
      - `obtener_historial_visitas_apm(apm_id: str, fecha_desde: str, fecha_hasta: str)` — history by date range
    - Query DynamoDB using GSIs (APM-Fecha-index, Medico-Fecha-index)
    - Filter planned visits by APM and current date
    - _Requirements: 1.1, 1.2, 1.4, 5.5, 8.7_

  - [ ]* 6.4 Write property test: Visit filtering by APM and date (Property 1)
    - **Property 1: Visit filtering by APM and date**
    - Use Hypothesis to generate random APM names, dates, and mixed visit records; verify only matching APM+date visits returned
    - **Validates: Requirements 1.1**

  - [x] 6.5 Implement Ventas tools
    - Create `backend/tools/ventas_tools.py` with Strands `@tool` decorated functions:
      - `obtener_ventas_por_zona(zona: str, anio: int, mes: int)` — sales for a zone
      - `obtener_ventas_declinando(zonas: list[str])` — products with negative YoY in given zones
      - `obtener_ventas_por_producto(producto: str, zona: str)` — detail for a product
    - Use ventas_utils for filtering and sorting logic
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_

  - [x] 6.6 Implement Web Search and Generation tools
    - Create `backend/tools/web_search_tools.py` with `buscar_info_publica_medico(nombre, apellido, especialidad, hospital)` using DDGS
    - Create `backend/tools/generacion_tools.py` with:
      - `generar_brief_medico(medico_mn: int, apm_id: str)` — combines CRM data + web search + visit history into structured brief
      - `generar_mensaje_cumpleanos(medico_mn: int)` — generates personalized birthday message using Bedrock
    - Web search uses `DDGS().text()` with `region="ar-es"`, `max_results=5`
    - Fallback: if web search fails, generate brief with CRM data only
    - _Requirements: 4.7, 4.8, 5.3, 5.4_

- [x] 7. Backend API and Strands Agent
  - [x] 7.1 Configure Strands Agent with all tools
    - Create `backend/agents/assistant.py` with single Agent configuration
    - Register all 13+ tools from medicos_tools, visitas_tools, ventas_tools, web_search_tools, generacion_tools
    - Configure BedrockModel with model_id from env var (`anthropic.claude-opus-4-6-20250514-v1:0`), temperature=0.3, max_tokens=4096
    - Write system prompt: Spanish argentino, "vos" form, pharmaceutical domain, cite concrete data
    - Implement session context management for follow-up questions
    - _Requirements: 8.2, 8.3, 8.5, 8.6, 8.7_

  - [x] 7.2 Implement FastAPI endpoints
    - `POST /api/chat` — sends message to Strands agent, returns response with sources
    - `GET /api/dashboard/visits-today?apm_id=X` — queries visitas_planificadas for today, enriches with médico data
    - `GET /api/dashboard/birthdays?apm_id=X` — filters upcoming birthdays (30 days), generates messages via agent
    - `GET /api/dashboard/sla-alerts?apm_id=X` — calculates SLA breaches using sla_utils
    - `POST /api/audio/upload` — receives audio file, sends to Amazon Transcribe, generates minuta via agent
    - `POST /api/minutas` — saves minuta to DynamoDB minutas_visitas table
    - `GET /api/minutas?apm_id=X&medico_mn=Y` — lists minutas
    - All endpoints filter by apm_id for data isolation
    - _Requirements: 1.1, 1.4, 3.2, 3.3, 4.1, 6.1, 7.7, 8.1, 10.1_

- [x] 8. Checkpoint — Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Frontend — Dashboard layout and contextual cards (Tier 1)
  - [x] 9.1 Implement DashboardPage layout and responsive behavior
    - Create `frontend/src/pages/DashboardPage.tsx` as single-screen layout
    - Mobile (<600px): stack Tarjetas vertically, Chat accessible via FAB
    - Desktop (>=600px): Tarjetas in horizontal row, Chat below
    - Create `frontend/src/components/Layout/AppLayout.tsx` — minimal layout, no side menus
    - Create `frontend/src/App.tsx` with React Router, single route to DashboardPage
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 9.2 Implement API client and Zustand store
    - Create `frontend/src/api/client.ts` with Axios instance (base URL from VITE_API_URL env var)
    - Create typed API functions: `getVisitsToday()`, `getBirthdays()`, `getSlaAlerts()`, `sendChatMessage()`, `uploadAudio()`, `saveMinuta()`
    - Create `frontend/src/stores/useAppStore.ts` with Zustand: apm_id, visits, birthdays, alerts, chat messages, loading states
    - _Requirements: 7.7, 8.4_

  - [x] 9.3 Implement TarjetaVisitasHoy card
    - Create `frontend/src/components/Cards/TarjetaVisitasHoy.tsx`
    - Display list of today's planned visits: doctor name, address (Calle + Altura, Barrio), Especialidad_Medica, Productos to discuss
    - Tapping address opens Google Maps URL using mapsUtils (`https://www.google.com/maps/search/?api=1&query={lat},{lon}`)
    - Empty state: "No tenés visitas planificadas para hoy"
    - _Requirements: 1.1, 1.2, 1.3, 1.7_

  - [x] 9.4 Implement TarjetaCumpleaños card
    - Create `frontend/src/components/Cards/TarjetaCumpleanos.tsx`
    - Display upcoming birthdays: full name, Especialidad_Medica, birthday date (day/month), days until birthday
    - Sorted by proximity (nearest first)
    - "Enviar WhatsApp" button per entry: cleans phone with phoneUtils, opens WhatsApp deep link with generated message
    - Tapping doctor name triggers Brief_Médico request in ChatPanel
    - Disable WhatsApp button if no Telefono_Celular, tooltip "Sin número de celular registrado"
    - Empty state: "No hay cumpleaños próximos en los próximos 30 días"
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.9, 4.10, 4.11_

  - [x] 9.5 Implement TarjetaAlertasSLA card
    - Create `frontend/src/components/Cards/TarjetaAlertasSLA.tsx`
    - Display SLA breaches: doctor name, Especialidad_Medica, Cadencia, Fecha_Ultima_Visita, days overdue, Zona
    - Sorted by days overdue descending (most overdue first)
    - Tapping doctor triggers Brief_Médico request in ChatPanel
    - Handle "Sin visitas registradas" for null Fecha_Ultima_Visita
    - Empty state: "Todas las visitas están al día. ¡Buen trabajo!"
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 10. Frontend — Chat panel and voice recorder (Tier 1)
  - [x] 10.1 Implement ChatPanel component
    - Create `frontend/src/components/Chat/ChatPanel.tsx` with MessageList, MessageInput, LoadingIndicator
    - Accept free-text input, send to `/api/chat` endpoint
    - Display loading indicator while waiting for response
    - Render assistant responses with markdown support
    - Maintain session_id for conversation context
    - Create `frontend/src/components/Chat/FABChat.tsx` — FAB button for mobile, opens ChatPanel as overlay/drawer
    - _Requirements: 7.3, 8.1, 8.4, 8.5_

  - [x] 10.2 Implement GrabadorAudio component
    - Create `frontend/src/components/Audio/GrabadorAudio.tsx` with RecordButton, AudioPreview, MinutaPreview
    - Use browser MediaRecorder API to capture audio
    - Validate duration >= 3 seconds, show error "La grabación es muy corta. Grabá al menos 3 segundos." if too short
    - Allow APM to select associated Médico from portfolio before/after recording
    - Send audio to `/api/audio/upload`, display generated minuta for review before saving
    - Handle transcription failure: "No se pudo transcribir el audio. Intentá de nuevo."
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 10.3 Write property test: Audio duration validation (Property 7)
    - **Property 7: Audio duration validation**
    - Use fast-check to generate random float durations (0-300s), verify < 3s rejected and >= 3s accepted
    - **Validates: Requirements 3.7**

- [x] 11. Checkpoint — Frontend core complete
  - Ensure all tests pass, ask the user if questions arise.

 - [x] 12. Integration — Wire frontend to backend
  - [x] 12.1 Connect dashboard cards to API endpoints
    - Wire TarjetaVisitasHoy to `GET /api/dashboard/visits-today`
    - Wire TarjetaCumpleaños to `GET /api/dashboard/birthdays` (includes generated messages)
    - Wire TarjetaAlertasSLA to `GET /api/dashboard/sla-alerts`
    - Implement loading states and error handling for each card
    - APM identity: use hardcoded APM name for demo (e.g., "Valentina Pérez"), configurable via store
    - _Requirements: 1.1, 4.1, 6.1, 7.7_

  - [x] 12.2 Connect ChatPanel to agent endpoint
    - Wire ChatPanel to `POST /api/chat` with apm_id and session_id
    - Handle streaming or polling for long responses
    - Display error toast on API failure: "No se pudo conectar con el servidor. Verificá tu conexión."
    - Handle timeout (>30s): "El asistente está tardando más de lo esperado. Intentá de nuevo."
    - _Requirements: 8.1, 8.4, 8.6_

  - [x] 12.3 Connect GrabadorAudio to transcription pipeline
    - Wire audio upload to `POST /api/audio/upload`
    - Wire minuta save to `POST /api/minutas`
    - Handle all error states (transcription failure, empty text)
    - _Requirements: 3.2, 3.3, 3.5, 3.6_

  - [x] 12.4 Wire cross-component interactions
    - Tapping doctor in birthday card → triggers brief request in ChatPanel
    - Tapping doctor in SLA card → triggers brief request in ChatPanel
    - WhatsApp button → opens deep link with cleaned phone and encoded message
    - Google Maps link → opens coordinates in new tab
    - _Requirements: 1.3, 4.4, 4.10, 6.5_

- [x] 13. Error handling and polish
  - [x] 13.1 Implement frontend error handling
    - API unreachable: toast with retry button
    - Empty states for all cards (Req 1.7, 4.5, 6.7)
    - WhatsApp button disabled when no phone (tooltip "Sin número de celular registrado")
    - Audio recording not supported: hide recorder, show message
    - _Requirements: 1.7, 3.6, 3.7, 4.5, 4.11, 6.7_

  - [x] 13.2 Implement backend error handling
    - All Strands tools follow `{success, message, data}` return pattern
    - Agent system prompt: never expose raw errors, suggest alternatives, respond in Spanish argentino
    - DynamoDB query failures: log error, return user-friendly message
    - Bedrock invocation failure: fallback message "El asistente no está disponible en este momento."
    - Médico not assigned to APM: return 403 "No tenés acceso a la información de ese médico."
    - _Requirements: 8.6, 10.2, 10.4_

- [x] 14. Infrastructure — AWS CDK stack
  - [x] 14.1 Create CDK stack with DynamoDB tables and supporting resources
    - Create `infrastructure/app.py` and `infrastructure/stacks/pharmassist_stack.py`
    - Define 5 DynamoDB tables with GSIs as specified in design (crm_medicos, apm_visitas, ventas_reportadas, visitas_planificadas, minutas_visitas)
    - Add S3 bucket for frontend SPA with website hosting configuration
    - Add CloudFront distribution pointing to the S3 bucket
    - Add CDK Aspects for automatic tagging (TAG_PROJECT, TAG_ENVIRONMENT, TAG_OWNER from env)
    - Configure removal policies (DESTROY for dev)
    - Export stack outputs: table names, CloudFront domain, S3 bucket name
    - Create `infrastructure/requirements.txt` with aws-cdk-lib, constructs
    - Create `infrastructure/cdk.json`
    - _Requirements: 10.3_

- [x] 15. Data loading — CSV to DynamoDB
  - [x] 15.1 Implement CLI interface for the data loader
    - Update `backend/data/loader.py` to accept table names as CLI arguments (--medicos-table, --visitas-table, --ventas-table, --planificadas-table)
    - Add argparse or click for CLI parsing
    - Read CSV paths from DATA_DIR env var or default to `./data/`
    - Add progress output (number of items loaded per table)
    - The loader should: parse CSVs, transform to DynamoDB format, batch write, and generate visitas_planificadas
    - _Requirements: 9.5_

- [x] 16. AgentCore — Agent deployment package
  - [x] 16.1 Create AgentCore wrapper and deployment structure
    - Create `agentcore/agent.py` with `BedrockAgentCoreApp` wrapper that imports the Strands agent and all tools
    - Create `agentcore/requirements.txt` with: bedrock-agentcore, strands-agents, strands-agents-tools, boto3, pydantic>=2.0, pandas, ddgs
    - Copy (or symlink) shared modules from backend: tools/, utils/, models/, data/product_catalog.py
    - The entrypoint should accept `{prompt, apm_id}` payload and return `{result}` response
    - Create `agentcore/README.md` with deploy instructions (agentcore configure, agentcore launch with --env flags)
    - _Requirements: 8.2, 10.3_

- [x] 17. Deploy — Frontend to S3 + CloudFront
  - [x] 17.1 Build and deploy frontend SPA
    - Run `npm run build` in frontend/ to generate dist/
    - Document the deploy commands: `aws s3 sync dist/ s3://<BUCKET> --delete` and CloudFront invalidation
    - Update `frontend/src/api/client.ts` to use VITE_API_URL env var for the API base URL
    - Create a deploy script `scripts/deploy-frontend.sh` that reads S3 bucket and CloudFront distribution ID from CDK outputs
    - _Requirements: 7.6_

- [x] 18. Local end-to-end verification
  - [x] 18.1 Load CSV data into DynamoDB tables
    - Run `backend/data/loader.py` with table names from CDK stack outputs (PharmAssistStack)
    - Load crm_medicos.csv, apm_visitas.csv, ventas_reportadas.csv
    - Generate visitas_planificadas from CRM cadence data
    - Verify data loaded correctly by querying a sample record from each table
    - _Requirements: 9.5_

  - [x] 18.2 Start backend locally and verify API endpoints
    - Start FastAPI backend with `uvicorn backend.main:app --port 8000`
    - Verify `GET /api/dashboard/visits-today?apm_id=Valentina+Pérez` returns data
    - Verify `GET /api/dashboard/birthdays?apm_id=Valentina+Pérez` returns data
    - Verify `GET /api/dashboard/sla-alerts?apm_id=Valentina+Pérez` returns data
    - Verify `POST /api/chat` with a test message returns agent response
    - _Requirements: 1.1, 4.1, 6.1, 8.1_

  - [x] 18.3 Verify frontend connects to local backend
    - Start frontend dev server with `npm run dev` (VITE_API_URL=http://localhost:8000)
    - Verify dashboard cards load data (visits, birthdays, SLA alerts)
    - Verify chat panel sends and receives messages
    - Verify WhatsApp deep links and Google Maps links work
    - _Requirements: 7.1, 7.2, 7.3, 8.4_

- [x] 19. Deploy — Backend to AgentCore
  - [x] 19.1 Deploy Strands agent to Amazon Bedrock AgentCore
    - Run `agentcore configure --entrypoint agent.py --non-interactive --region us-east-1` in agentcore/
    - Run `agentcore launch` with `--env` flags for BEDROCK_MODEL_ID, AWS_REGION, and all DynamoDB table names from CDK outputs
    - Verify agent responds with `agentcore invoke '{"prompt": "Hola", "apm_id": "Valentina Pérez"}'`
    - Document the AgentCore endpoint URL
    - _Requirements: 8.2, 10.3_

  - [x] 19.2 Create FastAPI proxy or update frontend to use AgentCore endpoint
    - Option A: Update `backend/main.py` to proxy chat requests to AgentCore invoke endpoint (keeps all API endpoints in one place)
    - Option B: Deploy backend as a lightweight API (Lambda or ECS) that calls AgentCore for chat and DynamoDB directly for dashboard endpoints
    - Ensure CORS allows CloudFront domain
    - Update VITE_API_URL to point to the deployed backend URL
    - _Requirements: 8.1, 7.7_

  - [x] 19.3 Rebuild and redeploy frontend with production API URL
    - Update `.env` with `VITE_API_URL` pointing to the deployed backend endpoint
    - Run `npm run build` in frontend/
    - Run `scripts/deploy-frontend.sh` or manually sync to S3 and invalidate CloudFront
    - Verify the CloudFront-hosted frontend connects to the deployed backend
    - _Requirements: 7.6_

- [x] 20. Deploy — FastAPI backend to Lambda + API Gateway
  - [x] 20.1 Create Lambda-compatible handler for FastAPI
    - Create `backend/lambda_handler.py` using Mangum to wrap the existing FastAPI app as a Lambda handler
    - Install `mangum` dependency (add to `backend/requirements.txt`)
    - The handler should import the existing `app` from `backend/main.py` and wrap it: `handler = Mangum(app)`
    - Ensure all imports work in Lambda context (no local file paths, no uvicorn dependency at runtime)
    - Test locally with `python -c "from backend.lambda_handler import handler"` to verify imports
    - _Requirements: 8.1, 7.7_

  - [x] 20.2 Update CDK stack with Lambda function + API Gateway
    - Add to `infrastructure/stacks/pharmassist_stack.py`:
    - Create a Lambda function (Python 3.12 runtime) with the `backend/` directory as code asset
    - Set Lambda memory to 512 MB, timeout to 120 seconds (chat + AgentCore proxy can be slow)
    - Pass environment variables: all DynamoDB table names, AWS_REGION, AGENTCORE_AGENT_ARN, AGENTCORE_REGION, BEDROCK_MODEL_ID
    - Grant the Lambda read/write access to all 5 DynamoDB tables (`table.grant_read_write_data(lambda_fn)`)
    - Grant Bedrock invoke permissions (`bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`) for birthday message generation
    - Grant AgentCore invoke permissions (`bedrock-agentcore:InvokeAgentRuntime`) for chat proxy
    - Create an API Gateway HTTP API (not REST API — simpler, cheaper, lower latency)
    - Add a default `$default` route that proxies all requests to the Lambda (catch-all `/{proxy+}`)
    - Enable CORS on API Gateway: allow origins `*`, allow methods `*`, allow headers `*`
    - Export API Gateway URL as stack output (`ApiUrl`)
    - _Requirements: 8.1, 7.7, 10.3_

  - [x] 20.3 Package backend dependencies as Lambda layer
    - Create a `requirements-lambda.txt` in `backend/` with only the runtime dependencies (no uvicorn, no dev tools)
    - Dependencies needed: fastapi, mangum, boto3 (already in Lambda runtime), pydantic, python-dotenv, pandas, strands-agents, strands-agents-tools, ddgs
    - Option A (recommended for demo): Use a Docker-based Lambda build to bundle dependencies
    - Option B: Create a Lambda layer with pip install to a target directory
    - Update CDK to use `aws_lambda.Code.from_asset()` with bundling options that install requirements
    - Ensure the Lambda code asset includes: `backend/main.py`, `backend/lambda_handler.py`, `backend/agents/`, `backend/tools/`, `backend/utils/`, `backend/models/`, `backend/data/`
    - _Requirements: 10.3_

  - [x] 20.4 Deploy CDK stack and verify API Gateway URL
    - Run `cdk diff` to review changes
    - Run `cdk deploy PharmAssistStack` to deploy the updated stack
    - Note the new `ApiUrl` output from the stack
    - Test the API Gateway URL: `curl https://<api-url>/health`
    - Test dashboard endpoint: `curl "https://<api-url>/api/dashboard/sla-alerts?apm_id=Valentina+Pérez"`
    - Test chat endpoint: `curl -X POST https://<api-url>/api/chat -H "Content-Type: application/json" -d '{"message":"Hola","apm_id":"Valentina Pérez"}'`
    - Add `API_URL` to `.env` with the API Gateway URL from CDK output
    - _Requirements: 8.1, 7.7_

  - [x] 20.5 Rebuild and redeploy frontend with API Gateway URL
    - Update `VITE_API_URL` in `.env` to the API Gateway URL from task 20.4
    - Run `npm run build` in `frontend/`
    - Run `scripts/deploy-frontend.sh` to sync to S3 and invalidate CloudFront
    - Verify the CloudFront-hosted frontend loads dashboard cards from API Gateway
    - Verify chat works end-to-end: CloudFront → API Gateway → Lambda → AgentCore
    - _Requirements: 7.6, 7.7_

- [x] 21. Final checkpoint — Full integration and deploy
  - Verify CDK stack is deployed with Lambda + API Gateway
  - Verify data is loaded in DynamoDB
  - Verify AgentCore agent responds
  - Verify frontend on CloudFront connects to API Gateway backend
  - Test all dashboard cards, chat, WhatsApp links, and Google Maps links from CloudFront URL
  - Ask the user if questions arise

- [x] 22. Documentation — Project README
  - [x] 22.1 Write comprehensive README.md
    - Project overview and architecture description
    - Prerequisites (Node.js, Python, AWS CLI, CDK, AgentCore toolkit)
    - Local development setup instructions (frontend, backend, env vars)
    - CDK deployment instructions (synth, deploy, outputs)
    - Data loading instructions (CSV → DynamoDB)
    - AgentCore deployment instructions (configure, launch, invoke)
    - Frontend deployment instructions (build, S3 sync, CloudFront invalidation)
    - Environment variables reference table
    - Project structure overview
    - Troubleshooting common issues

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 16 universal correctness properties from the design
- Tier 1 features (dashboard, chat, brief, cumpleaños) are implemented first for demo impact
- Tier 3 (notas de voz) is included but can be deferred if demo time is tight
- APM identity is hardcoded for demo; production would use auth
- Tasks 14-17 cover AWS infrastructure: CDK stack (DynamoDB + S3 + CloudFront), data loading, AgentCore package, and frontend deploy
- Task 18 validates everything works locally (data load + backend + frontend)
- Task 19 deploys the Strands agent to AgentCore and adds proxy support in FastAPI
- Task 20 deploys the FastAPI backend to Lambda + API Gateway (all in CDK) so CloudFront can reach the API without a local server
- Task 21 is the final end-to-end verification on AWS
- Task 22 documents the full project in README.md
- AgentCore deploy requires `bedrock-agentcore-starter-toolkit` installed and AWS credentials configured
