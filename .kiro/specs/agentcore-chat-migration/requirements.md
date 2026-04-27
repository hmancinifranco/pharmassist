# Documento de Requerimientos — Migración Chat a AgentCore + Cognito Auth

## Introducción

PharmAssist actualmente ejecuta el agente Strands embebido dentro de la Lambda de FastAPI. El chat del APM envía un HTTP POST a API Gateway HTTP API → Lambda → Strands Agent → Bedrock. Este flujo tiene tres problemas críticos:

1. **Timeout de 30 segundos**: API Gateway HTTP API tiene un hard limit de 30s. Consultas complejas (briefs con web search, análisis de ventas multi-zona) toman 25-40s y fallan intermitentemente.
2. **Sin observabilidad ni persistencia**: El agente Strands corre dentro de Lambda sin métricas GenAI, sin gestión de memoria (STM), sin persistencia de sesión entre cold starts.
3. **Sin autenticación**: La app no tiene capa de login. Cualquiera con la URL puede acceder a datos de médicos y ventas. El `apm_id` está hardcodeado en el frontend.

Esta migración resuelve los tres problemas:
- **Cognito User Pool** para autenticación de APMs (login con usuario/contraseña)
- **WebSocket API Gateway + Lambda Proxy** (Opción A) para chat via AgentCore Runtime con streaming
- **AgentCore Identity** reutiliza el mismo Cognito User Pool para que el agente acceda a servicios externos sin re-autenticación

Los endpoints de dashboard permanecen como HTTP en el API Gateway existente, protegidos por el mismo Cognito authorizer.

## Decisión Arquitectónica: Opción A (Lambda Proxy)

Se eligió la Opción A (Lambda Proxy con WebSocket API Gateway) sobre las alternativas B (Presigned URL directo) y C (Híbrido) por las siguientes razones:

| Criterio | Opción A (Lambda Proxy) | Opción B (Presigned URL) | Opción C (Híbrido) |
|----------|------------------------|--------------------------|---------------------|
| Seguridad | Alta — auth en Lambda, no expone ARN de AgentCore | Media — URL firmada expuesta al browser | Media |
| Control | Total — logging, rate limiting, validación | Limitado — el frontend habla directo con AgentCore | Parcial |
| Producción | Patrón estándar AWS | Más simple pero menos controlable | Mezcla de patrones |
| Streaming | Via WS API GW → Lambda → AgentCore | Nativo WS a AgentCore | Mixto |
| Complejidad | Media — Lambda proxy + WS API GW | Baja — solo endpoint de URL | Media |

**Decisión: Opción A** — es el patrón recomendado para producción porque permite autenticación centralizada, logging, rate limiting, y no expone el ARN de AgentCore al frontend.

## Glosario

- **Cognito_User_Pool**: Amazon Cognito User Pool que gestiona la autenticación de APMs. Cada APM tiene un usuario con atributo custom `apm_id` (ej: "Valentina Pérez"). El JWT token incluye el `apm_id` como claim.
- **Cognito_Authorizer**: Authorizer de API Gateway que valida el JWT token de Cognito en cada request HTTP y WebSocket.
- **AgentCore_Runtime**: Servicio gestionado de Amazon Bedrock AgentCore que ejecuta el agente Strands con observabilidad, STM memory y gestión de sesiones.
- **AgentCore_Identity**: Servicio de AgentCore que permite al agente acceder a servicios externos usando el mismo Cognito User Pool, sin re-autenticación del usuario.
- **WebSocket_API**: API Gateway WebSocket API que mantiene conexiones bidireccionales persistentes entre el frontend y el backend.
- **Lambda_Proxy**: Función Lambda liviana que recibe mensajes del WebSocket_API, invoca AgentCore_Runtime via `invoke-agent-runtime`, y retransmite la respuesta streaming de vuelta al WebSocket.
- **HTTP_API**: API Gateway HTTP API existente que sirve los endpoints de dashboard, ahora protegido por Cognito_Authorizer.
- **JWT_Token**: Token JSON Web Token emitido por Cognito al hacer login. Contiene claims: `sub`, `email`, `custom:apm_id`. Se envía como `Authorization: Bearer <token>` en HTTP y como query param en WebSocket.
- **STM_Memory**: Short-Term Memory gestionada por AgentCore que persiste contexto de conversación entre invocaciones.
- **CDK_Stack**: Stack de AWS CDK (`PharmAssistStack`) que define toda la infraestructura.
- **Dashboard_Endpoints**: Endpoints HTTP existentes protegidos por Cognito_Authorizer.
- **APM**: Agente de Propaganda Médica, usuario principal de PharmAssist.

