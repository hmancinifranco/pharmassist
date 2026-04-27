# Implementation Plan: Migración Chat a AgentCore + Cognito Auth + Voice

## Overview

Migración incremental de PharmAssist desde HTTP POST → Lambda → Strands Agent embebido hacia una arquitectura de producción con Cognito auth, WebSocket streaming via AgentCore, Nova Sonic voice-to-voice, pipeline de notas de voz, y nuevos tools. Cada tarea construye sobre la anterior, priorizando la base de autenticación primero y luego las capas de funcionalidad.

## Tasks

- [x] 1. Cognito User Pool + CDK foundation
  - [x] 1.1 Add Cognito User Pool and App Client to PharmAssistStack
    - Add `aws_cognito` imports to `infrastructure/stacks/pharmassist_stack.py`
    - Create `PharmAssistUsers` User Pool with email sign-in, `custom:apm_id` attribute, self-sign-up disabled, password policy (min 8, lowercase, uppercase, digits)
    - Create SPA App Client with `USER_PASSWORD_AUTH` + `USER_SRP_AUTH`, no client secret
    - Add CfnOutputs: `UserPoolId`, `UserPoolClientId`
    - _Requirements: 1.1, 1.2, 1.3, 11.1, 11.2, 11.4_

  - [x] 1.2 Add Cognito Authorizer to HTTP API
    - Import `aws_apigatewayv2_authorizers` and create `HttpJwtAuthorizer` with Cognito issuer URL and audience
    - Modify existing `/{proxy+}` route to use the Cognito authorizer
    - Keep `/health` route without authorizer
    - _Requirements: 2.1, 2.4, 11.5_

  - [x] 1.3 Create demo user via CDK Custom Resource or post-deploy script
    - Create a script `scripts/create-demo-user.py` that uses boto3 `admin_create_user` + `admin_set_user_password` + `admin_update_user_attributes` to create user with email from env var `DEMO_USER_EMAIL` (default: configured in .env) with `custom:apm_id = "Valentina Pérez"`
    - Password from env var `DEMO_USER_PASSWORD`
    - _Requirements: 1.4_

  - [x] 1.4 Update .env and .env.example with new Cognito variables
    - Add `VITE_COGNITO_CLIENT_ID`, `VITE_COGNITO_USER_POOL_ID`, `VITE_AWS_REGION`, `DEMO_USER_PASSWORD`, `DEMO_USER_EMAIL` to `.env.example`
    - Set `DEMO_USER_EMAIL` in `.env` (real email for password reset flow)
    - _Requirements: 11.2_

- [x] 2. Frontend authentication (login + auth store)
  - [x] 2.1 Create auth service `frontend/src/api/auth.ts`
    - Install `@aws-sdk/client-cognito-identity-provider`
    - Implement `login(email, password)`, `refreshSession(refreshToken)`, `parseJwt(token)`, `getApmIdFromToken(idToken)` as specified in design section 5
    - _Requirements: 1.5, 1.6, 1.7, 1.8_

  - [ ]* 2.2 Write property test for JWT apm_id extraction (Property 1)
    - **Property 1: Extracción de apm_id desde JWT**
    - Use fast-check to generate arbitrary strings as apm_id, encode into a mock JWT payload, verify `parseJwt` + extraction returns the exact same string
    - **Validates: Requirements 1.8**

  - [x] 2.3 Create auth store `frontend/src/stores/useAuthStore.ts`
    - Implement Zustand store with: `tokens`, `apmId`, `isAuthenticated`, `isLoading`, `error`, `login()`, `logout()`, `refresh()`, `getIdToken()` as specified in design section 6
    - Store tokens in memory only (not localStorage)
    - _Requirements: 1.6, 1.7, 1.8_

  - [x] 2.4 Create LoginPage component `frontend/src/pages/LoginPage.tsx`
    - MUI form with email + password fields, submit button, error display
    - On success, redirect to dashboard
    - _Requirements: 1.5_

  - [x] 2.5 Wire auth into App.tsx routing
    - Add route guard: if not authenticated, show LoginPage; if authenticated, show dashboard
    - Replace hardcoded `apmId` in `useAppStore` with value from `useAuthStore.apmId`
    - _Requirements: 1.5, 1.8_

  - [x] 2.6 Add JWT interceptor to axios client `frontend/src/api/client.ts`
    - Add axios request interceptor that attaches `Authorization: Bearer <idToken>` header
    - Add axios response interceptor that triggers token refresh on 401
    - _Requirements: 2.5, 1.7_

