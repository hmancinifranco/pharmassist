# Plan de Implementación: Migración Voice a BidiAgent + WebSocket Directo

## Resumen

Migrar el modo voz de PharmAssist desde ECS Fargate + Socket.IO hacia BidiAgent + WebSocket directo a AgentCore con SigV4. La implementación es incremental: primero infraestructura CDK, luego BidiAgent Python, después frontend TypeScript, y finalmente limpieza de recursos legacy.

## Tareas

- [x] 1. Agregar Cognito Identity Pool al CDK Stack
  - [x] 1.1 Crear Identity Pool con User Pool como proveedor en `infrastructure/stacks/pharmassist_stack.py`
    - Agregar `CfnIdentityPool` con `allow_unauthenticated_identities=False`
    - Configurar `cognito_identity_providers` con el `app_client` y `user_pool` existentes
    - Crear rol IAM autenticado con `sts:AssumeRoleWithWebIdentity` federado a Cognito Identity
    - Agregar policy `bedrock-agentcore:InvokeAgentRuntime` con resource scoped al ARN del runtime
    - Crear `CfnIdentityPoolRoleAttachment` para vincular el rol
    - Agregar stack outputs: `IdentityPoolId`, `UserPoolId`, `UserPoolClientId`
    - _Requerimientos: 1.1, 1.2, 1.3, 1.4, 10.1, 10.2, 10.5_

  - [ ]* 1.2 Escribir tests CDK para el Identity Pool
    - Verificar que Identity Pool existe con User Pool como provider
    - Verificar que `AllowUnauthenticatedIdentities` es `False`
    - Verificar que el rol autenticado tiene solo `InvokeAgentRuntime`
    - Verificar que el rol NO tiene permisos DynamoDB/S3/Lambda
    - Verificar que existen outputs `IdentityPoolId` y `UserPoolId`
    - _Requerimientos: 1.1, 1.2, 1.3, 10.1, 10.2_

- [x] 2. Eliminar infraestructura ECS Fargate del CDK Stack
  - [x] 2.1 Remover bloque ECS del `pharmassist_stack.py`
    - Eliminar el bloque condicional `if os.environ.get("DEPLOY_VOICE_SERVER")` completo (~100 líneas)
    - Eliminar la variable `voice_alb_dns`
    - Eliminar imports no usados: `aws_ecs`, `aws_ec2`, `aws_elasticloadbalancingv2`, `aws_ecr_assets` (si ya no se usan)
    - Eliminar output `VoiceServerUrl` si existe
    - _Requerimientos: 6.1, 6.2, 6.3_

  - [ ]* 2.2 Escribir tests CDK para verificar ausencia de recursos ECS
    - Verificar que no existen recursos `AWS::ECS::Cluster`, `AWS::ECS::Service`, `AWS::ECS::TaskDefinition`
    - Verificar que no existe `AWS::ElasticLoadBalancingV2::LoadBalancer`
    - Verificar que no existe output `VoiceServerUrl`
    - _Requerimientos: 6.1, 6.2, 6.3_

- [x] 3. Checkpoint — Verificar CDK Stack
  - Ejecutar `cdk synth` para verificar que el template se genera sin errores. Asegurar que todos los tests pasan, preguntar al usuario si surgen dudas.

