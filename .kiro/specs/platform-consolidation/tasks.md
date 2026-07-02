# Implementation Plan: Platform Consolidation

## Overview

Consolidación de la plataforma PharmAssist: migración de endpoints del dashboard a Aurora PostgreSQL (vía `backend/db.py`), eliminación de 4 tablas DynamoDB del CDK stack, mejoras UX (loading skeletons, dark mode, suggestion chips, WebSocket fallback), deploy unificado con Makefile (`deploy-all` / `destroy`), y test E2E con Playwright.

**Lenguajes**: Python (backend, CDK), TypeScript (frontend, E2E)

## Tasks

- [x] 1. Crear módulo de conexión Aurora (`backend/db.py`)
  - [x] 1.1 Crear `backend/db.py` con pool psycopg2 + Secrets Manager
    - Implementar `_get_secret()` para fetch de credenciales desde Secrets Manager
    - Implementar `_init_pool()` con `ThreadedConnectionPool(minconn=2, maxconn=10)`
    - Implementar `get_pool()` singleton y `get_connection()` context manager
    - Configurar `sslmode=require` + CA bundle
    - _Requirements: 1.4, 1.5_

  - [ ]* 1.2 Write unit tests for `backend/db.py`
    - Test `get_connection()` returns and releases connections to pool
    - Test `_get_secret()` calls Secrets Manager with correct ARN
    - Test pool initialization with expected params
    - Mock `boto3` and `psycopg2` for isolation
    - _Requirements: 1.4, 1.5_

- [x] 2. Refactorizar dashboard endpoints a Aurora
  - [x] 2.1 Refactorizar `GET /api/dashboard/visits-today` para consultar Aurora
    - Reemplazar lógica DynamoDB por query parametrizado a tabla `agenda` JOIN `doctor`
    - Filtrar por `apm_id` y `fecha_planificada = CURRENT_DATE`
    - Atrapar `psycopg2.OperationalError` / `InterfaceError` → HTTP 503 genérico
    - Mantener el contrato de respuesta existente (`VisitaPlanificada[]`)
    - _Requirements: 1.1, 1.6, 1.7_

  - [x] 2.2 Refactorizar `GET /api/dashboard/birthdays` para consultar Aurora
    - Reemplazar lógica DynamoDB por query a tabla `doctor` filtrado por `apm_id`
    - Ordenar por día del año próximo al cumpleaños
    - Usar `filtrar_cumpleanos_proximos(rows, dias_adelante=30)`
    - Atrapar errores de conexión → HTTP 503
    - _Requirements: 1.2, 1.6, 1.7_

  - [x] 2.3 Refactorizar `GET /api/dashboard/sla-alerts` para consultar Aurora
    - Reemplazar lógica DynamoDB por query a `cartera_medica` JOIN `doctor`
    - Filtrar por `apm_id`, usar `obtener_alertas_sla(rows)`
    - Atrapar errores de conexión → HTTP 503
    - _Requirements: 1.3, 1.6, 1.7_

  - [ ]* 2.4 Write property tests for dashboard data isolation
    - **Property 1: Data isolation — visits filtered by APM**
    - **Property 2: Data isolation — birthdays filtered by assigned APM**
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 2.5 Write property test for SLA alert correctness
    - **Property 3: SLA alert correctness**
    - **Validates: Requirements 1.3**

  - [ ]* 2.6 Write property test for Aurora error handling
    - **Property 4: Aurora error produces 503 without internal details**
    - **Validates: Requirements 1.7**

- [x] 3. Checkpoint — Backend Aurora funcional
  - Ensure all tests pass, ask the user if questions arise.
  - Verificar que `backend/db.py` importa correctamente en `main.py`
  - Verificar que los 3 endpoints compilan sin errores de import

- [x] 4. Eliminar tablas DynamoDB del CDK stack
  - [x] 4.1 Eliminar definiciones de 4 tablas DynamoDB de `pharmassist_stack.py`
    - Eliminar `self.medicos_table` (MedicosTable / `crm_medicos`)
    - Eliminar `self.visitas_table` (VisitasTable / `apm_visitas`)
    - Eliminar `self.ventas_table` (VentasTable / `ventas_reportadas`)
    - Eliminar `self.planificadas_table` (PlanificadasTable / `visitas_planificadas`)
    - Conservar `self.minutas_table` (MinutasTable / `minutas_visitas`)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 4.2 Eliminar CfnOutputs y permisos IAM asociados a las 4 tablas
    - Eliminar `CfnOutput` que exportan nombres/ARNs de las 4 tablas
    - Eliminar `grant_read_write_data()` / `grant_read_data()` del Lambda proxy hacia las 4 tablas
    - Eliminar environment variables del Lambda proxy que referencian las tablas eliminadas
    - Conservar permisos y outputs de MinutasTable
    - _Requirements: 2.6, 2.7, 2.8_

  - [x] 4.3 Validar CDK synth genera template válido
    - Ejecutar `cd infrastructure && . .venv/bin/activate && cdk synth`
    - Verificar que no hay errores de síntesis
    - Verificar que MinutasTable sigue presente en el template generado
    - **Nota**: `python app.py` genera el template correctamente (exit 0). El CLI `cdk synth` tiene un bug de captura de output por version mismatch (CLI 2.1122 vs lib 2.199), pero el template se genera bien y `cdk deploy` funciona.
    - _Requirements: 2.9_