- [x] 3. Protect FastAPI backend with Cognito JWT extraction
  - [x] 3.1 Update FastAPI Lambda to extract apm_id from JWT claims
    - In `backend/main.py`, read `apm_id` from `event.requestContext.authorizer.jwt.claims["custom:apm_id"]` instead of query parameter
    - Add `USER_POOL_ID` env var to Lambda in CDK
    - Keep `apm_id` query param as fallback for local dev
    - _Requirements: 2.2, 2.3, 11.3_

  - [x] 3.2 Verify dashboard endpoints still work with JWT auth
    - Ensure `/api/dashboard/visits-today`, `/api/dashboard/birthdays`, `/api/dashboard/sla-alerts` work with JWT-based apm_id
    - Keep `/api/chat` HTTP endpoint as fallback
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 4. Checkpoint — Cognito auth end-to-end
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: CDK synth succeeds, login page works, dashboard loads with JWT auth, /health is public.

- [x] 5. New Strands tools (sugerir_proxima_visita + obtener_minutas_medico)
  - [x] 5.1 Implement `obtener_minutas_medico` tool in `backend/tools/visitas_tools.py`
    - Query `minutas_visitas` table by `Medico-Fecha-index`, filter by APM, return last 3 ordered by `Fecha_Creacion` desc
    - Return fields: fecha, resumen, productos_discutidos, compromisos
    - _Requirements: 14.1, 14.4_

  - [ ]* 5.2 Write property test for obtener_minutas_medico (Property 11)
    - **Property 11: Minutas ordenadas y limitadas a 3**
    - Use hypothesis to generate N minutas (0..10), verify result is min(N, 3) items sorted by date desc
    - **Validates: Requirements 14.4**

  - [x] 5.3 Implement `sugerir_proxima_visita` tool in `backend/tools/visitas_tools.py`
    - Combine SLA overdue days, declining sales by zone, pending planned visits
    - Include last minuta context if exists (via `obtener_minutas_medico`)
    - Calculate priority score, return top 5 with: nombre, especialidad, zona, dirección, motivo, productos_recomendados, score, ultima_minuta
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [ ]* 5.4 Write property test for sugerir_proxima_visita ranking (Property 9)
    - **Property 9: Ranking de sugerencia de visita — orden y límite**
    - Use hypothesis to generate sets of doctors with SLA/sales data, verify max 5 results sorted by score desc with required fields
    - **Validates: Requirements 12.2, 12.3, 12.4**

  - [ ]* 5.5 Write property test for minuta context inclusion (Property 10)
    - **Property 10: Inclusión de contexto de minutas en sugerencias**
    - Verify doctors with minutas have `ultima_minuta` field, doctors without have it absent/null
    - **Validates: Requirements 12.6, 14.3**

  - [x] 5.6 Register new tools in agent and sync to agentcore
    - Add `sugerir_proxima_visita` and `obtener_minutas_medico` to `ALL_TOOLS` in `backend/agents/assistant.py`
    - Update system prompt to document the new tools
    - Copy updated files to `agentcore/` directory
    - _Requirements: 12.5, 14.2, 14.3_