- [x] 4. Crear BidiAgent Python
  - [x] 4.1 Crear estructura del directorio `bidiagent/` con archivos base
    - Crear `bidiagent/agent.py` con el entrypoint `BedrockAgentCoreApp` + `BidiAgent`
    - Configurar Nova Sonic con voz `lupe`, audio input PCM 16kHz mono, audio output PCM 24kHz mono
    - Incluir system prompt en español argentino (conciso, 2-3 oraciones, sin markdown/tablas/emojis)
    - Configurar `inference_config` con `maxTokens: 1024`, `topP: 0.9`, `temperature: 0.7`
    - Crear `bidiagent/requirements.txt` con `bedrock-agentcore`, `strands-agents`, `strands-agents-tools`, `boto3`
    - Crear `bidiagent/Dockerfile` basado en `python:3.12-slim`, instalar deps, exponer entrypoint
    - _Requerimientos: 2.1, 2.4, 2.5, 2.8, 3.1, 3.2, 3.3_

  - [x] 4.2 Implementar tool `consultarAsistente` en `bidiagent/agent.py`
    - Crear tool con `@tool` decorator que reciba `pregunta: str`
    - Construir payload JSON con campos `prompt`, `apm_id`, `mode: "voice"`
    - Invocar Text Agent via `bedrock-agent-runtime` client con el ARN de `TEXT_AGENT_ARN`
    - Validar que `apm_id` no sea vacío ni solo whitespace antes de invocar
    - Retornar mensaje de error amigable si la invocación falla o si `apm_id` es inválido
    - Leer `TEXT_AGENT_ARN`, `BEDROCK_MODEL_ID`, `AWS_REGION` de variables de entorno
    - _Requerimientos: 2.2, 2.3, 2.7, 3.4, 3.5, 10.4_

  - [ ]* 4.3 Escribir property test para construcción de payload de `consultarAsistente`
    - **Property 3: consultarAsistente payload construction**
    - Para cualquier string de pregunta no vacía y apm_id válido, el payload debe ser JSON con exactamente `prompt`, `apm_id`, `mode: "voice"`
    - Usar `hypothesis` con `st.text(min_size=1)` para pregunta y apm_id
    - **Valida: Requerimientos 2.3**

  - [ ]* 4.4 Escribir property test para validación de apm_id
    - **Property 8: apm_id validation before Text Agent invocation**
    - Si apm_id es vacío o solo whitespace, no debe invocar Text Agent y debe retornar error
    - Si apm_id tiene al menos un carácter no-whitespace, debe proceder con invocación
    - Usar `hypothesis` con `st.text()` incluyendo vacíos y whitespace
    - **Valida: Requerimientos 10.4**

- [x] 5. Checkpoint — Verificar BidiAgent
  - Asegurar que todos los tests del BidiAgent pasan. Verificar que `bidiagent/agent.py` se ejecuta sin errores de import. Preguntar al usuario si surgen dudas.

- [x] 6. Crear módulo de credenciales AWS en el frontend
  - [x] 6.1 Crear `frontend/src/api/credentials.ts`
    - Implementar función `getAwsCredentials(idToken: string)` que intercambie JWT por credenciales AWS temporales
    - Usar `@aws-sdk/client-cognito-identity` con `GetIdCommand` y `GetCredentialsForIdentityCommand`
    - Implementar cache de credenciales con renovación automática (margen de 5 minutos antes de expiración)
    - Leer `VITE_IDENTITY_POOL_ID`, `VITE_USER_POOL_ID`, `VITE_AWS_REGION` de variables de entorno Vite
    - Exportar `clearCredentialsCache()` para limpiar cache al logout
    - Retornar interfaz `AwsCredentials` con `accessKeyId`, `secretAccessKey`, `sessionToken`, `expiration`
    - _Requerimientos: 1.5, 1.6, 1.7, 9.3, 10.6_

  - [ ]* 6.2 Escribir property test para decisión de cache de credenciales
    - **Property 2: Credential cache expiry decision**
    - Para cualquier par de timestamps (expiración, ahora), usar cache si diferencia > 5 min, renovar si ≤ 5 min
    - Usar `fast-check` con `fc.date()` para generar pares de fechas
    - **Valida: Requerimientos 1.6**

