# Requirements Document — Platform Consolidation

## Introducción

Este spec consolida la plataforma PharmAssist eliminando la dependencia de DynamoDB para los datos del dashboard (médicos, visitas, ventas, planificadas) y migrando las consultas a Aurora PostgreSQL via FastAPI. Se simplifican el CDK stack, el flujo de deploy (`make deploy-all` / `make destroy`), y se mejora la UX del frontend (loading skeletons, dark mode fixes, suggestion chips, WebSocket fallback silencioso). Se agrega un test E2E con Playwright para validar el flujo completo.

## Glosario

- **Sistema_Dashboard**: Componentes frontend (React + MUI) que renderizan las tarjetas del dashboard del APM (visitas hoy, cumpleaños, alertas SLA)
- **Sistema_Backend**: Servidor FastAPI que expone endpoints REST para el dashboard y chat, consultando Aurora PostgreSQL
- **Sistema_CDK**: Stack de infraestructura AWS CDK que define los recursos cloud del proyecto
- **Sistema_Deploy**: Conjunto de targets del Makefile que orquestan el deploy completo de infraestructura, agentes y frontend
- **Sistema_Frontend**: Aplicación React SPA con Material UI que consume la API y WebSocket
- **Sistema_E2E**: Suite de tests end-to-end con Playwright que valida flujos críticos del usuario
- **Aurora_DB**: Base de datos Aurora PostgreSQL con tablas `agenda`, `doctor`, `cartera_medica`
- **MinutasTable**: Tabla DynamoDB que persiste minutas de visitas (única tabla DynamoDB que se conserva)
- **APM**: Agente de Propaganda Médica — usuario principal del sistema
- **Suggestion_Chips**: Botones clickeables con sugerencias de consulta que el APM puede enviar al chat
- **Loading_Skeleton**: Componente MUI Skeleton que indica carga en progreso sin mostrar errores
- **WebSocket_Fallback**: Mecanismo que degrada silenciosamente a HTTP polling cuando la conexión WebSocket falla


## Requirements

### Requirement 1 — Dashboard con Aurora PostgreSQL

**User Story:** Como APM, quiero que mis tarjetas del dashboard carguen datos desde Aurora PostgreSQL, para tener información actualizada desde la fuente de verdad del CRM sin depender de DynamoDB.

#### Acceptance Criteria

1. WHEN el APM accede al dashboard, THE Sistema_Backend SHALL consultar la tabla `agenda` en Aurora_DB para obtener las visitas planificadas del día filtradas por `apm_id`
2. WHEN el APM accede al dashboard, THE Sistema_Backend SHALL consultar la tabla `doctor` en Aurora_DB para obtener los cumpleaños próximos filtrados por los médicos asignados al APM
3. WHEN el APM accede al dashboard, THE Sistema_Backend SHALL consultar la tabla `cartera_medica` en Aurora_DB para calcular alertas SLA basadas en la última fecha de visita vs cadencia del médico
4. THE Sistema_Backend SHALL obtener las credenciales de conexión a Aurora_DB desde AWS Secrets Manager usando el SDK de boto3
5. THE Sistema_Backend SHALL usar la librería `psycopg2` para ejecutar queries parametrizados contra Aurora_DB
6. THE Sistema_Backend SHALL mantener los endpoints REST existentes (`/api/dashboard/visits-today`, `/api/dashboard/birthdays`, `/api/dashboard/sla-alerts`) con los mismos contratos de respuesta
7. IF la conexión a Aurora_DB falla, THEN THE Sistema_Backend SHALL retornar un HTTP 503 con un mensaje de error genérico sin exponer detalles internos de la base de datos


### Requirement 2 — Eliminación de tablas DynamoDB del CDK Stack

**User Story:** Como equipo de desarrollo, quiero eliminar las 4 tablas DynamoDB que ya no se usan (MedicosTable, VisitasTable, VentasTable, PlanificadasTable), para simplificar la infraestructura y reducir costos.

#### Acceptance Criteria

