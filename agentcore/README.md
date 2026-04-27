# PharmAssist — AgentCore Deployment

Paquete de deploy del agente Strands para Amazon Bedrock AgentCore.

## Endpoint

Al hacer deploy con `agentcore deploy`, el CLI emite un ARN con el formato:

```
arn:aws:bedrock-agentcore:<region>:<account-id>:runtime/<agent-id>
```

Copiar ese ARN al `.env` como `AGENTCORE_AGENT_ARN`.

- **Region**: `us-east-1` (configurable via `AGENTCORE_REGION`)
- **Deployment Type**: Direct Code Deploy (Python 3.13)
- **GenAI Dashboard**: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#gen-ai-observability/agent-core

## Estructura

```
agentcore/
├── agent.py              # Entrypoint (BedrockAgentCoreApp wrapper)
├── requirements.txt      # Dependencias del agente
├── .bedrock_agentcore.yaml  # Config generada por agentcore configure
├── agents/               # Copia del módulo del agente (fuente: backend/agents)
├── tools/                # Copia de los tools Strands (fuente: backend/tools)
├── models/               # Copia de los modelos Pydantic (fuente: backend/models)
├── data/                 # Copia de datos de referencia (fuente: backend/data)
└── utils/                # Copia de utilidades (fuente: backend/utils)
```

Los módulos son copias de `backend/` con imports dual-path (try backend.X / except X)
para funcionar tanto en desarrollo local como en el runtime de AgentCore.

## Payload

```json
{
  "prompt": "¿Cuáles son mis visitas de hoy?",
  "apm_id": "Demo APM"
}
```

## Desarrollo local

```bash
cd agentcore
pip install -r requirements.txt

# Dev server con hot reload
agentcore dev -env BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID \
              -env AWS_REGION=$AWS_REGION \
              -env MEDICOS_TABLE_NAME=$MEDICOS_TABLE_NAME \
              -env VISITAS_TABLE_NAME=$VISITAS_TABLE_NAME \
              -env VENTAS_TABLE_NAME=$VENTAS_TABLE_NAME \
              -env PLANIFICADAS_TABLE_NAME=$PLANIFICADAS_TABLE_NAME \
              -env MINUTAS_TABLE_NAME=$MINUTAS_TABLE_NAME

# Test local (en otra terminal)
agentcore invoke --dev '{"prompt": "¿Cuántos médicos tengo?", "apm_id": "Demo APM"}'
```

## Deploy a AWS

```bash
source ../.env
export AWS_PROFILE=$AWS_PROFILE   # agentcore CLI no soporta --profile

# 1. Configurar
agentcore configure \
  -e agent.py \
  -ni \
  -r $AGENTCORE_REGION

# 2. Deploy (SIEMPRE incluir -env con nombres de tablas del CDK output)
agentcore deploy -auc \
  -env BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID \
  -env AWS_REGION=$AWS_REGION \
  -env MEDICOS_TABLE_NAME=$MEDICOS_TABLE_NAME \
  -env VISITAS_TABLE_NAME=$VISITAS_TABLE_NAME \
  -env VENTAS_TABLE_NAME=$VENTAS_TABLE_NAME \
  -env PLANIFICADAS_TABLE_NAME=$PLANIFICADAS_TABLE_NAME \
  -env MINUTAS_TABLE_NAME=$MINUTAS_TABLE_NAME

# 3. Test en cloud
agentcore invoke '{"prompt": "¿Qué médicos tengo en Belgrano?", "apm_id": "Demo APM"}'

# 4. Ver estado
agentcore status
```

## Notas

- `agentcore` CLI NO persiste env vars entre deploys — siempre incluir `-env`
- Omitir `-env` = el agente usa defaults que no coinciden con tus tablas
- Región default de AgentCore es `us-west-2`, especificar con `-r` si usás otra
- Requiere `bedrock-agentcore-starter-toolkit` instalado
- Requiere acceso al modelo habilitado en Bedrock Console → Model access
- Los módulos en agentcore/ son copias (no symlinks) porque el deploy no resuelve symlinks
- Después de cambios en `backend/`, copiar los archivos modificados a `agentcore/`