- [x] 7. Reescribir VoiceService con WebSocket SigV4
  - [x] 7.1 Implementar generación de Presigned WebSocket URL en `frontend/src/api/voice.ts`
    - Agregar función `generatePresignedUrl(credentials, region, agentArn)` usando `@smithy/signature-v4` y `@aws-crypto/sha256-js`
    - Firmar request con servicio `bedrock-agentcore`, método GET, protocolo `wss:`
    - Configurar expiración de URL en 300 segundos (5 minutos)
    - Extraer `agentId` del ARN del BidiAgent para construir el path
    - _Requerimientos: 4.2, 10.3_

  - [ ]* 7.2 Escribir property test para formato de Presigned URL
    - **Property 4: Presigned WebSocket URL format**
    - Para cualquier conjunto de credenciales y ARN válido, la URL debe comenzar con `wss://`, contener host correcto, path con agentId, y query params SigV4
    - Usar `fast-check` con generadores de strings para credentials
    - **Valida: Requerimientos 4.2**

  - [x] 7.3 Reescribir clase `VoiceService` en `frontend/src/api/voice.ts`
    - Reemplazar Socket.IO por WebSocket nativo con URL presignada SigV4
    - Mantener interfaz pública compatible: `constructor(idToken, apmId, callbacks)`, `connect()`, `setMuted()`, `disconnect()`
    - Implementar flujo de conexión: obtener credenciales → generar URL presignada → conectar WebSocket
    - Enviar eventos de protocolo en orden: `sessionStart` → `promptStart` (con toolConfiguration) → `contentStart` (system prompt) → `textInput` → `contentEnd` → `contentStart` (audio) → `audioInput` chunks
    - Recibir y despachar eventos: `audioOutput` → reproducir, `textOutput` → transcripción, `toolUse` → thinking, `contentEnd` → listening
    - Mantener captura de micrófono PCM 16kHz mono con `ScriptProcessorNode`
    - Mantener reproducción de audio PCM 24kHz con `AudioContext` + `BufferSource`
    - Implementar barge-in: detener playback cuando el usuario habla
    - Pasar `apm_id` del JWT como parte del contexto de sesión
    - _Requerimientos: 4.1, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 7.4 Escribir property test para mapeo evento-a-estado-UI
    - **Property 5: Event-to-UI-state mapping**
    - Para cualquier evento de respuesta del BidiAgent, el mapeo a estado UI debe ser determinístico
    - `contentStart` ASSISTANT AUDIO → `speaking`, `textOutput` USER → `listening`, `toolUse` → `thinking`, etc.
    - Usar `fast-check` con `fc.oneof()` para tipos de evento
    - **Valida: Requerimientos 5.5**

  - [ ]* 7.5 Escribir property test para serialización JSON de eventos WebSocket
    - **Property 7: WebSocket event JSON serialization**
    - Para cualquier evento válido del protocolo, la serialización debe producir un objeto con exactamente una key `"event"` cuyo valor tiene exactamente una key del tipo de evento
    - Usar `fast-check` con generadores de eventos
    - **Valida: Requerimientos 5.1**

- [x] 8. Implementar manejo de errores y reconexión en VoiceService
  - [x] 8.1 Agregar reconexión con backoff exponencial y manejo de errores
    - Implementar backoff exponencial: 1s, 2s, 4s (máximo 3 intentos)
    - Si reconexión falla después de 3 intentos, cerrar overlay y notificar error
    - Manejar error de micrófono: mostrar "Se necesita acceso al micrófono para el modo voz."
    - Manejar error de credenciales: mostrar "No se pudieron obtener credenciales para el modo voz. Intentá reloguearte." y deshabilitar botón
    - Manejar error de Nova Sonic: mostrar "El asistente de voz no está disponible." y ofrecer chat texto
    - Manejar timeout de 8 minutos: mostrar "La sesión de voz expiró. Podés iniciar una nueva." con opción de reconectar
    - Renovar credenciales automáticamente si expiran durante sesión activa
    - Asegurar que errores en modo voz NO afectan chat de texto ni dashboard
    - _Requerimientos: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.5_

  - [ ]* 8.2 Escribir property test para delay de backoff exponencial
    - **Property 6: Backoff exponential delay**
    - Para cualquier intento N (1-3), delay = 1000 * 2^(N-1) ms. Para N > 3, no reintentar
    - Usar `fast-check` con `fc.integer({min: 1, max: 5})`
    - **Valida: Requerimientos 7.5**

- [x] 9. Actualizar VoiceOverlay y dependencias del frontend
  - [x] 9.1 Actualizar `VoiceOverlay.tsx` para usar el nuevo `VoiceService`
    - Ajustar la instanciación de `VoiceService` con los nuevos parámetros (`idToken`, `apmId`, callbacks)
    - Obtener `idToken` y `apmId` del auth store existente
    - Mantener la interfaz visual sin cambios (ParticleSphere, botones, estados)
    - _Requerimientos: 4.5, 8.5_

  - [x] 9.2 Instalar nuevas dependencias y eliminar `socket.io-client`
    - Instalar: `@aws-sdk/client-cognito-identity`, `@aws-crypto/sha256-js`, `@smithy/signature-v4`
    - Eliminar: `socket.io-client`
    - _Requerimientos: 6.4_

  - [ ]* 9.3 Escribir property test para round-trip de audio PCM
    - **Property 1: Audio PCM encoding round-trip**
    - Para cualquier array Float32 en [-1.0, 1.0], convertir a Int16 y volver debe tener diferencia < 1/32768
    - Para cualquier array Int16, codificar a base64 y decodificar debe producir el array original
    - Usar `fast-check` con `fc.float({min: -1, max: 1})`
    - **Valida: Requerimientos 4.3, 4.4**