1. THE Sistema_CDK SHALL eliminar la definición de `MedicosTable` (tabla `crm_medicos`) del stack
2. THE Sistema_CDK SHALL eliminar la definición de `VisitasTable` (tabla `apm_visitas`) del stack
3. THE Sistema_CDK SHALL eliminar la definición de `VentasTable` (tabla `ventas_reportadas`) del stack
4. THE Sistema_CDK SHALL eliminar la definición de `PlanificadasTable` (tabla `visitas_planificadas`) del stack
5. THE Sistema_CDK SHALL conservar la definición de `MinutasTable` (tabla `minutas_visitas`) en el stack
6. THE Sistema_CDK SHALL conservar las definiciones de Cognito User Pool, Identity Pool, API Gateway (HTTP y WebSocket), Lambda proxy, CloudFront + S3 (frontend), y S3 audio bucket
7. THE Sistema_CDK SHALL eliminar los CfnOutputs asociados a las 4 tablas removidas
8. THE Sistema_CDK SHALL eliminar los permisos IAM del Lambda proxy que referencien las 4 tablas removidas
9. WHEN se ejecute `cdk synth`, THE Sistema_CDK SHALL generar un template CloudFormation válido sin errores


### Requirement 3 — UX: Loading Skeletons

**User Story:** Como APM, quiero ver indicadores de carga elegantes mientras se obtienen los datos del dashboard, para saber que la app está respondiendo sin ver errores intermitentes.

#### Acceptance Criteria

1. WHILE los datos de visitas del día se están cargando, THE Sistema_Dashboard SHALL mostrar un componente MUI Skeleton con la forma y dimensiones aproximadas de la tarjeta TarjetaVisitasHoy
2. WHILE los datos de cumpleaños se están cargando, THE Sistema_Dashboard SHALL mostrar un componente MUI Skeleton con la forma y dimensiones aproximadas de la tarjeta TarjetaCumpleanos
3. WHILE los datos de alertas SLA se están cargando, THE Sistema_Dashboard SHALL mostrar un componente MUI Skeleton con la forma y dimensiones aproximadas de la tarjeta TarjetaAlertasSLA
4. WHEN la carga finaliza exitosamente, THE Sistema_Dashboard SHALL reemplazar el Skeleton por la tarjeta con datos reales sin parpadeo visible
5. IF la carga falla después de agotar los reintentos, THEN THE Sistema_Dashboard SHALL mostrar la tarjeta en estado vacío con un texto indicando que no se pudieron cargar los datos

### Requirement 4 — UX: WebSocket Fallback silencioso

**User Story:** Como APM, quiero que el chat funcione sin interrupciones aunque el WebSocket falle, para no perder productividad por problemas de conectividad.

#### Acceptance Criteria

1. IF la conexión WebSocket falla al establecerse, THEN THE Sistema_Frontend SHALL degradar silenciosamente a comunicación via HTTP POST al endpoint `/api/chat` sin mostrar un banner de error al usuario
2. IF la conexión WebSocket se interrumpe durante una sesión activa, THEN THE Sistema_Frontend SHALL reconectar automáticamente en segundo plano y usar HTTP como fallback mientras reconecta
3. THE Sistema_Frontend SHALL indicar el modo de conexión activo (WebSocket o HTTP) únicamente en la consola del navegador para debugging, sin mostrar indicadores visuales al APM
4. WHEN el WebSocket se reconecta exitosamente después de un fallback HTTP, THE Sistema_Frontend SHALL retomar la comunicación via WebSocket sin intervención del usuario


### Requirement 5 — UX: Dark Mode Fixes

**User Story:** Como APM, quiero que el dark mode se vea correctamente en todas las tarjetas y componentes del dashboard, para usar la app de noche sin problemas de contraste o legibilidad.

#### Acceptance Criteria

1. WHILE el tema dark mode está activo, THE Sistema_Frontend SHALL renderizar todas las tarjetas del dashboard con colores de fondo y texto que cumplan un ratio de contraste mínimo de 4.5:1 según WCAG AA
2. WHILE el tema dark mode está activo, THE Sistema_Frontend SHALL renderizar los Suggestion_Chips con colores de fondo y borde visibles contra el fondo oscuro del panel de chat
3. WHILE el tema dark mode está activo, THE Sistema_Frontend SHALL renderizar las tablas DataGrid con bordes de celda, headers y texto legibles sin conflictos de color
4. WHILE el tema dark mode está activo, THE Sistema_Frontend SHALL renderizar los Loading_Skeleton con una animación de pulso que sea visible contra el fondo oscuro

### Requirement 6 — UX: Suggestion Chips clickeables via HTTP fallback

**User Story:** Como APM, quiero poder clickear chips de sugerencia para enviar consultas predefinidas al chat, para agilizar las interacciones más frecuentes sin tipear.

#### Acceptance Criteria

