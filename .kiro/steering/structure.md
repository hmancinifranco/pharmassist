---
inclusion: always
---

# Estructura del Proyecto

## Directorios principales

```
pharmassist/
├── frontend/                          # React + Material UI (Vite)
│   ├── src/
│   │   ├── main.tsx                   # Entry point
│   │   ├── App.tsx                    # Router + Layout principal
│   │   ├── theme.ts                   # Tema MUI personalizado
│   │   ├── api/                       # Clients de API y servicios
│   │   │   ├── client.ts             # Axios instance + HTTP API functions
│   │   │   ├── auth.ts               # Cognito auth service
│   │   │   ├── credentials.ts        # Identity Pool → credenciales AWS temporales
│   │   │   ├── voice.ts              # VoiceService (WSS + SigV4 → BidiAgent)
│   │   │   └── websocket.ts          # ChatWebSocket class (WS streaming)
│   │   ├── components/                # Componentes reutilizables
│   │   │   ├── Chat/                  # Panel de chat con el agente IA
│   │   │   ├── Cards/                 # Tarjetas del dashboard
│   │   │   │   ├── TarjetaVisitasHoy.tsx
│   │   │   │   ├── TarjetaCumpleanos.tsx
│   │   │   │   └── TarjetaAlertasSLA.tsx
│   │   │   ├── Audio/                 # Grabación de minutas de voz
│   │   │   ├── Voice/                 # ParticleSphere + VoiceOverlay (modo voz)
│   │   │   └── Layout/                # AppLayout (sidebar + topbar)
│   │   ├── pages/                     # Solo 2 páginas: el chat es el centro del producto
│   │   │   ├── DashboardPage.tsx      # Dashboard del APM + chat
│   │   │   └── LoginPage.tsx          # Login con Cognito
│   │   ├── stores/                    # Zustand stores
│   │   ├── utils/
│   │   └── types/                     # TypeScript types
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
├── backend/                           # Python + FastAPI (Mangum → Lambda)
│   ├── main.py                        # FastAPI app: dashboard, chat fallback, audio
│   ├── lambda_handler.py              # Mangum adapter para Lambda
│   ├── db.py                          # Pool de conexiones a Aurora + Secrets Manager
│   ├── ws_proxy/                      # Lambda proxy del WebSocket → AgentCore
│   ├── agents/
│   │   └── assistant.py               # Agente Strands (uso local / fallback)
│   ├── tools/
│   │   ├── medicos_tools.py           # Herramientas Strands para médicos
│   │   ├── visitas_tools.py           # Herramientas Strands para visitas
│   │   └── ventas_tools.py            # Herramientas Strands para ventas
│   ├── models/
│   │   └── schemas.py                 # Pydantic models
│   ├── data/
│   │   ├── loader.py                  # Acceso a datos (SQL a Aurora PostgreSQL)
│   │   └── README.md                  # Notas de la capa de datos
│   ├── lambdas/                       # Lambda functions independientes
│   │   ├── transcribe_trigger.py      # S3 trigger → Amazon Transcribe
│   │   └── summarize_minuta.py        # Transcribe complete → Bedrock → DDB
│   ├── requirements.txt
│   └── .env.example
├── agentcore/                         # Agente para deploy en Bedrock AgentCore
│   ├── agent.py                       # Entry point wrapeado con BedrockAgentCoreApp
│   ├── requirements.txt               # Deps (bedrock-agentcore, strands-agents, etc.)
│   ├── .bedrock_agentcore.yaml        # Config generada por agentcore configure
│   ├── README.md                      # Instrucciones de deploy + endpoint URL
│   ├── agents/                        # Copia de backend/agents (imports dual-path)
│   ├── tools/                         # Copia de backend/tools
│   ├── models/                        # Copia de backend/models
│   ├── data/                          # Copia de backend/data
│   └── utils/                         # Copia de backend/utils
├── bidiagent/                         # Agente de voz (Nova Sonic) para AgentCore
│   ├── agent.py                       # FastAPI + uvicorn + BidiAgent (NO BedrockAgentCoreApp)
│   ├── Dockerfile                     # Container deployment (requerido por awscrt)
│   └── requirements.txt
├── infrastructure/                    # CDK en Python — app principal
│   ├── app.py                         # Entry point CDK (PharmAssistStack)
│   ├── app_datalake.py                # Entry point DataLakeStack (road-to-prod)
│   ├── app_datasources.py             # Entry point DataSourcesStack (road-to-prod)
│   ├── app_ingestion.py               # Entry point IngestionStack (road-to-prod)
│   ├── stacks/
│   │   ├── pharmassist_stack.py       # Stack principal (Cognito, HTTP/WS API, Lambda, MinutasTable, S3, CloudFront)
│   │   ├── data_lake_stack.py         # S3 + Glue + Athena (road-to-prod, no desplegado)
│   │   ├── data_sources_stack.py      # VPC + RDS que simula warehouses externos
│   │   └── ingestion_stack.py         # DMS Serverless + Glue ETL
│   ├── cdk_constructs/                # L3 constructs (NO 'constructs/': colisiona con el paquete CDK)
│   ├── table_definitions/             # Definiciones de tablas Iceberg
│   ├── tests/unit|integration/
│   └── cdk.json
├── produccion-poc/                    # POC del CodeAgent + CAPA DE DATOS REAL
│   ├── infrastructure/
│   │   ├── stacks/produccion_poc_stack.py   # VPC + Aurora Serverless v2 + Lambda de seed
│   │   └── lambda/seed/
│   │       ├── ddl.sql                # ★ Fuente canónica del modelo de datos (21 tablas)
│   │       ├── seed_handler.py         # Orquesta la generación (~2M filas)
│   │       └── generators/             # Generadores de datos sintéticos
│   ├── agent/                         # Agente del POC + prompts (schema, business_rules)
│   └── tests/e2e/
├── e2e/                               # Tests end-to-end con Playwright
├── data/                              # CSVs legacy (los datos viven en Aurora vía Lambda de seed)
├── scripts/                           # Scripts de automatización (deploy, seed, usuarios demo)
├── docs/                              # Documentación (ver docs/kiro-skills.md como entrada)
│   └── decisions/                     # ADRs
├── Makefile                           # Orquesta setup y deploy completo
├── .env                               # Variables de entorno (NO en git)
├── .env.example                       # Template
├── .gitignore
└── README.md
```