## Requerimientos

### Requerimiento 1: Autenticación con Cognito User Pool

**User Story:** Como APM, quiero loguearme con mi usuario y contraseña para acceder a PharmAssist, para que mis datos y los de mis médicos estén protegidos.

#### Criterios de Aceptación

1. THE CDK_Stack SHALL crear un Cognito_User_Pool con nombre `PharmAssistUsers` y configuración de sign-in por email.
2. THE Cognito_User_Pool SHALL tener un atributo custom `apm_id` (string, mutable) que identifica al APM en el sistema.
3. THE CDK_Stack SHALL crear un Cognito App Client con flujo `USER_PASSWORD_AUTH` y `USER_SRP_AUTH` habilitados, sin client secret (para uso desde SPA).
4. THE CDK_Stack SHALL crear al menos un usuario de demo: email `valentina@pharmassist.demo`, password configurable via env var, con `custom:apm_id = "Valentina Pérez"`.
5. THE frontend SHALL mostrar una pantalla de login antes del dashboard, con campos email y contraseña.
6. WHEN el APM se loguee exitosamente, THE frontend SHALL almacenar el JWT_Token (id_token y access_token) en memoria (no localStorage por seguridad) y usarlo en todas las requests subsiguientes.
7. WHEN el JWT_Token expire, THE frontend SHALL usar el refresh_token para obtener uno nuevo sin requerir re-login.
8. THE frontend SHALL extraer el `apm_id` del claim `custom:apm_id` del JWT_Token y usarlo en lugar del valor hardcodeado actual.

### Requerimiento 2: Protección de API Gateway HTTP con Cognito

**User Story:** Como desarrollador, quiero que todos los endpoints HTTP estén protegidos por Cognito, para que solo APMs autenticados puedan acceder a los datos.

#### Criterios de Aceptación

1. THE CDK_Stack SHALL configurar un Cognito_Authorizer en HTTP_API que valide el JWT_Token en el header `Authorization: Bearer <token>`.
2. ALL Dashboard_Endpoints SHALL requerir un JWT_Token válido para responder. Requests sin token o con token inválido SHALL recibir HTTP 401.
3. THE Lambda de FastAPI SHALL extraer el `apm_id` del JWT_Token (claim `custom:apm_id`) en lugar de recibirlo como query parameter.
4. THE endpoint `/health` SHALL permanecer sin autenticación para health checks.
5. THE frontend SHALL incluir el JWT_Token en el header `Authorization` de todas las requests HTTP via un interceptor de axios.

### Requerimiento 3: WebSocket API Gateway con Lambda Proxy para Chat

**User Story:** Como APM, quiero que el chat use WebSocket para recibir respuestas del asistente en streaming via AgentCore, para que no se corte por timeout y pueda ver la respuesta mientras se genera.

#### Criterios de Aceptación