- [x] 10. Actualizar variables de entorno y configuración
  - [x] 10.1 Actualizar `.env.example` y variables de entorno Vite
    - Agregar a `.env.example`: `BIDIAGENT_AGENT_ARN`, `IDENTITY_POOL_ID` con comentarios descriptivos
    - Agregar variables Vite al frontend: `VITE_IDENTITY_POOL_ID`, `VITE_BIDIAGENT_AGENT_ARN`, `VITE_USER_POOL_ID`, `VITE_AWS_REGION`
    - Eliminar `VITE_VOICE_URL` del frontend
    - Verificar que no hay valores sensibles hardcodeados en el código fuente
    - _Requerimientos: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 6.5_

- [x] 11. Checkpoint — Verificar integración completa
  - Asegurar que todos los tests pasan (CDK, BidiAgent, frontend). Verificar que `npm run build` compila sin errores. Preguntar al usuario si surgen dudas.

- [x] 12. Marcar voice-server como deprecado
  - [x] 12.1 Agregar README de deprecación en `voice-server/`
    - Crear o actualizar `voice-server/README.md` indicando que el directorio está deprecado
    - Indicar que fue reemplazado por `bidiagent/` + WebSocket directo a AgentCore
    - _Requerimientos: 6.6_

- [x] 13. Checkpoint final — Verificación completa
  - Asegurar que todos los tests pasan. Verificar que el chat de texto, dashboard y funcionalidades existentes no fueron afectados. Preguntar al usuario si surgen dudas.
  - _Requerimientos: 8.1, 8.2, 8.3, 8.4, 8.6_

- [x] 14. Deploy a AWS
  - [x] 14.1 Deploy CDK Stack (Identity Pool + eliminación ECS)
    - Ejecutar `cdk deploy PharmAssistStack` con el Identity Pool nuevo y sin recursos ECS
    - Anotar outputs: `IdentityPoolId`, `UserPoolId`, `UserPoolClientId`
    - Actualizar `.env` con los nuevos valores
    - _Requerimientos: 1.4, 6.7, 9.1_

  - [x] 14.2 Deploy BidiAgent a AgentCore con container deployment
    - Ejecutar `agentcore configure` con entrypoint `agent.py`, protocolo WebSocket, container deployment
    - Ejecutar `agentcore deploy` con `-env TEXT_AGENT_ARN`, `-env BEDROCK_MODEL_ID`, `-env AWS_REGION`
    - Anotar el ARN del BidiAgent y actualizar `.env` con `BIDIAGENT_AGENT_ARN`
    - Verificar que el BidiAgent está en estado `READY` con `agentcore status`
    - _Requerimientos: 3.1, 3.2, 3.4, 3.6_

  - [x] 14.3 Deploy frontend con nuevas env vars
    - Ejecutar `scripts/deploy-frontend.sh` con `VITE_IDENTITY_POOL_ID` y `VITE_BIDIAGENT_AGENT_ARN` configurados
    - Verificar que el build compila sin errores
    - _Requerimientos: 9.3_

- [x] 15. Verificación end-to-end
  - [x] 15.1 Verificar modo voz desde localhost
    - Ejecutar `npm run dev` en el frontend
    - Activar modo voz, hablar, verificar que Nova Sonic responde con audio
    - Verificar que `consultarAsistente` delega al Text Agent (preguntar por médicos/visitas)
    - Verificar barge-in (interrumpir al asistente hablando)
    - _Requerimientos: 2.6, 4.3, 4.4, 5.5_

  - [x] 15.2 Verificar modo voz desde CloudFront (HTTPS)
    - Abrir la URL de CloudFront del stack (ver output `CloudFrontDomain`)
    - Activar modo voz, verificar que WSS + SigV4 conecta sin error de mixed content
    - Hablar y verificar respuesta de audio
    - _Requerimientos: 4.1, 4.2_

  - [x] 15.3 Verificar que funcionalidades existentes no se rompieron
    - Verificar login con Cognito
    - Verificar dashboard (tarjetas de visitas, cumpleaños, SLA)
    - Verificar chat de texto via WebSocket streaming
    - Verificar minuta rápida (grabar + transcribir directo)
    - _Requerimientos: 8.1, 8.2, 8.3, 8.4, 8.6_

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requerimientos específicos para trazabilidad
- Los checkpoints aseguran validación incremental
- Los property tests validan propiedades universales de correctitud definidas en el diseño
- Los unit tests validan ejemplos específicos y edge cases
- El agente de texto existente y el chat NO se modifican en ningún paso
