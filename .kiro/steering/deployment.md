---
inclusion: always
---

# Build, Deploy y Configuración

## Seguridad para repo público (OBLIGATORIO)

Toda información sensible DEBE estar en `.env` (que está en `.gitignore`) y NUNCA en el código fuente.

**Datos que NUNCA deben aparecer en código commiteado:**

- AWS Account IDs, CLI profile names
- API keys, tokens, secrets de cualquier tipo
- Bedrock model IDs hardcodeados (usar .env)
- Nombres reales de personas, emails, teléfonos (en código, no en CSVs de datos)
- Credenciales de base de datos
- ARNs de roles IAM

## Configuración via `.env` (FUENTE DE VERDAD)

Todas las variables de entorno se centralizan en `.env` en la raíz del proyecto.
Cada script, CDK stack, agentcore deploy y comando debe leer de acá.

```bash
# === AWS General ===
AWS_PROFILE=your-profile
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# === Bedrock ===
# Usar inference profile IDs (us. prefix), NO raw model IDs
BEDROCK_MODEL_ID=us.anthropic.claude-opus-4-6-v1

# === Tags (aplicados a todos los recursos via CDK Aspects) ===
TAG_PROJECT=PharmAssist
TAG_ENVIRONMENT=dev
TAG_OWNER=your-team

# === Frontend ===
VITE_API_URL=http://localhost:8000

# === AgentCore ===
AGENTCORE_AGENT_NAME=pharmassist-agent
AGENTCORE_REGION=us-east-1
# Set AGENTCORE_AGENT_ARN to proxy /api/chat through AgentCore instead of local agent.
# Leave empty to use local Strands agent (default for local dev).
# AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/agent-XXXXX

# === Datos ===
DATA_DIR=../data
```

## `.env.example` (template para nuevos devs)

Mantener siempre actualizado. Copiar a `.env` y completar valores reales.

## Desarrollo local

### Frontend
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Comando de dev server depende del framework elegido en spec
```

### AgentCore (desarrollo local)
```bash
cd agentcore
pip install -r requirements.txt

# Iniciar dev server con hot reload
agentcore dev --env BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID

# Test local (en otra terminal)
agentcore invoke --dev '{"prompt": "¿Qué médicos tengo en Belgrano?"}'
```

### Requisitos previos
- Node.js 20+ y npm
- Python 3.12+
- AWS CLI configurado (`aws configure` o `AWS_PROFILE` en .env)
- Acceso a Bedrock habilitado (Console → Model access → habilitar Claude)
- Los CSVs de datos en el directorio `data/`
- `bedrock-agentcore-starter-toolkit` instalado (`pip install bedrock-agentcore-starter-toolkit`)

## Deploy con CDK (infraestructura)

### Setup
```bash
cd infrastructure
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Comandos CDK
```bash
source ../.env

# Ver cambios pendientes
cdk diff --profile $AWS_PROFILE

# Sintetizar template CloudFormation
cdk synth

# Deploy completo
cdk deploy --all --profile $AWS_PROFILE --region $AWS_REGION

# Deploy de un stack específico
cdk deploy PharmAssistStack --profile $AWS_PROFILE --region $AWS_REGION

# Destruir (con cuidado)
cdk destroy --all --profile $AWS_PROFILE --region $AWS_REGION
```

### Principios CDK
- Un solo stack (salvo que se excedan 500 recursos o multi-región)
- Tags automáticos via CDK Aspects (TAG_PROJECT, TAG_ENVIRONMENT, TAG_OWNER)
- Removal policies: DESTROY para dev, RETAIN para prod
- Outputs del stack exportan ARNs y nombres de tablas DynamoDB
- Usar los outputs del CDK como `-env` flags en agentcore deploy

### Recursos CDK esperados
- DynamoDB tables (médicos, visitas, ventas)
- Lambda functions (API, procesamiento)
- S3 bucket (frontend SPA)
- CloudFront distribution
- IAM roles con permisos mínimos

## Deploy de Agentes con AgentCore

### Flujo completo

```bash
source .env

# 1. Configurar el agente
cd agentcore
agentcore configure \
  -e agent.py \
  -ni \
  -r $AGENTCORE_REGION

# 2. Deploy a AWS (usar deploy, NO launch)
agentcore deploy -auc \
  -env BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID \
  -env AWS_REGION=$AWS_REGION \
  -env MEDICOS_TABLE_NAME=$MEDICOS_TABLE_NAME \
  -env VISITAS_TABLE_NAME=$VISITAS_TABLE_NAME \
  -env VENTAS_TABLE_NAME=$VENTAS_TABLE_NAME \
  -env PLANIFICADAS_TABLE_NAME=$PLANIFICADAS_TABLE_NAME \
  -env MINUTAS_TABLE_NAME=$MINUTAS_TABLE_NAME

# 3. Test en cloud
agentcore invoke '{"prompt": "¿Cuántos médicos tengo asignados?", "apm_id": "Demo APM"}'

# 4. Ver estado
agentcore status

# 5. Parar sesión activa
agentcore stop-session

# 6. Destruir (cuando ya no se necesite)
agentcore destroy --dry-run   # preview primero
agentcore destroy
```

