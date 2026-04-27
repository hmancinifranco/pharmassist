# Requirements Document — Asistente APM (PharmAssist)

## Introduction

PharmAssist "Asistente APM" es una webapp responsive (mobile-first) que funciona como panel único de control para Agentes de Propaganda Médica (APMs) de Megalabs Argentina. Combina tarjetas contextuales (visitas del día, cumpleaños, alertas SLA) con un chat conversacional estilo ChatGPT respaldado por agentes Strands + Amazon Bedrock. El APM abre la app y ve todo de un vistazo: agenda, alertas y acceso al asistente inteligente para consultas de CRM, ventas y preparación de visitas.

## Glossary

- **APM**: Agente de Propaganda Médica (visitador médico). Usuario principal de la aplicación.
- **Asistente**: Agente conversacional IA (Strands + Bedrock Claude Opus 4.6) que responde consultas del APM en lenguaje natural.
- **Dashboard**: Pantalla principal "Single Pane of Glass" con tarjetas contextuales y chat.
- **Tarjeta_Contextual**: Componente visual compacto en la parte superior del Dashboard que muestra información resumida (visitas, cumpleaños, alertas).
- **Chat_Panel**: Panel de conversación estilo ChatGPT donde el APM interactúa con el Asistente.
- **FAB**: Floating Action Button para acceder al Chat_Panel en vista móvil.
- **Médico**: Profesional de la salud registrado en el CRM con matrícula nacional (Medico_MN).
- **CRM**: Tabla de datos de médicos (crm_medicos) con información personal, profesional y de asignación.
- **Cadencia**: Frecuencia esperada de visitas a un médico: Mensual (1/mes), Trimestral (1/3 meses), Semestral (1/6 meses), Anual (1/año), Digital (1/2 meses, solo virtual/telefónica).
- **Visita_Planificada**: Registro en la tabla de agenda generado automáticamente a partir de la cadencia del médico y la asignación APM-Médico.
- **SLA_Visita**: Acuerdo de nivel de servicio que define el plazo máximo entre visitas según la cadencia del médico.
- **Zona**: Área geográfica de cobertura comercial (ej: Recoleta-Norte, Belgrano-R). Las ventas se reportan por zona.
- **Crecimiento_YoY_Pct**: Porcentaje de crecimiento interanual de ventas de un producto en una zona.
- **Tipo_Visita**: Modalidad de la visita: Presencial, Virtual o Telefónica.
- **Productos_Presentados**: Lista de productos del portfolio Megalabs discutidos durante una visita, separados por `|`.
- **Brief_Médico**: Perfil enriquecido de un médico que combina datos internos del CRM con información pública (publicaciones, hospital, especialización).
- **Minuta_Visita**: Resumen estructurado generado por IA a partir de una nota de voz post-visita.
- **Transcripción**: Texto generado por Amazon Transcribe a partir de audio grabado por el APM.
- **Generador_IA**: Componente que usa Amazon Bedrock (Claude Opus 4.6) para generar texto estructurado (minutas, briefs, mensajes de cumpleaños).
- **Grabador_Audio**: Componente del frontend que captura audio desde el micrófono del dispositivo.
- **Buscador_Web**: Herramienta del agente Strands que busca información pública de un médico en internet.
- **Mensaje_Cumpleaños**: Mensaje de saludo personalizado generado por IA (Bedrock Claude Opus 4.6) para felicitar a un médico por su cumpleaños, basado en datos del CRM (Hobby_Intereses, Religion, Especialidad_Medica y otros datos personales relevantes).
- **WhatsApp_DeepLink**: URL con formato `https://wa.me/{phone_digits}?text={encoded_message}` que abre WhatsApp con un número de teléfono y mensaje pre-cargado. El número se limpia de espacios, guiones y prefijos no numéricos.

## Requirements

### Requirement 1: Visitas Planificadas para Hoy

**User Story:** As an APM, I want to see my planned visits for today on the Dashboard and ask the Asistente about them, so that I can organize my workday efficiently.

#### Acceptance Criteria