> El modelo de datos vive en `produccion-poc/`, no en `infrastructure/`. Es el desvío estructural más confuso del repo: `ProduccionPocStack` empezó como POC y terminó siendo la capa de datos productiva.

## Convenciones de nombres

### Frontend (TypeScript/React)
- Componentes React: `PascalCase.tsx` (ej: `ChatPanel.tsx`)
- Pages: sufijo `Page` (ej: `DashboardPage.tsx`)
- Stores Zustand: prefijo `use` (ej: `useAppStore.ts`)
- Types/interfaces: `PascalCase` (ej: `Medico`, `Visita`)
- Funciones/variables: `camelCase`
- Archivos de utilidad: `camelCase.ts`
- Constantes: `UPPER_SNAKE_CASE`

### Backend (Python)
- Archivos: `snake_case.py` (ej: `medicos_tools.py`)
- Clases: `PascalCase` (ej: `MedicoSchema`)
- Funciones/variables: `snake_case`
- Agentes: sufijo `_agent` (ej: `visitas_agent.py`)
- Tools Strands: sufijo `_tools` (ej: `medicos_tools.py`)
- Constantes: `UPPER_SNAKE_CASE`

### CDK (Python)
- Stacks: `PascalCase` con sufijo `Stack` (ej: `PharmAssistStack`)
- Constructs: `PascalCase` con nombre descriptivo (ej: `DataIngestionConstruct`)
- Logical IDs: descriptivos con tipo de recurso (ej: `MedicosTable`, `ApiFunction`)
- Archivos: `snake_case.py` (ej: `pharmassist_stack.py`)
- Tests: `test_*.py` en carpetas `unit/` e `integration/`

## Arquitectura

### Frontend
- **Pages** → componentes de página, conectan con stores y API
- **Components** → UI reutilizable, sin lógica de negocio
- **Stores** → Zustand para estado global (APM logueado, filtros activos)
- **API** → Axios client tipado para comunicación con backend

### Backend
- **Agents** → Strands Agents con system prompts y tools específicos
- **Tools** → Funciones Python decoradas como herramientas Strands (consultan datos)
- **Data** → Consulta a Aurora PostgreSQL vía `query_db` (SQL); minutas de voz en DynamoDB
- **API** → Framework web por definir en spec, expone endpoints para el frontend

### AgentCore
- Agente wrapeado con `BedrockAgentCoreApp` en `agentcore/agent.py`
- Módulos compartidos copiados de `backend/` con imports dual-path (try backend.X / except X)
- Deploy via `agentcore deploy` (no `launch`)
- Symlinks no funcionan con `agentcore deploy` — usar copias
- Después de cambios en `backend/`, copiar archivos modificados a `agentcore/`

### Voice (BidiAgent — en migración)
- BidiAgent Python con Strands `BidiAgent`, desplegado en AgentCore con container deployment + protocolo WebSocket
- Frontend se conecta directamente a AgentCore via WSS + SigV4 (sin servidor intermedio)
- Cognito Identity Pool provee credenciales AWS temporales al browser
- Nova Sonic (`amazon.nova-sonic-v1:0`) para speech-to-speech bidireccional
- Tool `consultarAsistente` delega al Text Agent existente con `mode: "voice"`
- Límite de 8 minutos por sesión Nova Sonic (con reconexión)
- ECS Fargate / Socket.IO / ALB eliminados del CDK stack

### Infraestructura (CDK)
- Un solo stack con todos los recursos
- Constructs L3 para agrupar recursos relacionados
- Tags automáticos via CDK Aspects
- Outputs exportan nombres de tablas y ARNs

### Comunicación
```
Frontend (React) ←→ API REST (Python/Lambda) ←→ Strands Agents ←→ Bedrock (Claude)
                                                      ↕
                                        Tools (Aurora PostgreSQL + DynamoDB minutas)

Frontend (React) ←→ WebSocket API GW ←→ Lambda Proxy ←→ AgentCore Runtime ←→ Strands Agent
                                                                                    ↕
                                                                  Tools (Aurora + DynamoDB minutas)

Frontend (React) ←→ WSS + SigV4 ←→ AgentCore (BidiAgent) ←→ Nova Sonic ←→ consultarAsistente
                                                                                  ↕
                                                                           AgentCore (Text Agent)
```

## Git

- `.env` NUNCA se commitea (está en `.gitignore`)
- `.env.example` se mantiene actualizado como template
- `node_modules/`, `dist/`, `.venv/`, `__pycache__/`, `cdk.out/` en `.gitignore`
- `.bedrock_agentcore.yaml` puede commitearse (no tiene secrets)
- CSVs con datos reales en `.gitignore` para producción
- Commits atómicos con mensajes descriptivos en español