- [x] 5. Implementar loading skeletons en dashboard
  - [x] 5.1 Agregar Skeletons a las 3 tarjetas del dashboard
    - Implementar patrón loading/error/data en `DashboardPage.tsx`
    - Skeleton para TarjetaVisitasHoy (text + rectangular)
    - Skeleton para TarjetaCumpleanos
    - Skeleton para TarjetaAlertasSLA
    - Estado vacío con mensaje para error post-retry
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 6. Implementar WebSocket fallback silencioso
  - [x] 6.1 Extender `useAppStore.ts` con fallback HTTP en `sendMessage`
    - Si `wsConnected && wsInstance` → enviar por WS
    - Si no → POST a `/api/chat` con `sendChatMessage()`
    - Agregar user message al chat inmediatamente (optimistic)
    - Agregar flags `fallbackActive` al store state
    - _Requirements: 4.1, 4.3_

  - [x] 6.2 Implementar reconexión automática con backoff exponencial
    - Retry: 1s, 2s, 4s, max 30s
    - Durante retry, mensajes van por HTTP
    - Cuando reconecta, retomar WS automáticamente
    - Log solo en `console.debug`, sin UI feedback
    - _Requirements: 4.2, 4.4_

- [x] 7. Implementar dark mode fixes
  - [x] 7.1 Ajustar theme MUI (`frontend/src/theme.ts`) para dark mode
    - Agregar `darkPalette` con background y text overrides
    - Agregar `styleOverrides` para MuiCard (borde, background)
    - Agregar `styleOverrides` para MuiChip (color, borde visible)
    - Agregar `styleOverrides` para MuiSkeleton (backgroundColor)
    - Agregar `styleOverrides` para MuiDataGrid (borders, headers)
    - Verificar contraste WCAG AA (4.5:1 mínimo)
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 8. Implementar Suggestion Chips
  - [x] 8.1 Crear componente `SuggestionChips.tsx`
    - Definir array de 4 sugerencias en constante local
    - Componente con `onChipClick` y `visible` props
    - Renderizar `Chip` de MUI con `variant="outlined"` y `clickable`
    - _Requirements: 6.1, 6.5_

  - [x] 8.2 Integrar SuggestionChips en ChatPanel
    - Mostrar chips cuando `chatMessages.length === 0`
    - Al click, enviar texto como mensaje de usuario via `sendMessage`
    - Ocultar chips después de enviar cualquier mensaje
    - Agregar `data-testid="suggestion-chip"` para E2E
    - _Requirements: 6.2, 6.3, 6.4_

  - [ ]* 8.3 Write property tests for Suggestion Chips
    - **Property 6: Suggestion chip click sends user message**
    - **Property 7: Suggestion chips hidden after message**
    - **Property 8: Suggestion chip count within bounds**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

- [x] 9. Checkpoint — Frontend features completas
  - Ensure all tests pass, ask the user if questions arise.
  - Verificar que el frontend compila sin errores (`npm run build`) ✅ (verificado)
  - Verificar que skeletons, chips, dark mode y WS fallback están integrados ✅

- [x] 10. Agregar targets `deploy-all` y `destroy` al Makefile
  - [x] 10.1 Agregar target `deploy-all` al Makefile
    - Ejecutar en orden: `deploy-infra` → `env-from-outputs` → `deploy-text-agent` → `deploy-bidi-agent` → `deploy-frontend`
    - Después de `deploy-infra`, ejecutar `make env-from-outputs` para escribir outputs del stack en `.env`
    - Esto asegura que los deploys de agentes tengan acceso a los resource names/ARNs más recientes
    - Documentar dependencias entre pasos en comentarios
    - Error propagation: Makefile detiene si un paso falla
    - _Requirements: 7.1, 7.3, 7.6_

  - [x] 10.2 Crear script `scripts/deploy-bidi-agent.sh` con auto-wiring
    - Ejecutar `agentcore status` en `agentcore/` para obtener TEXT_AGENT_ARN
    - Pasar ARN como `-env TEXT_AGENT_ARN=<arn>` al deploy del BidiAgent
    - Si Text Agent no está desplegado, mostrar error y exit 1
    - _Requirements: 7.2, 8.1, 8.2, 8.3_

  - [x] 10.3 Actualizar target `destroy` con orden correcto
    - Destruir en orden: BidiAgent → Text Agent → CDK stack
    - Pedir confirmación interactiva antes de proceder
    - _Requirements: 7.4, 7.5_