- [x] 6. AgentCore mode flag (text vs voice)
  - [x] 6.1 Add mode detection to AgentCore agent
    - Modify `agentcore/agent.py` `invoke()` to read `mode` field from payload (`"text"` default, `"voice"`)
    - Pass mode to `chat()` function
    - _Requirements: 15.15_

  - [x] 6.2 Update assistant.py to adjust response format based on mode
    - In `backend/agents/assistant.py`, modify `chat()` to accept optional `mode` parameter
    - When `mode="voice"`: append instructions to prompt for plain text, no markdown, no tables, no emojis, concise 2-3 sentences
    - Sync changes to `agentcore/agents/assistant.py`
    - _Requirements: 15.15_

  - [ ]* 6.3 Write property test for voice mode response format (Property 13)
    - **Property 13: Formato de respuesta en modo voz**
    - Use hypothesis to verify voice-mode responses contain no markdown chars (`#`, `**`, `|`, `-` as bullet), no emojis, no tables
    - **Validates: Requirements 15.15**

- [x] 7. WebSocket API Gateway + Lambda Proxy
  - [x] 7.1 Create Lambda Proxy code `backend/ws_proxy/ws_handler.py`
    - Implement `handler()` with route dispatch: `$connect` (JWT validation), `$disconnect` (log), `sendMessage` (AgentCore forwarding)
    - JWT validation in `$connect` using `python-jose` or manual decode + Cognito JWKS
    - Extract `apm_id` from validated JWT claims
    - Invoke AgentCore via `invoke_agent_runtime`, stream chunks back via `post_to_connection`
    - Send `{type: "tools", steps: [...]}` before chunks if tool use detected
    - Send `{type: "complete", session_id}` at end
    - Send `{type: "error", message}` on failure (Spanish, no technical details)
    - _Requirements: 3.2, 3.4, 3.5, 3.6, 3.7, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 7.2 Write property test for Lambda Proxy parsing (Property 3)
    - **Property 3: Lambda Proxy — parsing y forwarding**
    - Use hypothesis to generate valid WebSocket events, verify correct extraction of prompt, session_id, apm_id
    - **Validates: Requirements 3.4, 3.6**

  - [ ]* 7.3 Write property test for response protocol types (Property 4)
    - **Property 4: Protocolo de respuesta WebSocket — tipos válidos**
    - Verify all generated messages have valid `type` field and required companion fields
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 5.6**

  - [ ]* 7.4 Write property test for error mapping (Property 7)
    - **Property 7: Mapeo de errores a mensajes en español**
    - Use hypothesis to generate various exception types, verify error messages are in Spanish with no technical details
    - **Validates: Requirements 10.2**

  - [x] 7.5 Add WebSocket API + Lambda Proxy to CDK stack
    - Add `WebSocketApi` with `$connect`, `$disconnect`, `sendMessage` routes
    - Create Lambda function for ws_proxy with Python 3.12, 120s timeout, 256MB
    - Grant IAM: `bedrock-agentcore:InvokeAgentRuntime`, `execute-api:ManageConnections`
    - Pass env vars: `AGENTCORE_AGENT_ARN`, `AGENTCORE_REGION`, `USER_POOL_ID`
    - Create WebSocket stage `prod` with auto-deploy
    - Add CfnOutput `WebSocketUrl`
    - _Requirements: 3.1, 3.2, 3.3, 3.8, 11.1, 11.2_

  - [x] 7.6 Add `VITE_WS_URL` to frontend .env after deploy
    - Update `.env.example` with `VITE_WS_URL` placeholder
    - _Requirements: 3.8_