1. WHEN the APM opens the Dashboard, THE Tarjeta_Contextual SHALL display the list of Visitas_Planificadas for the current date filtered by the logged-in APM.
2. THE Tarjeta_Contextual SHALL display for each Visita_Planificada the doctor name, address (Calle + Altura, Barrio), Especialidad_Medica, and Productos_Presentados to discuss.
3. WHEN the APM taps a Visita_Planificada address, THE Dashboard SHALL open the address coordinates (Latitud, Longitud) in Google Maps using the URL scheme `https://www.google.com/maps/search/?api=1&query={Latitud},{Longitud}`.
4. WHEN the APM asks "¿Cuáles son mis visitas planificadas para hoy?" in the Chat_Panel, THE Asistente SHALL query the Visitas_Planificadas table and return the same list with doctor name, address, specialty, and products.
5. WHILE a Médico has Cadencia "Digital", THE Visita_Planificada SHALL have Tipo_Visita set to "Virtual" or "Telefónica" and SHALL NOT be scheduled as "Presencial".
6. THE system SHALL generate Visitas_Planificadas from the CRM cadence data distributing visits so that each APM has between 3 and 5 planned visits per day across working days of the month.
7. IF no Visitas_Planificadas exist for the current date, THEN THE Tarjeta_Contextual SHALL display the message "No tenés visitas planificadas para hoy".

### Requirement 2: Ventas Bajando en Zonas Asignadas

**User Story:** As an APM, I want to identify products with declining sales in my assigned zones, so that I can prioritize corrective actions and focus my visits on underperforming products.

#### Acceptance Criteria

1. WHEN the APM asks "¿Qué ventas bajaron en mis zonas asignadas?" in the Chat_Panel, THE Asistente SHALL query the ventas_reportadas data filtered by the zones assigned to the logged-in APM.
2. THE Asistente SHALL return only products where Crecimiento_YoY_Pct is negative, sorted by Crecimiento_YoY_Pct ascending (most severe decline first).
3. THE Asistente SHALL display for each declining product: Producto name, Presentacion, Zona, Unidades_Vendidas, Valor_Venta_ARS, and Crecimiento_YoY_Pct.
4. THE Asistente SHALL determine the APM's assigned zones by querying the CRM for all distinct Zona values of Médicos assigned to the logged-in APM.
5. IF no products have negative Crecimiento_YoY_Pct in the APM's zones, THEN THE Asistente SHALL respond with "No se detectaron caídas de ventas en tus zonas asignadas".
6. WHEN the APM asks about sales for a specific product or zone, THE Asistente SHALL filter results accordingly and include the Crecimiento_YoY_Pct and Valor_Venta_ARS for the requested scope.

### Requirement 3: Notas de Voz → Minuta de Visita

**User Story:** As an APM, I want to record a voice note after a visit and have the system generate a structured visit summary, so that I can document visits hands-free while in the field.

#### Acceptance Criteria

1. WHEN the APM activates the Grabador_Audio, THE Dashboard SHALL capture audio from the device microphone using the browser MediaRecorder API.
2. WHEN the APM stops the recording, THE Dashboard SHALL send the audio to Amazon Transcribe for speech-to-text conversion in Spanish (es-ES locale).
3. WHEN the Transcripción is complete, THE Generador_IA SHALL process the transcribed text and generate a Minuta_Visita containing: summary paragraph, products discussed, commitments made, and next steps.
4. THE Dashboard SHALL allow the APM to associate the Minuta_Visita with a specific Médico from the APM's assigned portfolio by selecting the doctor before or after recording.
5. THE Dashboard SHALL display the generated Minuta_Visita for APM review before saving.
6. IF the Transcripción fails or produces empty text, THEN THE Dashboard SHALL display an error message "No se pudo transcribir el audio. Intentá de nuevo." and allow the APM to re-record.
7. IF the audio recording duration is less than 3 seconds, THEN THE Dashboard SHALL display the message "La grabación es muy corta. Grabá al menos 3 segundos." and discard the recording.

### Requirement 4: Cumpleaños Próximos

**User Story:** As an APM, I want to see upcoming birthdays of doctors in my portfolio, so that I can strengthen professional relationships with timely greetings.

#### Acceptance Criteria