1. THE Sistema_Frontend SHALL mostrar entre 3 y 5 Suggestion_Chips debajo del área de input del chat cuando no hay mensajes en la conversación
2. WHEN el APM hace click en un Suggestion_Chip, THE Sistema_Frontend SHALL enviar el texto del chip como mensaje al chat usando el canal disponible (WebSocket o HTTP fallback)
3. WHEN el APM hace click en un Suggestion_Chip, THE Sistema_Frontend SHALL mostrar el texto del chip como un mensaje enviado por el usuario en el historial del chat
4. WHEN se envía un mensaje (por chip o por input), THE Sistema_Frontend SHALL ocultar los Suggestion_Chips hasta que la conversación se reinicie
5. THE Sistema_Frontend SHALL obtener los textos de los Suggestion_Chips desde una configuración local sin requerir una llamada al backend


### Requirement 7 — Deploy unificado con Makefile

**User Story:** Como desarrollador, quiero un solo comando `make deploy-all` que despliegue toda la plataforma (CDK + agentes + frontend), para simplificar el proceso de deploy y evitar pasos manuales.

#### Acceptance Criteria

1. WHEN se ejecuta `make deploy-all`, THE Sistema_Deploy SHALL ejecutar en orden: deploy CDK stack, deploy Text Agent, deploy BidiAgent, deploy frontend
2. WHEN se ejecuta `make deploy-all`, THE Sistema_Deploy SHALL pasar automáticamente el ARN del Text Agent como variable de entorno `TEXT_AGENT_ARN` al deploy del BidiAgent
3. IF algún paso de `make deploy-all` falla, THEN THE Sistema_Deploy SHALL detener la ejecución y reportar cuál paso falló con el código de salida del proceso
4. WHEN se ejecuta `make destroy`, THE Sistema_Deploy SHALL destruir en orden: BidiAgent, Text Agent, CDK stack
5. WHEN se ejecuta `make destroy`, THE Sistema_Deploy SHALL pedir confirmación interactiva antes de proceder con la destrucción
6. THE Sistema_Deploy SHALL documentar las dependencias entre pasos en comentarios del Makefile

### Requirement 8 — Auto-wiring de TEXT_AGENT_ARN en BidiAgent

**User Story:** Como desarrollador, quiero que el deploy del BidiAgent reciba automáticamente el ARN del Text Agent sin configuración manual, para eliminar un paso propenso a errores.

#### Acceptance Criteria

1. WHEN se despliega el BidiAgent, THE Sistema_Deploy SHALL obtener el ARN del Text Agent desde el output de `agentcore status` ejecutado en el directorio `agentcore/`
2. WHEN se despliega el BidiAgent, THE Sistema_Deploy SHALL pasar el ARN obtenido como variable de entorno `-env TEXT_AGENT_ARN=<arn>` al comando `agentcore deploy` del BidiAgent
3. IF el Text Agent no está desplegado al momento de deployar el BidiAgent, THEN THE Sistema_Deploy SHALL mostrar un error indicando que se debe deployar el Text Agent primero


### Requirement 9 — Test E2E con Playwright

**User Story:** Como desarrollador, quiero un test E2E que valide el flujo completo (login, chat, dashboard), para tener confianza de que la plataforma funciona de punta a punta después de cada deploy.

#### Acceptance Criteria

1. WHEN se ejecuta `make e2e-test`, THE Sistema_E2E SHALL ejecutar un test Playwright que realice login con credenciales de usuario demo
2. WHEN el login es exitoso, THE Sistema_E2E SHALL verificar que el dashboard renderiza al menos una tarjeta con datos (DataGrid o tabla visible)
3. WHEN el dashboard está cargado, THE Sistema_E2E SHALL enviar un mensaje al chat y verificar que se recibe una respuesta del agente
4. WHEN el chat responde, THE Sistema_E2E SHALL verificar que los Suggestion_Chips se muestran correctamente antes del primer mensaje
5. THE Sistema_E2E SHALL capturar un screenshot del dashboard en cada ejecución y guardarlo en `e2e/screenshots/`
6. THE Sistema_E2E SHALL completar la ejecución completa en menos de 60 segundos en condiciones normales de red
7. IF el login falla, THEN THE Sistema_E2E SHALL reportar el error con un mensaje claro indicando que las credenciales demo son inválidas o el servicio no está disponible
8. THE Sistema_E2E SHALL ser invocable con `make e2e-test` desde la raíz del proyecto sin configuración adicional más allá de las variables en `.env`