- [x] 8. Frontend ChatPanel migration to WebSocket
  - [x] 8.1 Create WebSocket service `frontend/src/api/websocket.ts`
    - Implement `ChatWebSocket` class as specified in design section 7
    - Connect with JWT token as query param, handle `onmessage` parsing, reconnect with exponential backoff (3 attempts)
    - _Requirements: 4.2, 4.4, 4.5_

  - [ ]* 8.2 Write property test for WebSocket message format (Property 2)
    - **Property 2: Formato de mensajes WebSocket (cliente → servidor)**
    - Use fast-check to generate arbitrary prompts and UUIDs, verify formatted message matches expected structure
    - **Validates: Requirements 4.1, 5.1**

  - [ ]* 8.3 Write property test for chunk accumulation (Property 5)
    - **Property 5: Acumulación de chunks produce texto completo**
    - Use fast-check to generate sequences of chunk strings, verify concatenation equals the original full text
    - **Validates: Requirements 4.3**

  - [ ]* 8.4 Write property test for partial response suffix (Property 8)
    - **Property 8: Respuesta parcial con sufijo de incompleto**
    - Verify that on disconnect without "complete" message, accumulated text gets "(respuesta incompleta)" appended
    - **Validates: Requirements 10.6**

  - [x] 8.5 Migrate ChatPanel to use WebSocket
    - Update `frontend/src/stores/useAppStore.ts`: add WebSocket connection state, streaming message accumulation, session_id management
    - Modify `sendMessage` to use WebSocket `send()` instead of HTTP POST
    - Render chunks incrementally as they arrive
    - Generate `session_id` (UUID v4) on first message, reuse across conversation
    - On "Limpiar chat", generate new `session_id`
    - Keep HTTP fallback if WebSocket is not connected
    - _Requirements: 4.1, 4.2, 4.3, 4.6, 9.1, 9.2, 9.3, 9.4_

  - [x] 8.6 Add error handling and resilience to ChatPanel
    - Disable send button while waiting for response
    - Show "No se pudo conectar con el asistente." on WebSocket failure with retry button
    - Show "El asistente está tardando. Intentá de nuevo." on 120s timeout
    - Show partial text + "(respuesta incompleta)" on mid-stream disconnect
    - Ensure WebSocket errors don't affect dashboard cards
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 9. Checkpoint — WebSocket chat end-to-end
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: WebSocket connects with JWT, sendMessage streams chunks, reconnect works, HTTP fallback works, dashboard unaffected.

- [x] 10. Voice notes pipeline (S3 → Transcribe → Bedrock → DynamoDB)
  - [x] 10.1 Add S3 audio bucket to CDK stack
    - Create S3 bucket with 30-day lifecycle policy, block public access
    - Add CfnOutput `AudioBucketName`
    - _Requirements: 13.3_

  - [x] 10.2 Add presigned URL endpoint to FastAPI
    - Add `GET /api/audio/presigned-url` endpoint (protected by Cognito) that generates a presigned PUT URL for the audio bucket
    - Include `audio_key` in response for tracking
    - _Requirements: 13.2_

  - [x] 10.3 Create TranscribeLambda
    - Create `backend/lambdas/transcribe_trigger.py`: triggered by S3 `ObjectCreated`, starts Transcribe batch job with `LanguageCode="es-ES"`
    - Add Lambda + S3 event notification to CDK stack
    - Grant IAM: `transcribe:StartTranscriptionJob`, `s3:GetObject`
    - _Requirements: 13.4, 13.5_

  - [x] 10.4 Create SummarizeLambda
    - Create `backend/lambdas/summarize_minuta.py`: triggered by EventBridge when Transcribe job completes
    - Get transcript, invoke Bedrock Claude to generate structured minuta (resumen, productos, compromisos, proximos_pasos)
    - Write to `minutas_visitas` DynamoDB table with fields: Minuta_ID, APM, Medico_MN, Fecha_Creacion, Transcripcion, Resumen, Productos_Discutidos, Compromisos, Proximos_Pasos, Audio_S3_Key, Estado
    - Add Lambda + EventBridge rule to CDK stack
    - Grant IAM: `transcribe:GetTranscriptionJob`, `bedrock:InvokeModel`, `dynamodb:PutItem`
    - _Requirements: 13.6, 13.7, 13.8_

  - [x] 10.5 Update frontend audio upload flow
    - Modify `GrabadorAudio.tsx` to: get presigned URL, upload audio to S3, show processing states ("Subiendo audio...", "Transcribiendo...", "Generando resumen...", "Listo")
    - Allow APM to select a doctor to associate the note with
    - Show minuta for review when ready
    - _Requirements: 13.1, 13.2, 13.9, 13.10, 13.11_