1. THE CDK_Stack SHALL crear un WebSocket_API con rutas `$connect`, `$disconnect` y `sendMessage`.
2. THE WebSocket_API SHALL validar el JWT_Token de Cognito en la ruta `$connect` (via query parameter `token` o header).
3. THE CDK_Stack SHALL crear una Lambda_Proxy con runtime Python 3.12, timeout de 120 segundos, y permisos IAM para `bedrock-agentcore:InvokeAgentRuntime` y `execute-api:ManageConnections`.
4. WHEN la Lambda_Proxy reciba un mensaje en la ruta `sendMessage`, SHALL extraer `prompt` y `session_id` del payload, y el `apm_id` del JWT_Token validado en `$connect`.
5. THE Lambda_Proxy SHALL invocar AgentCore_Runtime usando `invoke-agent-runtime` con el payload `{"prompt": "...", "apm_id": "..."}` y el `runtimeSessionId` del `session_id`.
6. WHEN AgentCore_Runtime retorne la respuesta, THE Lambda_Proxy SHALL retransmitir el contenido al cliente WebSocket usando `post_to_connection`.
7. THE Lambda_Proxy SHALL tener código mínimo — solo forwarding, sin lógica de agente, sin tools, sin dependencias pesadas (solo boto3).
8. THE CDK_Stack SHALL exportar la URL del WebSocket_API como stack output (`WebSocketUrl`).

### Requerimiento 4: Migración del Frontend ChatPanel a WebSocket

**User Story:** Como APM, quiero que el chat muestre las respuestas del asistente en streaming mientras se generan, para tener una experiencia fluida sin esperas largas.

#### Criterios de Aceptación

1. WHEN el APM envíe un mensaje en el Chat_Panel, THE frontend SHALL enviar el mensaje via WebSocket con formato `{"action": "sendMessage", "data": {"prompt": "...", "session_id": "..."}}`.
2. THE Chat_Panel SHALL establecer la conexión WebSocket al cargar el dashboard, incluyendo el JWT_Token como query parameter para autenticación.
3. WHEN el frontend reciba chunks de respuesta via WebSocket, THE Chat_Panel SHALL renderizar el texto incrementalmente (streaming visual).
4. WHEN la conexión WebSocket se cierre inesperadamente, THE Chat_Panel SHALL intentar reconectar automáticamente hasta 3 veces con backoff exponencial.
5. IF la reconexión falla, THEN THE Chat_Panel SHALL mostrar "Se perdió la conexión con el asistente. Recargá la página." con botón de reconexión.
6. THE frontend SHALL seguir usando HTTP (axios con JWT) para todos los Dashboard_Endpoints.

### Requerimiento 5: Protocolo de Mensajes WebSocket

**User Story:** Como desarrollador, quiero un protocolo de mensajes definido entre frontend y backend para comunicación consistente.

#### Criterios de Aceptación

1. THE frontend SHALL enviar mensajes con formato: `{"action": "sendMessage", "data": {"prompt": "...", "session_id": "..."}}`.
2. THE backend SHALL enviar respuestas con campo `type`: `"chunk"` (fragmento parcial), `"complete"` (fin de respuesta), `"error"` (error), `"tools"` (herramientas usadas).
3. WHEN el backend envíe `"chunk"`, SHALL incluir `{"type": "chunk", "content": "..."}`.
4. WHEN el backend envíe `"complete"`, SHALL incluir `{"type": "complete", "session_id": "..."}`.
5. WHEN el backend envíe `"tools"`, SHALL incluir `{"type": "tools", "steps": ["Buscando médico en CRM", ...]}` para mostrar el proceso del agente.
6. WHEN el backend envíe `"error"`, SHALL incluir `{"type": "error", "message": "..."}` en español.

### Requerimiento 6: AgentCore Identity con Cognito (Single Sign-On)

**User Story:** Como APM, quiero que el asistente pueda acceder a servicios externos en mi nombre sin pedirme que me loguee de nuevo, para una experiencia fluida.

#### Criterios de Aceptación

