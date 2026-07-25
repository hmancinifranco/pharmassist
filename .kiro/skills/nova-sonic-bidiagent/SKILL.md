---
name: nova-sonic-bidiagent
description: Guía de implementación de voice-to-voice con Nova Sonic y BidiAgent de Strands desplegado en AgentCore (WebSocket, container deployment, SigV4). Usar cuando se trabaje en el modo voz de PharmAssist, agentcore/agent.py con BidiAgent, o el frontend de voz (VoiceOverlay, websocket.ts).
metadata:
  category: development
  complexity: advanced
---

# Nova Sonic + BidiAgent en AgentCore — Guía de Implementación

Aprendizajes de la migración voice-to-voice de PharmAssist. Referencia para futuras implementaciones con Nova Sonic bidireccional.

## Arquitectura

```
Browser (React) → WSS + SigV4 presigned URL → AgentCore Runtime → Container (FastAPI + BidiAgent) → Nova Sonic
```

- El browser se conecta directo a AgentCore via WebSocket con credenciales temporales de Cognito Identity Pool
- No hay servidor intermedio (no Lambda, no ECS, no proxy)
- AgentCore rutea la conexión WebSocket al container que corre FastAPI + uvicorn
- El BidiAgent de Strands maneja el protocolo Nova Sonic internamente

## Reglas Críticas

### 1. Usar FastAPI puro, NO BedrockAgentCoreApp

`BedrockAgentCoreApp` con `@app.websocket` tiene conflictos de event loop con `awscrt` (la librería CRT que Nova Sonic usa para HTTP/2 streaming). Esto causa `InvalidStateError: CANCELLED` en futures.

```python
# ❌ NO funciona con Nova Sonic
from bedrock_agentcore import BedrockAgentCoreApp
app = BedrockAgentCoreApp()

@app.websocket
async def handler(websocket, context):
    ...

# ✅ SÍ funciona — FastAPI puro (como el sample oficial de AWS)
from fastapi import FastAPI, WebSocket
app = FastAPI()

@app.websocket("/ws")
async def voice_chat(websocket: WebSocket):
    ...
```

### 2. Container deployment, NO direct_code_deploy

El runtime managed de AgentCore (Python 3.13) tiene incompatibilidades con `awscrt`. Container deployment te da control del entorno.

```bash
agentcore configure -e agent.py -ni -r us-east-1 -dt container
agentcore deploy -auc -env KEY=VALUE
```

- Dockerfile debe usar `public.ecr.aws/docker/library/python:3.12-slim` (evita Docker Hub rate limits en CodeBuild)
- Exponer puerto 8080, CMD con `uvicorn agent:app --host 0.0.0.0 --port 8080`
- Endpoint health check en `GET /ping` (requerido por AgentCore)
- Endpoint WebSocket en `/ws` (donde AgentCore rutea las conexiones)

### 3. No se puede cambiar artifact type de un agente existente

Si un agente fue creado con `direct_code_deploy`, no se puede cambiar a `container`. Hay que crear un agente nuevo con nombre diferente.

### 4. El BidiAgent maneja el protocolo Nova Sonic internamente

El frontend NO debe mandar eventos de protocolo Nova Sonic (sessionStart, promptStart, contentStart, audioInput, etc.). El BidiAgent de Strands se encarga de todo eso.

El frontend solo manda audio crudo y recibe audio + transcripciones.

### 5. Formato de eventos del frontend

**Enviar audio al BidiAgent:**
```json
{
  "type": "bidi_audio_input",
  "audio": "<base64 PCM 16kHz mono Int16>",
  "format": "pcm",
  "sample_rate": 16000,
  "channels": 1
}
```

**Recibir del BidiAgent:**
- `{type: "bidi_audio_stream", audio: "<base64>", format: "pcm", sample_rate: 16000}` — audio de respuesta
- `{type: "bidi_transcript_stream", text: "...", role: "user"|"assistant", is_final: bool}` — transcripciones
- `{type: "bidi_text_response", text: "..."}` — respuesta final de texto
- `{type: "bidi_interruption", reason: "..."}` — barge-in detectado

### 6. Presigned URL — formato correcto

```typescript
const encodedArn = encodeURIComponent(agentArn); // ARN completo URL-encoded
const path = `/runtimes/${encodedArn}/ws`;
const query = {
  qualifier: 'DEFAULT',
  'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': crypto.randomUUID(),
};
// Firmar con protocol: 'https:' y luego convertir a wss://
```

- Firmar con `protocol: 'https:'` (no `wss:`), luego reemplazar a `wss://` en la URL final
- Incluir `qualifier=DEFAULT` en los query params antes de firmar
- Incluir `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` con un UUID

### 7. IAM permissions para WebSocket

El rol del Cognito Identity Pool necesita:
```
bedrock-agentcore:InvokeAgentRuntime
bedrock-agentcore:InvokeAgentRuntimeWithWebSocketStream
```

### 8. Model ID

Nova Sonic 2: `amazon.nova-2-sonic-v1:0` (no `amazon.nova-sonic-v1:0`)

## Configuración del BidiAgent (Python)

```python
from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.models import BidiNovaSonicModel

sonic_model = BidiNovaSonicModel(
    model_id="amazon.nova-2-sonic-v1:0",
    provider_config={
        "audio": {
            "voice": "lupe",        # español femenino
            "input_rate": 16000,
            "output_rate": 16000,
            "channels": 1,
            "format": "pcm",
        },
        "inference": {},
    },
    client_config={"region": "us-east-1"},
)

# En el WebSocket handler:
voice_agent = BidiAgent(
    model=sonic_model,
    tools=[mi_tool],
    system_prompt="...",
)
await voice_agent.run(
    inputs=[websocket.receive_json],   # FastAPI WebSocket
    outputs=[websocket.send_json],
)
```

## Dependencias

**BidiAgent (requirements.txt):**
```
strands-agents[bidi]
strands-agents-tools
boto3
fastapi
uvicorn[standard]
```

**Frontend (package.json):**
```
@aws-sdk/client-cognito-identity
@aws-crypto/sha256-js
@aws-sdk/signature-v4    (o @smithy/signature-v4)
@smithy/protocol-http
```

## Referencia

- Sample oficial: https://github.com/aws-samples/sample-nova-sonic-websocket-agentcore
- Doc WebSocket AgentCore: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-websocket.html
- Strands BidiAgent quickstart: https://strandsagents.com/docs/user-guide/concepts/bidirectional-streaming/quickstart/
