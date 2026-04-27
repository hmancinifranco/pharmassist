---
inclusion: always
---

# Producto — PharmAssist

## Visión

PharmAssist es un asistente inteligente para Agentes de Propaganda Médica (APMs / visitadores médicos) de una farmacéutica argentina. Combina datos de CRM, historial de visitas y ventas con agentes de IA (Strands + Bedrock) para ayudar al APM a planificar visitas, preparar reuniones con médicos y analizar el desempeño comercial de su zona.

## Principios de Producto

1. **Centrado en el APM**: Todo gira alrededor del día a día del visitador médico — su agenda, sus médicos, sus productos
2. **Datos reales**: Trabaja con los CSVs reales del laboratorio (CRM, visitas, ventas). No datos inventados.
3. **IA conversacional**: El APM interactúa con un chat inteligente que entiende el contexto farmacéutico argentino
4. **Accionable**: Cada respuesta del asistente debe ser útil y concreta — no genérica
5. **Privacidad**: Los datos de médicos y ventas no salen de la infraestructura controlada (Bedrock, no APIs externas)

## Usuarios Target

- APMs (Agentes de Propaganda Médica) de la farmacéutica
- Gerentes de zona que supervisan equipos de APMs
- Dirección comercial que necesita visibilidad del desempeño

## Flujos Principales (MVP)

### 1. Dashboard del APM
- El APM ve un resumen de su zona: médicos asignados, visitas recientes, próximas visitas sugeridas
- KPIs: cobertura de médicos, frecuencia de visitas vs cadencia, productos más presentados
- Alertas: médicos sin visitar según su cadencia, productos con caída de ventas en la zona

### 2. Chat con el Asistente IA
- El APM escribe consultas en lenguaje natural en español
- Ejemplos:
  - "¿Cuándo fue la última vez que visité al Dr. Herrera?"
  - "¿Qué médicos de Belgrano no visité en los últimos 3 meses?"
  - "Dame un resumen de ventas de PAMOXET en mi zona"
  - "Preparame talking points para visitar a la Dra. Peralta que es gastroenteróloga"
  - "¿Qué productos debería presentarle al Dr. Molina en la próxima visita?"
- El agente Strands consulta las herramientas apropiadas y responde con datos reales

### 3. Perfil de Médico
- Vista detallada de un médico: datos personales, especialidad, hospital, historial de visitas, productos presentados
- Intereses y hobbies (para rapport)
- Sugerencia de próxima visita basada en cadencia
- Ventas de productos relevantes en la zona del médico

### 4. Análisis de Ventas
- Dashboard de ventas por zona, producto, período
- Comparación YoY (crecimiento)
- Identificación de productos con oportunidad (baja penetración, alta demanda)
- Filtros por tipo OTC/RX, presentación, farmacia

### 5. Planificación de Visitas
- Sugerencia automática de agenda semanal basada en:
  - Cadencia de cada médico (mensual, trimestral, semestral, anual, digital)
  - Última fecha de visita
  - Prioridad por ventas en la zona
- El APM puede aceptar, modificar o rechazar sugerencias

## Modelo de Datos

### Médico (crm_medicos.csv)
Matrícula Nacional (MN), nombre, apellido, email, teléfonos, especialidad, dirección, zona, cadencia de visita, hospital, facultad, APM asignado, intereses/hobbies, religión, coordenadas

### Visita (apm_visitas.csv)
ID, APM, médico (MN), fecha, zona, tipo (Presencial/Virtual/Telefónica), productos presentados, notas

### Venta (ventas_reportadas.csv)
Año, mes, zona, producto, presentación, tipo OTC/RX, unidades vendidas, valor en ARS, crecimiento YoY%, farmacia

## Reglas de Negocio

- Un APM solo ve los médicos que tiene asignados
- La cadencia define la frecuencia esperada de visitas: Mensual, Trimestral, Semestral, Anual, Digital (solo contenido online)
- Los productos se presentan según la especialidad del médico y el portfolio del laboratorio
- Las ventas son por zona, no por médico individual (el médico no compra, prescribe)
- El tipo de visita puede ser Presencial, Virtual o Telefónica
- Los datos sensibles de médicos (teléfono, email) solo son visibles para el APM asignado

## Métricas de Éxito (MVP)

- El APM puede consultar su cartera de médicos y obtener respuestas útiles en < 5 segundos
- El chat responde correctamente consultas sobre visitas, ventas y médicos con datos reales
- El dashboard muestra KPIs relevantes para la gestión diaria del APM
- La planificación de visitas sugiere una agenda coherente con las cadencias

## Consideraciones de UX

- Interfaz en español argentino
- Material UI con tema personalizado (colores del laboratorio)
- Responsive pero optimizado para desktop (el APM trabaja desde notebook)
- Dark mode opcional
- Chat como componente central, siempre accesible
- Tablas con filtros, ordenamiento y exportación (MUI X Data Grid)
- Carga de datos desde CSVs (no requiere base de datos externa para MVP)