1. THE AgentCore_Runtime SHALL estar configurado para usar AgentCore_Identity con el mismo Cognito_User_Pool usado para la autenticación del frontend.
2. WHEN el Lambda_Proxy invoque AgentCore_Runtime, SHALL pasar el JWT_Token del APM como contexto para que AgentCore_Identity pueda actuar en nombre del usuario.
3. THE APM SHALL NOT ser requerido a re-autenticarse para usar el chat después de haberse logueado en el frontend.
4. THE AgentCore_Identity SHALL usar el `apm_id` del JWT_Token para el aislamiento de datos en los tools del agente.

### Requerimiento 7: Preservación de Funcionalidad Existente

**User Story:** Como APM, quiero que todas las funcionalidades del dashboard sigan funcionando después de la migración, con la adición de autenticación.

#### Criterios de Aceptación

1. THE Dashboard_Endpoints SHALL seguir respondiendo via HTTP_API, ahora protegidos por Cognito_Authorizer.
2. ALL endpoints existentes SHALL mantener el mismo formato de request/response, excepto que `apm_id` se extrae del JWT en lugar de query parameter.
3. THE Lambda de FastAPI existente SHALL seguir ejecutándose para los Dashboard_Endpoints.
4. THE endpoint `/api/chat` HTTP SHALL mantenerse como fallback cuando el WebSocket no esté disponible.
5. THE tarjetas contextuales (visitas, cumpleaños, SLA) SHALL seguir cargando al abrir el dashboard.

### Requerimiento 8: Observabilidad y Monitoreo

**User Story:** Como desarrollador, quiero visibilidad completa sobre el chat via AgentCore para diagnosticar problemas.

#### Criterios de Aceptación

1. THE AgentCore_Runtime SHALL proveer métricas en CloudWatch GenAI Dashboard: latencia, tokens, errores.
2. THE Lambda_Proxy SHALL emitir logs estructurados: `apm_id`, `session_id`, duración, status.
3. THE sistema SHALL correlacionar consultas desde frontend hasta AgentCore usando `session_id`.
4. IF una invocación toma más de 60 segundos, THEN registrar warning con detalle.

### Requerimiento 9: Gestión de Sesiones y Memoria

**User Story:** Como APM, quiero que el asistente recuerde el contexto de mi conversación entre mensajes.

#### Criterios de Aceptación

1. THE frontend SHALL generar un `session_id` único al iniciar conversación y reutilizarlo.
2. THE AgentCore_Runtime SHALL usar `runtimeSessionId` para mantener contexto via STM_Memory.
3. WHEN el APM cierre y reabra el Chat_Panel, SHALL mantener el mismo `session_id` mientras la sesión del browser esté activa.
4. WHEN el APM haga click en "Limpiar chat", SHALL generar nuevo `session_id`.

### Requerimiento 10: Manejo de Errores y Resiliencia

**User Story:** Como APM, quiero que el chat maneje errores transparentemente sin interrumpir mi trabajo.

#### Criterios de Aceptación

1. IF la conexión WebSocket falla, THEN mostrar "No se pudo conectar con el asistente." con opción de reintentar.
2. IF AgentCore_Runtime retorna error, THEN mostrar "El asistente no está disponible." como mensaje del asistente.
3. IF no hay respuesta en 120 segundos, THEN mostrar "El asistente está tardando. Intentá de nuevo." y liberar estado de carga.
4. THE Chat_Panel SHALL deshabilitar envío mientras espera respuesta.
5. Errores del WebSocket NO afectan las tarjetas contextuales del dashboard.
6. IF el WebSocket se desconecta durante respuesta, THEN mostrar texto parcial con "(respuesta incompleta)".

### Requerimiento 11: Infraestructura CDK Unificada

**User Story:** Como desarrollador, quiero que toda la infraestructura nueva (Cognito, WebSocket API, Lambda Proxy) esté en el mismo CDK stack existente.

#### Criterios de Aceptación

