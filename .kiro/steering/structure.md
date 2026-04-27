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
│   │   ├── api/                       # Axios clients y tipos de API
│   │   │   ├── client.ts             # Axios instance + HTTP API functions
│   │   │   ├── auth.ts               # Cognito auth service
│   │   │   ├── voice.ts              # VoiceService (Socket.IO + WebAudio)
│   │   │   └── websocket.ts          # ChatWebSocket class (WS streaming)
│   │   ├── components/                # Componentes reutilizables
│   │   │   ├── Chat/
│   │   │   │   └── ChatPanel.tsx      # Panel de chat con el agente IA
│   │   │   ├── Voice/
│   │   │   │   ├── ParticleSphere.tsx # Esfera de partículas animada (Canvas 2D)
│   │   │   │   └── VoiceOverlay.tsx   # Overlay fullscreen modo voz
│   │   │   ├── Layout/
│   │   │   │   └── AppLayout.tsx      # Layout con sidebar + topbar
│   │   │   └── common/                # Botones, cards, etc. compartidos
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx      # Dashboard principal del APM
│   │   │   ├── MedicosPage.tsx        # Listado de médicos (DataGrid)
│   │   │   ├── MedicoDetailPage.tsx   # Perfil detallado de un médico
│   │   │   ├── VisitasPage.tsx        # Historial de visitas
│   │   │   ├── VentasPage.tsx         # Análisis de ventas
│   │   │   └── PlanificacionPage.tsx  # Planificación de visitas
│   │   ├── stores/                    # Zustand stores
│   │   │   └── useAppStore.ts
│   │   └── types/                     # TypeScript types
│   │       └── index.ts
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
├── backend/                           # Python + Strands Agents (framework web por definir)
│   ├── main.py                        # Entry point del backend
│   ├── agents/
│   │   ├── coordinator.py             # Agente coordinador (orquesta)
│   │   ├── visitas_agent.py           # Agente de visitas
│   │   ├── ventas_agent.py            # Agente de ventas
│   │   └── crm_agent.py              # Agente de CRM/médicos
│   ├── tools/
│   │   ├── medicos_tools.py           # Herramientas Strands para médicos
│   │   ├── visitas_tools.py           # Herramientas Strands para visitas
│   │   └── ventas_tools.py            # Herramientas Strands para ventas
│   ├── models/
│   │   └── schemas.py                 # Pydantic models
│   ├── data/
│   │   ├── loader.py                  # Carga y parseo de CSVs
│   │   └── README.md                  # Instrucciones para colocar CSVs
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
├── infrastructure/                    # CDK en Python
├── infrastructure/                    # CDK en Python
│   ├── app.py                         # Entry point CDK
│   ├── stacks/
│   │   └── pharmassist_stack.py       # Stack principal (DynamoDB, Lambda, S3, CloudFront)
│   ├── constructs/                    # L3 constructs reutilizables
│   ├── tests/
│   │   ├── unit/                      # CDK assertions
│   │   └── integration/               # Tests contra recursos reales
│   ├── requirements.txt
│   └── cdk.json
├── data/                              # CSVs fuente (gitignored en prod)
│   ├── crm_medicos.csv
│   ├── apm_visitas.csv
│   └── ventas_reportadas.csv
├── scripts/                           # Scripts de automatización
│   └── deploy-frontend.sh            # Build + deploy frontend a S3/CloudFront
├── .env                               # Variables de entorno (NO en git)
├── .env.example                       # Template
├── .gitignore
└── README.md
```

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
- **Data** → Carga de CSVs con pandas, expuestos via tools
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
                                             Tools (DynamoDB/CSVs)

Frontend (React) ←→ WebSocket API GW ←→ Lambda Proxy ←→ AgentCore Runtime ←→ Strands Agent
                                                                                    ↕
                                                                             Tools (DynamoDB)

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