1. WHEN the APM opens the Dashboard, THE Tarjeta_Contextual SHALL display Médicos from the APM's assigned portfolio whose Fecha_Nacimiento falls within the next 30 calendar days.
2. THE Tarjeta_Contextual SHALL display for each upcoming birthday: doctor full name (Nombre + Apellido), Especialidad_Medica, birthday date (day and month), and number of days until the birthday.
3. THE Tarjeta_Contextual SHALL sort upcoming birthdays by proximity (nearest birthday first).
4. WHEN the APM taps a doctor name in the birthday Tarjeta_Contextual, THE Dashboard SHALL trigger a Brief_Médico request for that doctor in the Chat_Panel.
5. IF no Médicos in the APM's portfolio have birthdays in the next 30 days, THEN THE Tarjeta_Contextual SHALL display the message "No hay cumpleaños próximos en los próximos 30 días".
6. THE Tarjeta_Contextual SHALL display a "Enviar WhatsApp" button for each upcoming birthday entry.
7. WHEN the birthday Tarjeta_Contextual is rendered, THE Generador_IA SHALL generate a Mensaje_Cumpleaños for each Médico using Amazon Bedrock (Claude Opus 4.6), personalizing the message based on the Médico's Hobby_Intereses, Religion, Especialidad_Medica, and other relevant CRM data (Nombre, Apellido, Hospital, Facultad).
8. THE Generador_IA SHALL produce a Mensaje_Cumpleaños that is warm, professional, written in Spanish argentino, and references the Médico's interests or hobbies naturally within the greeting.
9. WHEN the APM taps the "Enviar WhatsApp" button, THE Dashboard SHALL clean the Médico's Telefono_Celular by removing all non-digit characters (spaces, dashes, plus sign) from the CRM format "+54 9 11 XXXX-XXXX" to produce a digits-only string.
10. WHEN the APM taps the "Enviar WhatsApp" button, THE Dashboard SHALL open a WhatsApp_DeepLink with format `https://wa.me/{cleaned_phone}?text={url_encoded_message}` where cleaned_phone is the digits-only phone number and url_encoded_message is the generated Mensaje_Cumpleaños encoded with URL encoding.
11. IF the Médico has no Telefono_Celular recorded in the CRM, THEN THE Tarjeta_Contextual SHALL disable the "Enviar WhatsApp" button and display the tooltip "Sin número de celular registrado".

### Requirement 5: Brief de Médico

**User Story:** As an APM, I want to request a comprehensive doctor profile combining internal CRM data and public information, so that I can prepare effectively for visits.

#### Acceptance Criteria

1. WHEN the APM asks "Dame un brief sobre el Dr. [Nombre]" in the Chat_Panel, THE Asistente SHALL search the CRM for the Médico matching the provided name.
2. THE Asistente SHALL include in the Brief_Médico the following CRM data: full name, Medico_MN, Especialidad_Medica, Hospital, Facultad, Anio_Egresado, Hobby_Intereses, Religion, Cadencia, Fecha_Ultima_Visita, and Zona.
3. THE Buscador_Web SHALL search the internet for public information about the Médico including: recent publications, areas of specialization, hospital affiliations, and professional achievements.
4. THE Generador_IA SHALL combine CRM data and web search results into a structured Brief_Médico with sections: Professional Profile, Visit History Summary, Rapport Suggestions (based on hobbies, interests), and Recommended Products (based on specialty).
5. THE Asistente SHALL include in the Brief_Médico a summary of past visits from apm_visitas: total visit count, last visit date, products previously presented, and visit type distribution (Presencial/Virtual/Telefónica).
6. IF the Médico name matches multiple records in the CRM, THEN THE Asistente SHALL present the matching doctors with Medico_MN, Especialidad_Medica, and Zona, and ask the APM to select one.
7. IF the Médico is not found in the CRM, THEN THE Asistente SHALL respond with "No se encontró un médico con ese nombre en tu cartera."
8. THE Asistente SHALL only return Brief_Médico data for Médicos assigned to the logged-in APM.

### Requirement 6: Alertas de SLA de Visitas

**User Story:** As an APM, I want to see alerts for doctors whose visit cadence SLA has not been met, so that I can prioritize overdue visits and maintain compliance.

#### Acceptance Criteria

1. WHEN the APM opens the Dashboard, THE Tarjeta_Contextual SHALL display Médicos from the APM's portfolio where the time since Fecha_Ultima_Visita exceeds the expected interval defined by the Médico's Cadencia.
2. THE system SHALL calculate SLA breach using these cadence intervals: Mensual = 30 days, Trimestral = 90 days, Semestral = 180 days, Anual = 365 days, Digital = 60 days.
3. THE Tarjeta_Contextual SHALL display for each SLA alert: doctor full name, Especialidad_Medica, Cadencia, Fecha_Ultima_Visita, days overdue (days since last visit minus expected interval), and Zona.
4. THE Tarjeta_Contextual SHALL sort SLA alerts by days overdue descending (most overdue first).
5. WHEN the APM taps a doctor in the SLA alert Tarjeta_Contextual, THE Dashboard SHALL trigger a Brief_Médico request for that doctor in the Chat_Panel.
6. WHILE a Médico has no Fecha_Ultima_Visita recorded (empty field in CRM), THE system SHALL treat the Médico as overdue and display the alert with the message "Sin visitas registradas".
7. IF no Médicos in the APM's portfolio have SLA breaches, THEN THE Tarjeta_Contextual SHALL display the message "Todas las visitas están al día. ¡Buen trabajo!".

