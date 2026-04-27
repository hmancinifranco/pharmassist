# Documento de Requerimientos — Migración Voice a BidiAgent + WebSocket Directo

## Introducción

PharmAssist tiene un modo voz (voice-to-voice) que permite al APM hablar con el asistente usando Amazon Nova Sonic. La arquitectura actual presenta tres problemas críticos:

1. **Mixed Content (HTTPS/HTTP)**: El frontend está en HTTPS (CloudFront) pero el voice server ECS Fargate usa un ALB HTTP. Los browsers bloquean conexiones `ws://` desde páginas HTTPS, haciendo que el modo voz no funcione en producción.
2. **Alta latencia y audio entrecortado**: La cadena Frontend → Socket.IO → ECS Fargate (Node.js) → Nova Sonic → AgentCore agrega latencia innecesaria. El servidor intermedio introduce buffering y overhead de protocolo Socket.IO.
3. **Infraestructura costosa**: ECS Fargate requiere VPC con NAT Gateway (~$32/mes solo el NAT), ALB, cluster ECS, y un servicio Node.js dedicado. Todo esto para hacer de proxy entre el browser y Nova Sonic.

### Solución: BidiAgent + WebSocket Directo a AgentCore

Basado en el patrón de [sample-nova-sonic-websocket-agentcore](https://github.com/aws-samples/sample-nova-sonic-websocket-agentcore):

- El frontend se conecta directamente a AgentCore via WebSocket con firma SigV4
- AgentCore ejecuta un **Strands BidiAgent** que maneja Nova Sonic bidireccionalmente de forma interna
- Cognito Identity Pool vende credenciales AWS temporales al browser para firmar las requests SigV4
- Se elimina completamente el servidor intermedio (ECS, Socket.IO, Node.js, VPC, NAT, ALB)
- Funciona desde CloudFront HTTPS porque WebSocket a AgentCore usa WSS con SigV4

### Arquitectura Objetivo

```
Frontend (React)
    │
    ├── WSS + SigV4 ──→ AgentCore (BidiAgent) ──→ Nova Sonic (bidireccional)
    │                         │                         │
    │                         │                    consultarAsistente tool
    │                         │                         │
    │                         │                    AgentCore (Text Agent existente)
    │                         │                         │
    │                         │                    15 Strands tools (DynamoDB, web search, etc.)
    │
    └── Cognito User Pool (JWT) → Cognito Identity Pool (AWS credentials temporales)
```

### Coexistencia de Agentes

- **Agente de texto** (existente): `direct_code_deploy`, protocolo HTTP, invocado via Lambda Proxy + WebSocket API Gateway para chat
- **BidiAgent de voz** (nuevo): `container` deployment, protocolo WebSocket, invocado directamente desde el browser via SigV4

Ambos agentes son independientes en AgentCore. El BidiAgent delega consultas de datos al agente de texto via el tool `consultarAsistente`.

## Glosario

- **BidiAgent**: Agente Strands que usa la clase `BidiAgent` del SDK para manejar streaming bidireccional de audio con Nova Sonic. Se despliega en AgentCore con deployment type `container` y protocolo WebSocket.
- **Cognito_Identity_Pool**: Amazon Cognito Identity Pool que intercambia un JWT del Cognito_User_Pool por credenciales AWS temporales (access key, secret key, session token) con permisos limitados.
- **SigV4**: AWS Signature Version 4, protocolo de firma que autentica requests HTTP/WebSocket a servicios AWS usando credenciales temporales.
- **Presigned_WebSocket_URL**: URL de WebSocket firmada con SigV4 que permite al browser conectarse directamente a AgentCore sin exponer credenciales en el código.
- **AgentCore_Runtime**: Servicio gestionado de Amazon Bedrock AgentCore que ejecuta agentes Strands con observabilidad, STM memory y gestión de sesiones.
- **Nova_Sonic**: Amazon Nova Sonic (`amazon.nova-sonic-v1:0`), modelo de speech-to-speech bidireccional que procesa audio de entrada y genera audio de respuesta en tiempo real.
- **Cognito_User_Pool**: Amazon Cognito User Pool existente (`PharmAssistUsers`) que gestiona la autenticación de APMs con email y atributo `custom:apm_id`.
- **CDK_Stack**: Stack de AWS CDK (`PharmAssistStack`) que define toda la infraestructura.
- **Text_Agent**: Agente Strands existente desplegado en AgentCore con `direct_code_deploy` y protocolo HTTP, que ejecuta los 15 tools de PharmAssist (médicos, visitas, ventas, minutas, web search).
- **APM**: Agente de Propaganda Médica, usuario principal de PharmAssist.
- **ECS_Voice_Server**: Servidor Node.js actual desplegado en ECS Fargate que maneja Socket.IO y Nova Sonic. Será eliminado en esta migración.
- **Container_Deployment**: Tipo de deployment de AgentCore que usa Docker container en lugar de `direct_code_deploy`. Requerido para agentes que usan protocolo WebSocket.
- **Frontend**: Aplicación React + MUI + Zustand desplegada en CloudFront.

## Requerimientos

### Requerimiento 1: Cognito Identity Pool para Credenciales AWS Temporales

**User Story:** Como APM autenticado, quiero que el browser obtenga credenciales AWS temporales a partir de mi JWT de Cognito, para poder conectarme directamente a AgentCore via WebSocket firmado con SigV4.

#### Criterios de Aceptación

1. THE CDK_Stack SHALL crear un Cognito_Identity_Pool que acepte tokens del Cognito_User_Pool existente (`PharmAssistUsers`) como proveedor de identidad.
2. THE Cognito_Identity_Pool SHALL tener un rol IAM autenticado con permisos mínimos: `bedrock-agentcore:InvokeAgentRuntime` sobre el ARN del BidiAgent.
3. THE Cognito_Identity_Pool SHALL NO permitir acceso a identidades no autenticadas (unauthenticated access deshabilitado).
4. THE CDK_Stack SHALL exportar el `IdentityPoolId` como stack output para configuración del frontend.
5. WHEN el APM se autentique en el frontend, THE Frontend SHALL intercambiar el JWT (id_token) del Cognito_User_Pool por credenciales AWS temporales usando el SDK de Cognito Identity.
6. THE credenciales temporales SHALL tener una duración máxima de 1 hora y el Frontend SHALL renovarlas automáticamente antes de que expiren.
7. IF el intercambio de credenciales falla, THEN THE Frontend SHALL mostrar "No se pudieron obtener credenciales para el modo voz. Intentá reloguearte." y deshabilitar el botón de modo voz.

### Requerimiento 2: BidiAgent de Voz con Strands BidiAgent

**User Story:** Como desarrollador, quiero un agente de voz basado en Strands BidiAgent que maneje Nova Sonic bidireccionalmente dentro de AgentCore, para eliminar el servidor intermedio.

#### Criterios de Aceptación

1. THE BidiAgent SHALL ser un agente Python que use la clase `BidiAgent` del SDK de Strands para manejar streaming bidireccional de audio con Nova_Sonic.
2. THE BidiAgent SHALL definir un único tool `consultarAsistente` que reciba la pregunta transcrita por Nova_Sonic y la envíe al Text_Agent existente via `bedrock-agentcore:InvokeAgentRuntime`.
3. WHEN Nova_Sonic invoque `consultarAsistente`, THE BidiAgent SHALL invocar el Text_Agent con el payload `{"prompt": "<pregunta>", "apm_id": "<apm_id>", "mode": "voice"}` y retornar la respuesta de texto para que Nova_Sonic genere audio.
4. THE BidiAgent SHALL usar el system prompt existente del voice server: instrucciones en español argentino, respuestas concisas de 2-3 oraciones, sin markdown, sin tablas, sin emojis, optimizadas para ser escuchadas.
5. THE BidiAgent SHALL configurar Nova_Sonic con voz `lupe` (femenina, español), audio de salida PCM 24kHz mono, y audio de entrada PCM 16kHz mono.
6. THE BidiAgent SHALL soportar interrupciones (barge-in): el APM puede hablar mientras el asistente responde, y el asistente se detiene para escuchar.
7. THE BidiAgent SHALL tener un límite de sesión de 8 minutos (límite de Nova_Sonic) con notificación al cliente antes de cerrar.
8. THE BidiAgent SHALL residir en un directorio `bidiagent/` en la raíz del proyecto, separado del agente de texto en `agentcore/`.

### Requerimiento 3: Deploy del BidiAgent en AgentCore con Container Deployment

**User Story:** Como desarrollador, quiero desplegar el BidiAgent en AgentCore usando container deployment con protocolo WebSocket, para que el frontend pueda conectarse directamente via WSS.

#### Criterios de Aceptación

1. THE BidiAgent SHALL desplegarse en AgentCore con `deployment_type: container` (no `direct_code_deploy`), ya que el protocolo WebSocket requiere container deployment.
2. THE BidiAgent SHALL configurarse con `server_protocol: WEBSOCKET` en la configuración de AgentCore.
3. THE BidiAgent SHALL tener un `Dockerfile` que instale las dependencias Python (strands-agents, bedrock-agentcore, boto3) y exponga el entrypoint.
4. THE BidiAgent SHALL recibir como variables de entorno: `BEDROCK_MODEL_ID`, `AWS_REGION`, `TEXT_AGENT_ARN` (ARN del Text_Agent existente para delegación via `consultarAsistente`).
5. THE BidiAgent SHALL estar wrapeado con `BedrockAgentCoreApp` siguiendo el patrón estándar de AgentCore.
6. WHEN el BidiAgent se despliegue exitosamente, THE sistema SHALL verificar conectividad WebSocket end-to-end desde el browser.

### Requerimiento 4: Frontend — Conexión WebSocket Directa con SigV4

**User Story:** Como APM, quiero que el modo voz se conecte directamente a AgentCore via WebSocket firmado, para tener menor latencia y que funcione desde la URL de producción (HTTPS).

#### Criterios de Aceptación

1. THE Frontend SHALL reemplazar la clase `VoiceService` actual (Socket.IO) por una nueva implementación que use WebSocket nativo con URL presignada SigV4.
2. THE Frontend SHALL generar la Presigned_WebSocket_URL usando las credenciales temporales del Cognito_Identity_Pool y el ARN del BidiAgent.
3. THE Frontend SHALL enviar audio del micrófono en formato PCM 16kHz mono via el WebSocket, siguiendo el protocolo de eventos de AgentCore BidiAgent.
4. THE Frontend SHALL recibir y reproducir audio de respuesta en tiempo real via WebAudio API, decodificando los chunks PCM 24kHz del BidiAgent.
5. THE Frontend SHALL mantener la interfaz visual existente (VoiceOverlay + ParticleSphere) sin cambios, actualizando solo el servicio de conexión.
6. THE Frontend SHALL enviar los eventos de protocolo BidiAgent en el orden correcto: sessionStart → promptStart (con toolConfiguration) → contentStart (system prompt) → textInput → contentEnd → contentStart (audio) → audioInput chunks.
7. WHEN el APM active el modo voz, THE Frontend SHALL solicitar permisos de micrófono, obtener credenciales SigV4, generar la URL presignada, y conectar el WebSocket en secuencia.
8. THE Frontend SHALL pasar el `apm_id` del JWT como parte del contexto de sesión para que el BidiAgent lo use en las invocaciones a `consultarAsistente`.

### Requerimiento 5: Protocolo de Eventos WebSocket BidiAgent

**User Story:** Como desarrollador, quiero un protocolo de eventos definido entre el frontend y el BidiAgent para comunicación bidireccional de audio consistente.

#### Criterios de Aceptación

1. THE Frontend SHALL enviar eventos con estructura JSON: `{"event": {"sessionStart": {...}}}`, `{"event": {"audioInput": {...}}}`, etc., siguiendo el protocolo de Nova Sonic bidireccional.
2. THE BidiAgent SHALL enviar eventos de respuesta con tipos: `audioOutput` (chunk de audio PCM base64), `textOutput` (transcripción), `contentStart` (inicio de contenido), `contentEnd` (fin de contenido).
3. WHEN el BidiAgent detecte una interrupción (barge-in), SHALL enviar un evento `textOutput` con contenido `{ "interrupted" : true }` y detener la generación de audio.
4. WHEN el BidiAgent invoque `consultarAsistente`, SHALL enviar un evento de estado que el Frontend interprete como "thinking" para actualizar la animación de la esfera.
5. THE Frontend SHALL mapear los eventos recibidos a los estados de la UI: `listening`, `thinking`, `speaking`, `idle`.
6. WHEN la sesión alcance el límite de 8 minutos, THE BidiAgent SHALL enviar un evento de cierre y THE Frontend SHALL mostrar "La sesión de voz expiró. Podés iniciar una nueva." con opción de reconectar.

### Requerimiento 6: Eliminación de Infraestructura ECS Fargate

**User Story:** Como desarrollador, quiero eliminar toda la infraestructura ECS del voice server para reducir costos y complejidad operativa.

#### Criterios de Aceptación

1. THE CDK_Stack SHALL eliminar los recursos de ECS Fargate del voice server: VPC (`VoiceVpc`), NAT Gateway, ECS Cluster (`VoiceCluster`), Fargate Task Definition, Fargate Service, ALB (`VoiceALB`), listener, target group.
2. THE CDK_Stack SHALL eliminar la variable de entorno `DEPLOY_VOICE_SERVER` y el bloque condicional `if os.environ.get("DEPLOY_VOICE_SERVER")` del stack.
3. THE CDK_Stack SHALL eliminar el stack output `VoiceServerUrl` si existe.
4. THE Frontend SHALL eliminar la dependencia de `socket.io-client` del `package.json`.
5. THE Frontend SHALL eliminar la variable de entorno `VITE_VOICE_URL` y reemplazarla por `VITE_BIDIAGENT_ARN` (o equivalente) para la conexión directa.
6. THE directorio `voice-server/` SHALL marcarse como deprecado o eliminarse del repositorio.
7. WHEN se despliegue el CDK_Stack actualizado, THE sistema SHALL verificar que no queden recursos ECS huérfanos en la cuenta AWS.

### Requerimiento 7: Manejo de Errores y Resiliencia del Modo Voz

**User Story:** Como APM, quiero que el modo voz maneje errores de forma transparente sin interrumpir mi experiencia.

#### Criterios de Aceptación

1. IF la conexión WebSocket al BidiAgent falla, THEN THE Frontend SHALL mostrar "No se pudo conectar al asistente de voz. Verificá tu conexión." con opción de reintentar.
2. IF las credenciales SigV4 expiran durante una sesión de voz, THEN THE Frontend SHALL renovar las credenciales y reconectar automáticamente sin intervención del APM.
3. IF el BidiAgent retorna un error de Nova_Sonic, THEN THE Frontend SHALL mostrar "El asistente de voz no está disponible." y ofrecer volver al chat de texto.
4. IF el micrófono no está disponible o el APM deniega permisos, THEN THE Frontend SHALL mostrar "Se necesita acceso al micrófono para el modo voz." y no intentar conectar.
5. THE Frontend SHALL implementar reconexión automática con backoff exponencial (1s, 2s, 4s) hasta 3 intentos cuando la conexión WebSocket se cierre inesperadamente.
6. IF la reconexión falla después de 3 intentos, THEN THE Frontend SHALL cerrar el overlay de voz y mostrar una notificación de error.
7. THE modo voz y el chat de texto SHALL ser experiencias independientes: errores en el modo voz NO afectan al chat de texto ni al dashboard.

### Requerimiento 8: Preservación de Funcionalidad Existente

**User Story:** Como APM, quiero que el chat de texto, el dashboard y todas las funcionalidades existentes sigan funcionando sin cambios después de la migración del modo voz.

#### Criterios de Aceptación

1. THE Text_Agent existente SHALL permanecer desplegado en AgentCore con `direct_code_deploy` y protocolo HTTP, sin modificaciones.
2. THE chat de texto SHALL seguir funcionando via WebSocket API Gateway → Lambda Proxy → AgentCore, sin cambios en el flujo.
3. THE dashboard, tarjetas contextuales (visitas, cumpleaños, SLA), y endpoints HTTP SHALL seguir funcionando via HTTP API Gateway con Cognito Authorizer.
4. THE pipeline de notas de voz (S3 → Transcribe → Bedrock → DynamoDB) SHALL seguir funcionando sin cambios.
5. THE Frontend SHALL mantener la interfaz visual del modo voz (VoiceOverlay, ParticleSphere) sin cambios visuales, actualizando solo la capa de conexión.
6. WHEN el APM use el modo voz con el nuevo BidiAgent, SHALL poder consultar los mismos datos que con el chat de texto (médicos, visitas, ventas, minutas, sugerencias).

### Requerimiento 9: Configuración y Variables de Entorno

**User Story:** Como desarrollador, quiero que toda la configuración del BidiAgent y la Identity Pool esté centralizada en `.env` y en outputs del CDK, para mantener consistencia con el resto del proyecto.

#### Criterios de Aceptación

1. THE `.env` SHALL incluir nuevas variables: `BIDIAGENT_AGENT_ARN` (ARN del BidiAgent en AgentCore), `IDENTITY_POOL_ID` (ID del Cognito Identity Pool).
2. THE `.env.example` SHALL actualizarse con las nuevas variables y comentarios descriptivos.
3. THE Frontend SHALL leer `VITE_IDENTITY_POOL_ID`, `VITE_BIDIAGENT_AGENT_ARN`, `VITE_USER_POOL_ID`, y `VITE_AWS_REGION` como variables de entorno de Vite.
4. THE BidiAgent SHALL leer `TEXT_AGENT_ARN`, `BEDROCK_MODEL_ID`, y `AWS_REGION` como variables de entorno en runtime.
5. THE CDK_Stack SHALL exportar `IdentityPoolId` y `BidiAgentArn` (si se gestiona via CDK) como stack outputs.
6. ALL valores sensibles (ARNs, IDs de pools) SHALL estar en `.env` y NO hardcodeados en el código fuente.

### Requerimiento 10: Seguridad y Permisos Mínimos

**User Story:** Como desarrollador, quiero que las credenciales temporales del browser tengan permisos mínimos para invocar solo el BidiAgent, sin acceso a otros recursos AWS.

#### Criterios de Aceptación

1. THE rol IAM autenticado del Cognito_Identity_Pool SHALL tener permisos SOLO para `bedrock-agentcore:InvokeAgentRuntime` sobre el ARN específico del BidiAgent.
2. THE rol IAM autenticado SHALL NO tener permisos para DynamoDB, S3, Lambda, ni otros servicios AWS.
3. THE Presigned_WebSocket_URL SHALL expirar en un tiempo configurable (default 5 minutos) para limitar la ventana de uso.
4. THE BidiAgent SHALL validar que el `apm_id` recibido en el contexto de sesión corresponda a un APM válido antes de invocar el Text_Agent.
5. THE Cognito_Identity_Pool SHALL usar el claim `sub` del JWT como identificador de identidad, no el email ni el `apm_id`.
6. THE credenciales temporales SHALL estar scoped a la región del BidiAgent (`us-east-1`).