1. THE CDK_Stack SHALL agregar Cognito_User_Pool, Cognito App Client, Cognito_Authorizer, WebSocket_API, y Lambda_Proxy al stack `PharmAssistStack` existente.
2. THE CDK_Stack SHALL exportar outputs adicionales: `UserPoolId`, `UserPoolClientId`, `WebSocketUrl`.
3. THE CDK_Stack SHALL pasar el `UserPoolId` como variable de entorno a la Lambda de FastAPI para validación de tokens.
4. ALL nuevos recursos SHALL seguir las convenciones existentes: tags automáticos, removal policy DESTROY para dev, nombres generados por CDK.
5. THE CDK_Stack SHALL NOT modificar los recursos existentes (DynamoDB tables, Lambda FastAPI, HTTP API, S3, CloudFront) de forma que rompa funcionalidad actual.

### Requerimiento 12: Tool de Sugerencia Inteligente de Próxima Visita

**User Story:** Como APM, quiero preguntarle al asistente "se me liberó un hueco, ¿a quién puedo visitar?" y recibir una sugerencia priorizada basada en SLA, ventas y proximidad, para aprovechar mi tiempo de forma óptima.

**Validación técnica:** Los datos necesarios ya existen en DynamoDB:
- `crm_medicos`: Cadencia, Fecha_Ultima_Visita, Zona, Latitud, Longitud, Especialidad_Medica
- `visitas_planificadas`: Estado (Pendiente/Completada/Vencida), Fecha_Planificada
- `ventas_reportadas`: Crecimiento_YoY_Pct por Zona y Producto
- `minutas_visitas`: notas de visitas previas (contexto para la sugerencia)

#### Criterios de Aceptación

1. THE agente SHALL tener un nuevo tool `sugerir_proxima_visita(apm_id: str)` que retorne un ranking de médicos priorizados para visitar.
2. THE tool SHALL calcular la prioridad combinando: (a) días de SLA vencido (mayor peso), (b) productos con caída de ventas en la zona del médico, (c) visitas planificadas pendientes para hoy/esta semana.
3. THE tool SHALL retornar para cada médico sugerido: nombre, especialidad, zona, dirección, motivo de la sugerencia (ej: "SLA vencido hace 15 días", "APSICO cayó -86% en su zona"), y productos recomendados.
4. THE tool SHALL limitar el resultado a los top 5 médicos más prioritarios.
5. WHEN el APM pregunte "¿a quién puedo visitar?", "se me liberó un hueco", o variantes similares, THE agente SHALL invocar este tool automáticamente.
6. IF hay minutas de visitas previas para un médico sugerido, THE tool SHALL incluir un resumen breve de la última minuta como contexto.

### Requerimiento 13: Pipeline de Notas de Voz (Transcripción + Resumen IA)

**User Story:** Como APM, quiero grabar una nota de voz después de una visita y que el sistema la transcriba y genere un resumen estructurado automáticamente, para documentar visitas sin escribir.