### Notas importantes de AgentCore
- `agentcore` CLI NO soporta `--profile`. Usar `export AWS_PROFILE=...` antes
- `agentcore` CLI NO persiste env vars entre deploys. SIEMPRE incluir `-env` flags
- Omitir `-env` flags causa que el agente use valores por defecto incorrectos
- Default deployment usa `direct_code_deploy` (no requiere Docker)
- Región default es `us-west-2`, especificar con `-r` si se usa otra
- Configuración se guarda en `.bedrock_agentcore.yaml`
- Para desarrollo local: `agentcore dev` + `agentcore invoke --dev`
- Symlinks NO funcionan con `agentcore deploy` — usar copias de `backend/` en `agentcore/`
- Después de cambios en `backend/`, copiar archivos modificados a `agentcore/`
- El comando correcto es `agentcore deploy` (no `launch`)

### Wrapping del agente para AgentCore
El agente DEBE estar wrapeado con `BedrockAgentCoreApp`:
```python
from bedrock_agentcore import BedrockAgentCoreApp
app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload, context):
    # lógica del agente
    return {"result": "..."}

if __name__ == "__main__":
    app.run()
```

`requirements.txt` del agente DEBE incluir:
- `bedrock-agentcore`
- `strands-agents`
- `strands-agents-tools`
- Todas las demás dependencias

## Permisos AWS mínimos (IAM)

### Para el agente (AgentCore execution role)
- `bedrock:InvokeModel` — llamar a Claude via Strands
- `bedrock:InvokeModelWithResponseStream` — streaming
- `dynamodb:GetItem`, `dynamodb:Query`, `dynamodb:Scan` — leer datos
- `dynamodb:PutItem`, `dynamodb:UpdateItem` — escribir datos (si aplica)

### Para Lambda functions
- `dynamodb:*` sobre las tablas del proyecto
- `bedrock:InvokeModel` (si Lambda llama a Bedrock directamente)
- `s3:GetObject` (si lee CSVs de S3)

### Para CDK deploy
- `cloudformation:*`, `iam:*`, `lambda:*`, `dynamodb:*`, `s3:*`, `cloudfront:*`
- O usar `AdministratorAccess` para dev (no para prod)

## Variables de entorno — Referencia completa

| Variable | Dónde se usa | Ejemplo |
|----------|-------------|---------|
| `AWS_PROFILE` | CDK, AWS CLI, AgentCore (via export) | `my-profile` |
| `AWS_REGION` | CDK, AgentCore, backend | `us-east-1` |
| `AWS_ACCOUNT_ID` | CDK (env) | `123456789012` |
| `BEDROCK_MODEL_ID` | Agentes Strands, AgentCore | `us.anthropic.claude-opus-4-6-v1` |
| `TAG_PROJECT` | CDK Aspects | `PharmAssist` |
| `TAG_ENVIRONMENT` | CDK Aspects | `dev` |
| `TAG_OWNER` | CDK Aspects | `your-team` |
| `VITE_API_URL` | Frontend (Vite) | `http://localhost:8000` |
| `AGENTCORE_AGENT_NAME` | AgentCore CLI | `pharmassist-agent` |
| `AGENTCORE_AGENT_ARN` | Backend (FastAPI proxy) | `arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/agent-XXXXX` |
| `AGENTCORE_REGION` | Backend, AgentCore CLI | `us-east-1` |
| `DATA_DIR` | Backend, scripts de carga | `.` |
| `MEDICOS_TABLE_NAME` | Agente, Lambda | CDK output |
| `VISITAS_TABLE_NAME` | Agente, Lambda | CDK output |
| `VENTAS_TABLE_NAME` | Agente, Lambda | CDK output |
| `PLANIFICADAS_TABLE_NAME` | Agente, Lambda | CDK output |
| `MINUTAS_TABLE_NAME` | Agente, Lambda | CDK output |
| `API_URL` | Scripts, referencia | CDK output (API Gateway URL) |
| `RDS_SECRET_ARN` | IngestionStack (CDK) | `arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:xxx` |
| `DATASOURCES_VPC_ID` | IngestionStack (CDK) | `vpc-xxxxxxxxx` |
| `LAKE_BUCKET_NAME` | IngestionStack (CDK), Glue ETL | `datalakestack-lakebucket9cd7bbd2-xxx` |
| `GLUE_DB_CRM` | IngestionStack (CDK) | `pharmassist_crm` |
| `GLUE_DB_CUP` | IngestionStack (CDK) | `pharmassist_cup` |
| `GLUE_DB_IQVIA` | IngestionStack (CDK) | `pharmassist_iqvia` |
| `GLUE_DB_MAESTROS` | IngestionStack (CDK) | `pharmassist_maestros` |
| `INGESTION_STATE_MACHINE_ARN` | Scripts, referencia | CDK output (Step Functions ARN) |
| `INGESTION_GLUE_JOB_NAME` | Scripts, referencia | `pharmassist-parquet-to-iceberg` |
| `INGESTION_SCHEDULE_ARN` | Scripts, referencia | CDK output (EventBridge Schedule ARN) |

## Build para producción

### Frontend
```bash
cd frontend
npm run build        # genera dist/
# Subir dist/ a S3 bucket del CDK
```

### Backend / Agentes
Deploy via CDK (Lambda) y AgentCore (agentes).

## Testing

### Estrategia (remocal testing)
- **Unit tests**: Lógica pura con mocks (<1s)
- **Integration tests**: Código local contra servicios AWS reales (1-5s)
- **CDK tests**: Assertions sobre el template CloudFormation generado

```bash
# Frontend
cd frontend && npm run test

# Backend
cd backend && pytest

# CDK
cd infrastructure && pytest
```