### Requirement 7: Dashboard Single Pane of Glass

**User Story:** As an APM, I want a single main screen that shows all contextual information and chat access, so that I can work efficiently without navigating between multiple pages.

#### Acceptance Criteria

1. THE Dashboard SHALL render as a single screen with no side menus or complex navigation, following a "Single Pane of Glass" design.
2. THE Dashboard SHALL display Tarjetas_Contextuales at the top of the screen showing: today's planned visits (Req 1), upcoming birthdays (Req 4), and SLA alerts (Req 6).
3. THE Dashboard SHALL display the Chat_Panel in the center/bottom area of the screen for natural language interaction with the Asistente.
4. WHILE the viewport width is less than 600px (mobile), THE Dashboard SHALL stack Tarjetas_Contextuales vertically with scroll and display the Chat_Panel accessible via a FAB at the bottom-right corner.
5. WHILE the viewport width is 600px or greater (tablet/desktop), THE Dashboard SHALL display Tarjetas_Contextuales in a horizontal row and the Chat_Panel below them.
6. THE Dashboard SHALL use Material UI components with a responsive layout optimized for mobile-first usage.
7. THE Dashboard SHALL identify the logged-in APM and filter all displayed data (visits, doctors, sales, alerts) to show only data assigned to that APM.

### Requirement 8: Agente Conversacional con Strands

**User Story:** As an APM, I want to interact with an intelligent assistant via natural language in Spanish, so that I can query CRM, visits, and sales data conversationally.

#### Acceptance Criteria

1. THE Chat_Panel SHALL accept free-text input in Spanish and send messages to the Asistente backend.
2. THE Asistente SHALL use Strands Agents SDK with Amazon Bedrock (Claude Opus 4.6, model ID `anthropic.claude-opus-4-6-20250514-v1:0`) as the default model to interpret APM queries and invoke appropriate tools.
3. THE Asistente SHALL respond in Spanish argentino using informal "vos" form and pharmaceutical domain terminology.
4. WHEN the APM sends a message, THE Chat_Panel SHALL display a loading indicator until the Asistente responds.
5. THE Asistente SHALL maintain conversation context within a session so the APM can ask follow-up questions referencing previous responses.
6. IF the Asistente cannot interpret the query or no relevant data is found, THEN THE Asistente SHALL respond with a helpful message suggesting alternative queries the APM can try.
7. THE Asistente SHALL use dedicated Strands tools for each data domain: CRM/médicos tools, visitas tools, and ventas tools.

### Requirement 9: Generación de Agenda de Visitas Planificadas

**User Story:** As a system administrator, I want the system to auto-generate a planned visits calendar from CRM cadence data, so that APMs have a pre-populated daily agenda.

#### Acceptance Criteria

1. THE system SHALL generate Visitas_Planificadas for each Médico based on the Cadencia field: Mensual generates 1 visit per month, Trimestral generates 1 visit every 3 months, Semestral generates 1 every 6 months, Anual generates 1 per year, Digital generates 1 every 2 months.
2. THE system SHALL distribute Visitas_Planificadas across working days (Monday to Friday) of each month so that each APM has between 3 and 5 planned visits per day.
3. THE system SHALL assign each Visita_Planificada to the APM listed in the Médico's APM field in the CRM.
4. WHILE a Médico has Cadencia "Digital", THE system SHALL set the Tipo_Visita of generated Visitas_Planificadas to "Virtual" or "Telefónica".
5. THE system SHALL store generated Visitas_Planificadas with fields: APM, Medico_MN, Fecha_Planificada, Zona, Tipo_Visita, and Productos_Sugeridos (based on doctor specialty and Megalabs portfolio).
6. THE system SHALL populate Productos_Sugeridos based on the mapping between the Médico's Especialidad_Medica and the Megalabs product catalog.

### Requirement 10: Seguridad y Privacidad de Datos

**User Story:** As an APM, I want my data and my doctors' data to be private and only visible to me, so that sensitive information is protected.

#### Acceptance Criteria

1. THE Dashboard SHALL filter all data queries (médicos, visitas, ventas, alertas) by the logged-in APM identity.
2. THE Asistente SHALL only return Médico sensitive data (Telefono_Consultorio, Telefono_Celular, Mail) for Médicos assigned to the requesting APM.
3. THE system SHALL process all AI operations (transcription, brief generation, chat) through Amazon Bedrock and Amazon Transcribe within the controlled AWS infrastructure.
4. IF an APM queries data for a Médico not in the APM's assigned portfolio, THEN THE Asistente SHALL respond with "No tenés acceso a la información de ese médico."