**Validación técnica:**
- Amazon Transcribe soporta español (`es-ES`) en batch y streaming, disponible en us-east-1 ([docs](https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html))
- Existe un CDK Solutions Construct `aws-lambda-transcribe` que crea el patrón S3 → Lambda → Transcribe ([docs](https://docs.aws.amazon.com/solutions/latest/constructs/aws_lambda_transcribe.html))
- S3 event notifications pueden triggear Lambda al crear un objeto ([docs](https://docs.aws.amazon.com/lambda/latest/dg/with-s3.html))
- La tabla `minutas_visitas` ya existe con campos: Resumen, Productos_Discutidos, Compromisos, Proximos_Pasos

#### Criterios de Aceptación

1. THE frontend SHALL permitir al APM grabar audio desde el micrófono del dispositivo usando MediaRecorder API (componente `GrabadorAudio` existente).
2. WHEN el APM termine de grabar, THE frontend SHALL subir el archivo de audio a un S3 bucket dedicado (`pharmassist-audio-uploads`) via una presigned URL generada por un endpoint HTTP protegido por Cognito_Authorizer.
3. THE CDK_Stack SHALL crear un S3 bucket para audio uploads con lifecycle policy de 30 días (auto-delete).
4. THE CDK_Stack SHALL crear una Lambda `TranscribeLambda` que se triggee con S3 `ObjectCreated` events en el bucket de audio.
5. THE `TranscribeLambda` SHALL iniciar un batch transcription job en Amazon Transcribe con `LanguageCode="es-ES"` y el audio del S3 como input.
6. THE CDK_Stack SHALL crear una segunda Lambda `SummarizeLambda` que se triggee cuando Transcribe complete el job (via EventBridge o polling).
7. THE `SummarizeLambda` SHALL invocar Amazon Bedrock (Claude Opus 4.6) con la transcripción y un prompt que genere: resumen (párrafo), productos discutidos (lista), compromisos (texto), próximos pasos (texto).
8. THE `SummarizeLambda` SHALL escribir el resultado en la tabla `minutas_visitas` de DynamoDB con los campos: Minuta_ID (UUID), APM, Medico_MN, Fecha_Creacion, Transcripcion, Resumen, Productos_Discutidos, Compromisos, Proximos_Pasos.
9. THE frontend SHALL mostrar el estado del procesamiento: "Subiendo audio...", "Transcribiendo...", "Generando resumen...", "Listo".
10. WHEN la minuta esté lista, THE frontend SHALL mostrarla para revisión del APM antes de confirmar.
11. THE APM SHALL poder asociar la nota de voz a un médico específico de su cartera (selección antes o después de grabar).

### Requerimiento 14: Consulta de Minutas por el Agente

**User Story:** Como APM, quiero que el asistente pueda consultar mis notas de visitas previas cuando le pido un brief o sugerencias, para que las recomendaciones sean más contextuales.

#### Criterios de Aceptación

1. THE agente SHALL tener un tool `obtener_minutas_medico(medico_mn: int, apm_id: str)` que consulte la tabla `minutas_visitas` por médico.
2. WHEN el APM pida un brief de un médico, THE tool `generar_brief_medico` SHALL incluir un resumen de las últimas minutas como sección "Notas de Visitas Previas".
3. WHEN el tool `sugerir_proxima_visita` sugiera un médico, SHALL incluir contexto de la última minuta si existe (compromisos pendientes, próximos pasos).
4. THE tool SHALL retornar las últimas 3 minutas ordenadas por fecha descendente, con campos: fecha, resumen, productos discutidos, compromisos.

### Requerimiento 15: Modo Voice-to-Voice con Amazon Nova Sonic

**User Story:** Como APM que va manejando entre visitas, quiero hablar con el asistente por voz y escuchar las respuestas habladas, con una interfaz visual inmersiva estilo Perplexity, para consultar información sin usar las manos.

**Validación técnica:**
- Amazon Nova Sonic disponible en us-east-1 ([anuncio](https://aws.amazon.com/about-aws/whats-new/2025/04/amazon-nova-sonic-speech-to-speech-conversations-bedrock/))
- Soporta español con voces expresivas masculinas y femeninas ([docs](https://docs.aws.amazon.com/nova/latest/userguide/speech.html))
- Soporta function calling / tool use nativo con `toolSpec` ([docs](https://docs.aws.amazon.com/nova/latest/userguide/speech-tools.html))
- Soporta agentic flows con múltiples tools ([docs](https://docs.aws.amazon.com/nova/latest/userguide/speech-agentic.html))
- Bidirectional streaming API via HTTP/2 para baja latencia
- Soporta interrupciones (barge-in) sin perder contexto
- Sample de referencia: [aws-samples/sample-nova-sonic-mcp](https://github.com/aws-samples/sample-nova-sonic-mcp)

**Referencia visual:** Interfaz estilo Perplexity Voice — pantalla completa con esfera de partículas animada central que reacciona al audio, fondo limpio, controles mínimos (cerrar y micrófono).

#### Criterios de Aceptación

**Interfaz visual (estilo Perplexity Voice)**

1. WHEN el APM active el modo voz, THE frontend SHALL mostrar una pantalla fullscreen overlay sobre el dashboard con fondo claro/oscuro limpio.
2. THE pantalla de voz SHALL mostrar en el centro una esfera animada de partículas (particle sphere) que reaccione al volumen del audio — se expande y vibra cuando el APM habla o el asistente responde, y se contrae suavemente en silencio.
3. THE pantalla SHALL mostrar un texto de estado debajo de la esfera: "Escuchando...", "Pensando...", "Respondiendo...", "Conectando..." según el estado de la conversación.
4. THE pantalla SHALL tener dos botones en la parte inferior: botón X (cerrar/colgar) a la izquierda y botón de micrófono a la derecha.
5. THE botón de micrófono SHALL permitir mutear/desmutear el audio del APM con feedback visual (cambio de color/icono).
6. THE esfera de partículas SHALL usar Canvas 2D o WebGL para renderizar partículas distribuidas en forma esférica con animación fluida a 60fps.
7. WHEN el asistente esté "pensando" (invocando tools), THE esfera SHALL mostrar una animación de rotación suave diferente a la de audio activo.

**Audio y streaming**

8. THE frontend SHALL capturar audio del micrófono en formato PCM 16kHz mono y transmitirlo via WebSocket al backend.
9. THE backend SHALL usar la Bidirectional Streaming API de Amazon Nova Sonic (`amazon.nova-sonic-v1:0`) para procesar el audio y generar respuestas habladas.
10. THE frontend SHALL reproducir el audio de respuesta en tiempo real mientras se genera (streaming de audio via WebAudio API).
11. THE sistema SHALL soportar interrupciones (barge-in): el APM puede hablar mientras el asistente responde, y el asistente se detiene para escuchar.

**Tools y agente**

12. THE sistema SHALL definir un único tool para Nova Sonic llamado `consultarAsistente` que reciba la pregunta transcrita por Nova Sonic y la envíe a AgentCore_Runtime via `invoke-agent-runtime`.
13. WHEN Nova Sonic invoque `consultarAsistente`, THE backend SHALL invocar AgentCore_Runtime con el payload `{"prompt": "<pregunta>", "apm_id": "<apm_id>"}` y retornar la respuesta de texto al modelo para que genere la respuesta hablada.
14. THE AgentCore_Runtime SHALL ser la fuente de verdad de todas las tools — Nova Sonic NO tiene tools propias de DynamoDB, solo delega a AgentCore que ejecuta las 14+ Strands tools.
15. THE system prompt de AgentCore SHALL detectar (via un flag en el payload, ej: `"mode": "voice"`) que la respuesta será hablada, y ajustar el formato: resúmenes en texto plano, sin tablas, sin markdown, sin emojis, sin listas con viñetas, optimizado para ser escuchado naturalmente.
16. THE voz por defecto SHALL ser femenina en español (configurable).

**Infraestructura y deploy**

16. THE backend del modo voz SHALL ser un servicio Node.js (basado en el sample de referencia) desplegado como Lambda o ECS task via CDK en el mismo stack.
17. THE frontend SHALL enviar el JWT_Token de Cognito al conectarse al server de voz (via query param o header en la conexión Socket.IO), y el server SHALL validar el JWT contra el Cognito_User_Pool antes de aceptar la conexión.
18. THE server de voz SHALL extraer el `apm_id` del JWT validado y pasarlo a AgentCore en cada invocación de `consultarAsistente`.
19. THE modo voz y el chat de texto SHALL ser experiencias independientes — el APM puede usar uno u otro.
20. THE sistema completo (frontend + backend voice + Nova Sonic + AgentCore + tools) SHALL estar desplegado y probado end-to-end en AWS antes de considerar el feature completo.