- [x] 11. Checkpoint — Voice notes pipeline
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: audio upload to S3, Transcribe job runs, SummarizeLambda generates minuta, minuta appears in DynamoDB.

- [x] 12. Voice server (Node.js + Nova Sonic + ECS Fargate)
  - [x] 12.1 Scaffold voice server project `voice-server/`
    - Create `voice-server/package.json`, `voice-server/tsconfig.json`, `voice-server/Dockerfile`
    - Install dependencies: `socket.io`, `@aws-sdk/client-bedrock-runtime`, `@aws-sdk/client-cognito-identity-provider`, `jsonwebtoken`, `jwks-rsa`
    - _Requirements: 15.16_

  - [x] 12.2 Implement voice server core `voice-server/src/index.ts`
    - Socket.IO server with JWT Cognito validation middleware
    - Extract `apm_id` from validated JWT
    - On `startSession`: create Nova Sonic bidirectional stream with `amazon.nova-sonic-v1:0`, system prompt in Spanish, `laura` voice, `consultarAsistente` tool spec
    - On `audioInput`: forward PCM chunks to Nova Sonic
    - On Nova Sonic `toolUse(consultarAsistente)`: invoke AgentCore with `{prompt, apm_id, mode: "voice"}`
    - On Nova Sonic audio output: emit `audioOutput` to client
    - On Nova Sonic state change: emit `stateChange` ("listening", "thinking", "speaking")
    - Handle 8-minute connection limit with reconnection logic
    - On `disconnect`: close Nova Sonic session
    - _Requirements: 15.8, 15.9, 15.10, 15.11, 15.12, 15.13, 15.14, 15.17, 15.18_

  - [ ]* 12.3 Write property test for consultarAsistente payload (Property 12)
    - **Property 12: Payload de consultarAsistente incluye mode voice**
    - Use fast-check to generate arbitrary questions and apm_ids, verify payload includes `mode: "voice"`
    - **Validates: Requirements 15.13, 15.18, 15.19**

  - [x] 12.4 Add ECS Fargate service + ALB to CDK stack
    - Create ECR repository, ECS cluster, Fargate task definition, Fargate service
    - Create ALB with health check
    - Pass env vars: `AGENTCORE_AGENT_ARN`, `AGENTCORE_REGION`, `USER_POOL_ID`, `AWS_REGION`
    - Grant IAM: `bedrock:InvokeModelWithResponseStream`, `bedrock-agentcore:InvokeAgentRuntime`
    - Add CfnOutput `VoiceServerUrl`
    - Add `VITE_VOICE_URL` to `.env.example`
    - _Requirements: 15.16, 11.1_

- [x] 13. Frontend voice mode UI (particle sphere, Perplexity-style)
  - [x] 13.1 Create particle sphere animation component `frontend/src/components/Voice/ParticleSphere.tsx`
    - Canvas 2D or WebGL rendering of particles distributed in spherical shape
    - Animate at 60fps: expand/vibrate on audio activity, contract on silence, smooth rotation on "thinking"
    - Accept `state` prop: "listening" | "thinking" | "speaking" | "idle"
    - Accept `audioLevel` prop for volume reactivity
    - _Requirements: 15.2, 15.6, 15.7_

  - [x] 13.2 Create voice overlay component `frontend/src/components/Voice/VoiceOverlay.tsx`
    - Fullscreen overlay over dashboard with clean background
    - Center: ParticleSphere component
    - Below sphere: status text ("Escuchando...", "Pensando...", "Respondiendo...", "Conectando...")
    - Bottom: X button (close/hangup) left, microphone button (mute/unmute) right
    - Mute button with visual feedback (color/icon change)
    - _Requirements: 15.1, 15.3, 15.4, 15.5_

  - [x] 13.3 Create voice service `frontend/src/api/voice.ts`
    - Socket.IO client connecting to voice server with JWT auth
    - Capture microphone audio via WebAudio API (PCM 16kHz mono)
    - Stream audio chunks to server via `audioInput` event
    - Receive and play `audioOutput` chunks via WebAudio API
    - Handle `stateChange` events to update UI state
    - Support barge-in (interrupt playback when user speaks)
    - _Requirements: 15.8, 15.9, 15.10, 15.11, 15.17_

  - [x] 13.4 Wire voice mode into App
    - Add voice mode button to dashboard (microphone icon)
    - On click: show VoiceOverlay, request microphone permission, connect Socket.IO
    - On close: disconnect Socket.IO, stop microphone, hide overlay
    - Voice mode and text chat are independent experiences
    - _Requirements: 15.1, 15.19_

