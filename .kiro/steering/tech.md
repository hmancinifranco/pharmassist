---
inclusion: always
---

# Stack Tecnológico

## Frontend — React + Material UI

- **Framework**: React 18+ con TypeScript
- **UI Library**: Material UI (MUI) v6 — componentes, theming, sistema de diseño
- **Build Tool**: Vite
- **State Management**: Zustand (ligero, sin boilerplate)
- **Routing**: React Router v7
- **HTTP Client**: Axios para comunicación con el backend
- **Charts/Visualización**: MUI X Charts para dashboards de ventas y visitas
- **Formularios**: React Hook Form + Zod (validación)
- **Tablas**: MUI X Data Grid para listados de médicos, visitas, ventas
- **Idioma UI**: Español (Argentina) — locale `es-AR` en MUI
- **Voice**: Socket.IO client (`socket.io-client`) + WebAudio API para modo voz

## Backend — Python + Strands Agents

- **Runtime**: Python 3.12+
- **Framework Web**: Por definir en spec (candidatos: FastAPI, Flask, o serverless con Lambda)
- **AI Agents**: Strands Agents SDK — agentes inteligentes con herramientas
- **LLM**: Amazon Bedrock (Claude) via Strands
- **Datos**: Amazon Aurora PostgreSQL Serverless v2 (médicos, visitas, ventas, prescripciones, cartera, ciclos); Amazon DynamoDB solo para minutas de voz
- **Validación**: Pydantic v2

## AWS Services

- **AI/LLM**: Amazon Bedrock — Claude via Strands Agents SDK
- **Compute**: AWS Lambda (funciones backend) o ECS Fargate
- **Base de datos**: Amazon Aurora PostgreSQL Serverless v2 — médicos, visitas, ventas, prescripciones, cartera, ciclos (provisionada por `ProduccionPocStack`); Amazon DynamoDB solo para `MinutasTable` (minutas de voz)
- **Storage**: Amazon S3 — assets estáticos del frontend
- **CDN**: Amazon CloudFront — distribución del frontend SPA
- **IaC**: AWS CDK en Python — toda la infraestructura como código
- **Agentes**: Amazon Bedrock AgentCore — deploy y runtime de agentes Strands (modo VPC para alcanzar Aurora)
- **Auth**: AWS credentials via AWS CLI profiles o variables de entorno
- **Observabilidad**: CloudWatch Logs + AgentCore Observability
- **Región**: `us-east-1`

## Modelos de Bedrock — IDs válidos

Usar siempre IDs de inference profile (con prefijo `us.`). Configurar via `.env` con `BEDROCK_MODEL_ID`:

```
# Claude (Anthropic via Bedrock) — usar inference profile IDs
us.anthropic.claude-sonnet-5                # Claude Sonnet 5 (DEFAULT del proyecto)
us.anthropic.claude-opus-4-6-v1             # Claude Opus 4.6 (más capaz, más caro)
us.anthropic.claude-sonnet-4-6              # Claude Sonnet 4.6
us.anthropic.claude-haiku-4-5-20251001-v1:0 # Claude Haiku 4.5 (más económico)

# Amazon Nova
us.amazon.nova-premier-v1:0
us.amazon.nova-pro-v1:0

# IMPORTANTE: Habilitar acceso al modelo en Bedrock Console → Model access
# IMPORTANTE: Usar inference profile IDs (us. prefix), NO raw model IDs
```

## Infraestructura CDK (Python)

### Principios CDK
- Un solo stack por app CDK (atomicidad de deploy)
- L2 constructs por defecto, L3 para patrones, L1 solo si no hay alternativa
- Nombres de recursos generados por CDK (no hardcodear physical names)
- Configuración de entornos via stack properties, NO via context ni env vars
- Tags consistentes via CDK Aspects
- Removal policies para entornos efímeros

### Recursos CDK principales
- **Aurora PostgreSQL Serverless v2**: médicos, visitas, ventas, prescripciones, cartera, ciclos (VPC + Aurora + Lambda de seed en `ProduccionPocStack`); datos sintéticos generados por una Lambda de seed
- **DynamoDB Table**: `MinutasTable` (minutas de voz)
- **Lambda Functions**: API endpoints, seed de datos sintéticos a Aurora
- **S3 Buckets**: frontend SPA
- **CloudFront Distribution**: CDN para el frontend
- **IAM Roles**: roles mínimos para Lambda → Aurora/DynamoDB, Lambda → Bedrock

