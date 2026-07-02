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


## IAM Execution Role

El archivo `iam-policy.json` documenta todos los permisos que necesita el execution role
del Unified Agent desplegado en AgentCore.

### Permisos incluidos

| Sid | Servicio | Propósito |
|-----|----------|-----------|
| BedrockModelInvocation | Bedrock | InvokeModel + streaming para Claude |
| DynamoDBMinutasAccess | DynamoDB | Lectura de tabla de minutas (GetItem, Query, Scan) |
| SecretsManagerDBCredentials | Secrets Manager | Obtener credenciales de Aurora PostgreSQL |
| AgentCoreMemoryReadWrite | AgentCore Memory | STM y Semantic Memory (create events, list, retrieve) |
| VPCNetworkInterfaceManagement | EC2 | Crear/eliminar ENIs para VPC mode |
| CloudWatchLogsAndMetrics | CloudWatch Logs | Logging del runtime |

### Cómo se aplica el rol

`agentcore deploy` con flag `-auc` (auto-update-configuration) crea y actualiza el
execution role automáticamente con permisos básicos (Bedrock, CloudWatch). Sin embargo,
permisos adicionales como VPC ENI, DynamoDB, Secrets Manager y AgentCore Memory
**deben agregarse manualmente** al rol creado por `agentcore deploy`.

#### Opción A: Agregar permisos al rol auto-creado (recomendado para dev)

1. Hacer `agentcore deploy -auc` (crea el rol con permisos base)
2. Ir a IAM Console → buscar el rol `AgentCoreExecutionRole-<agent-name>-*`
3. Adjuntar una inline policy con el contenido de `iam-policy.json`
4. Reemplazar `${MINUTAS_TABLE_NAME}` y `${DB_SECRET_ARN}` con los valores reales

#### Opción B: Pre-crear el rol (recomendado para prod)

1. Crear un rol IAM con trust policy para `bedrock-agentcore.amazonaws.com`
2. Adjuntar la policy de `iam-policy.json` con ARNs reales
3. Pasar el ARN del rol al deploy: `agentcore deploy -auc -r us-east-1 --role-arn <ARN>`

### Variables a reemplazar en producción

| Placeholder | Valor real | Fuente |
|-------------|------------|--------|
| `${MINUTAS_TABLE_NAME}` | Nombre de la tabla DynamoDB de minutas | CDK Output / `.env` |
| `${DB_SECRET_ARN}` | ARN del secret con credenciales Aurora | ProduccionPocStack Output / `.env` |

### Trust Policy del rol

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "bedrock-agentcore.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```