- [x] 14. Observability and logging
  - [x] 14.1 Add structured logging to Lambda Proxy
    - Log `apm_id`, `session_id`, `connection_id`, `prompt_length`, `response_length`, duration on each invocation
    - Log warning if invocation > 60 seconds
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ]* 14.2 Write property test for data isolation (Property 6)
    - **Property 6: Aislamiento de datos por apm_id**
    - Use hypothesis to verify tool results only contain records for the given apm_id
    - **Validates: Requirements 6.4**

- [x] 15. Final checkpoint — End-to-end testing + deploy + README
  - [x] 15.1 Deploy everything to AWS
    - Run `cdk deploy` with all new resources (Cognito, WebSocket API, Lambda Proxy, S3 audio bucket, Transcribe/Summarize Lambdas, ECS Fargate voice server)
    - Run `agentcore deploy` with updated tools and mode flag
    - Deploy frontend with new env vars (`VITE_COGNITO_CLIENT_ID`, `VITE_WS_URL`, `VITE_VOICE_URL`)
    - _Requirements: 11.1, 15.20_

  - [x] 15.2 End-to-end verification
    - Verify login flow: email/password → JWT → dashboard loads
    - Verify WebSocket chat: connect → send message → streaming response → complete
    - Verify HTTP fallback: chat works when WebSocket unavailable
    - Verify voice notes: record → upload → transcribe → summarize → minuta in DDB
    - Verify voice mode: connect → speak → Nova Sonic → AgentCore → audio response
    - Verify new tools: "¿a quién puedo visitar?" triggers sugerir_proxima_visita
    - Verify dashboard regression: all cards load correctly with JWT auth
    - _Requirements: 7.1, 7.5, 15.20_

  - [x] 15.3 Update README.md with new architecture and setup instructions
    - Document new architecture (Cognito, WebSocket, Voice, Audio pipeline)
    - Update setup instructions with new env vars
    - Document demo user credentials
    - Add deployment instructions for all components
    - _Requirements: 15.20_

## Known Issues (Pendientes)

- **Brief no incluye minutas guardadas**: Al pedir un brief de un médico, el agente no muestra las notas de voz guardadas previamente. Posibles causas: (1) `generar_brief_medico` no llama internamente a `obtener_minutas_medico`, (2) el agente en AgentCore no tiene la tabla de minutas configurada, (3) el `Medico_MN` guardado en la minuta no coincide con el del brief. Investigar y corregir.

- **Voice mode no funciona en producción (Mixed Content)**: El frontend está en HTTPS (CloudFront) pero el voice server ALB está en HTTP. El browser bloquea conexiones `ws://` desde páginas HTTPS. Para resolverlo se necesita: (1) un dominio custom, (2) un certificado ACM, (3) agregar listener HTTPS al ALB. Funciona en desarrollo local.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties from the design document
- The voice server (tasks 12-13) can be developed in parallel with the audio pipeline (task 10) after the WebSocket chat is working
- All infrastructure changes go into the existing `PharmAssistStack` CDK stack
- Files modified in `backend/` must be synced to `agentcore/` before redeploying AgentCore