### Patrón Lambda (layered architecture)
```
Handler Layer    → Inicialización, validación, routing
Service Layer    → Lógica de negocio (compartida entre handlers)
Model Layer      → Pydantic models (compartidos)
```

## Dependencias Clave

### Frontend (package.json)
```
@mui/material, @mui/icons-material, @mui/x-data-grid, @mui/x-charts
react, react-dom, react-router-dom
zustand
axios
react-markdown                                  # Renderizado de markdown en chat
react-hook-form, @hookform/resolvers, zod
socket.io-client                                # Voice mode (Socket.IO)
vite, typescript
```

### Backend (requirements.txt)
```
strands-agents
strands-agents-tools
boto3
pydantic>=2.0
python-dotenv
pandas
ddgs                    # Web search (metabuscador, sin API key)
fastapi
uvicorn
```

### Infraestructura (infrastructure/requirements.txt)
```
aws-cdk-lib>=2.170.0
constructs>=10.0.0
```

### AgentCore (agentcore/requirements.txt)
```
bedrock-agentcore
strands-agents
strands-agents-tools
boto3
pandas
ddgs                    # Web search para brief de médicos
```

## Arquitectura de Agentes (Strands)

El core inteligente del sistema es un **CodeAgent** de Strands con 5 tools:

- **`query_db`**: ejecuta SQL read-only generado por el LLM contra Aurora PostgreSQL (timeout 5s)
- **`buscar_info_publica`**: búsqueda de información pública del médico
- **`generar_brief`**: arma el brief de preparación de visita
- **`obtener_minutas`**: recupera minutas de voz desde `MinutasTable` (DynamoDB)
- **`generar_mensaje_cumpleanos`**: genera un mensaje de cumpleaños para un médico

### Patrón de agente con Strands
```python
from strands import Agent
from strands.models import BedrockModel

model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-5",
    region_name="us-east-1",
    max_tokens=4096,
    # OJO: Sonnet 5 y otros modelos de razonamiento deprecaron `temperature`.
    # Omitirlo para ser compatible; los que lo soportan usan su default.
)

agent = Agent(
    model=model,
    tools=[tool1, tool2],
    system_prompt="Sos un asistente para visitadores médicos..."
)
```

### Deploy de agentes con AgentCore
Los agentes se wrappean con `BedrockAgentCoreApp` para deploy:
```python
from bedrock_agentcore import BedrockAgentCoreApp
app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload, context):
    user_message = payload.get("prompt", "Hola")
    response = agent(user_message)
    return {"result": str(response)}

if __name__ == "__main__":
    app.run()
```

## Comandos frecuentes

```bash
# Frontend
npm create vite@latest frontend -- --template react-ts
npm install
npm run dev          # desarrollo (puerto 5173)
npm run build        # build producción

# Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Comando de dev server depende del framework elegido en spec

# CDK
cd infrastructure
pip install -r requirements.txt
cdk synth            # sintetizar CloudFormation
cdk deploy --all     # deploy a AWS
cdk diff             # ver cambios pendientes

# AgentCore
pip install bedrock-agentcore-starter-toolkit
agentcore dev                                    # dev server local
agentcore invoke --dev '{"prompt": "test"}'      # test local
agentcore configure --entrypoint agent.py --non-interactive
agentcore launch                                 # deploy a AWS
agentcore invoke '{"prompt": "test"}'            # test en cloud

# Tests
npm run test         # frontend (vitest)
pytest               # backend
```

## Herramientas Kiro disponibles

- **Powers**: `strands` (agentes AI), `cloud-architect` (CDK/infra), `aws-agentcore` (deploy de agentes)
- **MCP Servers**: AWS Documentation, AWS Knowledge, MUI (Material UI docs)
- Usar MUI MCP para consultar documentación oficial de componentes Material UI
- Usar Strands power para guía de implementación de agentes
- Usar Cloud Architect power para CDK patterns, pricing, y best practices
- Usar AgentCore power para deploy y runtime de agentes