- [x] 10.4 Verificar identity mapping (Cognito → Aurora)
  - Después de que CDK despliega Cognito, crear usuario demo con `custom:apm_id` matching un APM ID en Aurora
  - Verificar via `scripts/setup_peccy_user.py` (o `make seed-peccy`) que el usuario Peccy existe con `custom:apm_id` correcto
  - El valor de `custom:apm_id` debe coincidir con un `apm.id` en Aurora que tenga doctores en `cartera_medica`
  - Ejecutar: `make seed-peccy` y verificar output exitoso
  - Validar en Cognito Console que el atributo custom está presente

- [x] 11. Deploy CDK stack a AWS (CREATE fresh — account 709578350924)
  - [x] 11.1 Ejecutar `cdk deploy` del PharmAssistStack COMPLETO desde cero
    - Este es un CREATE (no update) del stack. Crea todos los recursos from scratch:
      - Cognito User Pool + Identity Pool
      - HTTP API Gateway
      - WebSocket API Gateway
      - Lambda proxy
      - CloudFront + S3 (frontend)
      - S3 audio bucket
      - MinutasTable DynamoDB
    - Ejecutar `cd infrastructure && . .venv/bin/activate && cdk deploy PharmAssistStack --profile $AWS_PROFILE --require-approval never`
    - Verificar que el deploy completa sin errores
    - Verificar que todos los recursos fueron creados correctamente
    - Si falla: diagnosticar, corregir, y re-intentar
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.9_

  - [x] 11.2 Ejecutar `make env-from-outputs` para escribir CDK outputs a `.env`
    - Esto popula: VITE_COGNITO_USER_POOL_ID, VITE_COGNITO_CLIENT_ID, VITE_WS_URL, API_URL, MINUTAS_TABLE_NAME, AUDIO_BUCKET_NAME, etc.
    - Verificar que `.env` tiene todos los valores no-vacíos
    - Estos valores son necesarios para los deploys subsiguientes (agents, frontend)

- [x] 12. Checkpoint — Deploy exitoso
  - Ensure all tests pass, ask the user if questions arise.
  - Verificar que el stack desplegó correctamente ✅ (outputs en .env)
  - Verificar que `make deploy-all` funciona de punta a punta

- [x] 13. Implementar test E2E con Playwright
  - [x] 13.1 Crear configuración Playwright en `e2e/`
    - Crear `e2e/playwright.config.ts` con timeout 60s, screenshots `on`, base URL desde env
    - Crear `e2e/package.json` con dependencia `@playwright/test`
    - Agregar `make e2e-test` al Makefile
    - _Requirements: 9.6, 9.8_

  - [x] 13.2 Crear test E2E `e2e/tests/dashboard-flow.spec.ts`
    - Test: login con credenciales demo desde env
    - Test: dashboard renderiza al menos una tarjeta con datos
    - Test: suggestion chips visibles antes del primer mensaje
    - Test: enviar mensaje al chat y verificar respuesta del agente
    - Capturar screenshot del dashboard en `e2e/screenshots/`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.7_

- [x] 14. Final checkpoint — Spec completo
  - Ensure all tests pass, ask the user if questions arise.
  - Verificar que `cdk synth` sigue pasando
  - Verificar que el frontend compila
  - Verificar que los unit tests pasan
  - Spec listo para E2E test post-deploy

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- `backend/db.py` es el bloque fundacional — todos los endpoints dependen de él (Task 1 antes de Task 2)
- CDK changes (Task 4) pueden ejecutarse en paralelo con backend (Tasks 1-2) y frontend (Tasks 5-8)
- El deploy CDK (Task 11) depende de que el synth pase (Task 4.3)
- E2E test (Task 13) es el último paso — necesita todo desplegado
- Property tests validan las correctness properties definidas en el design document
- El target `deploy-all` del Makefile orquesta: CDK → Text Agent → BidiAgent → Frontend
- Los endpoints mantienen el mismo contrato de respuesta — el frontend no requiere cambios de API

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "4.2", "5.1", "7.1"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "4.3", "6.1", "8.1"] },
    { "id": 3, "tasks": ["2.4", "2.5", "2.6", "6.2", "8.2"] },
    { "id": 4, "tasks": ["8.3", "10.1", "10.2", "10.3"] },
    { "id": 5, "tasks": ["10.4", "11.1"] },
    { "id": 6, "tasks": ["11.2", "13.1"] },
    { "id": 7, "tasks": ["13.2"] }
  ]
}
```

## Target Account & Region

- **Account**: `709578350924`
- **Region**: `us-east-1`
- El **PharmAssistStack** se crea desde cero (CREATE, no UPDATE de un stack existente)
- Todos los deploys (CDK, AgentCore text agent, BidiAgent, frontend) apuntan a esta cuenta/región
- El profile AWS debe tener permisos de `AdministratorAccess` o equivalente sobre esta cuenta
