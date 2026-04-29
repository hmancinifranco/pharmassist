# Caso de estudio: De Demo a MLP — PharmAssist para la industria farmacéutica

> Cómo convertir la demo actual de PharmAssist en un Minimum Lovable Product productivo capaz de responder preguntas de alto valor para Agentes de Propaganda Médica (APMs), cruzando múltiples fuentes de datos corporativas y externas de la industria farmacéutica, con latencias aceptables y una experiencia de usuario moderna.

## Índice

- [El caso de estudio](#el-caso-de-estudio)
- [Las 3 fuentes de datos de la industria pharma](#las-3-fuentes-de-datos-de-la-industria-pharma)
- [Las preguntas que generan valor real](#las-preguntas-que-generan-valor-real)
- [Por qué la demo actual no alcanza](#por-qué-la-demo-actual-no-alcanza)
- [Principios de diseño del MLP](#principios-de-diseño-del-mlp)
- [Arquitectura objetivo](#arquitectura-objetivo)
- [Los 3 carriles de respuesta](#los-3-carriles-de-respuesta)
- [Ingesta: warehouse externo → AWS](#ingesta-warehouse-externo--aws)
- [Almacenamiento: data lake con 3 dominios](#almacenamiento-data-lake-con-3-dominios)
- [Capa semántica: el agente entiende el negocio](#capa-semántica-el-agente-entiende-el-negocio)
- [Experiencia async para análisis profundo](#experiencia-async-para-análisis-profundo)
- [Expectativas de latencia y cómo planificarlas](#expectativas-de-latencia-y-cómo-planificarlas)
- [Plan de evolución por fases](#plan-de-evolución-por-fases)
- [Elección de modelo](#elección-de-modelo)

---

## El caso de estudio

La demo actual de PharmAssist usa un atajo didáctico: tres CSVs sintéticos (CRM, visitas, ventas) cargados directamente en DynamoDB, con un único APM (Peccy) y 12 médicos asignados. Sirve para validar la experiencia de usuario, el stack de agentes, el modo voz con Nova Sonic y la integración con AgentCore.

En un entorno productivo real de la industria farmacéutica, el escenario cambia en múltiples dimensiones simultáneamente. Este documento describe cómo evolucionar el diseño para soportar un laboratorio real con cientos de APMs, datos corporativos vivos consolidados desde múltiples fuentes, y preguntas de negocio que hoy ningún tablero resuelve.

### Perfil del caso

- **Industria**: laboratorio farmacéutico argentino de mediano o gran porte
- **Usuarios**: 200–500 APMs (visitadores médicos) distribuidos geográficamente
- **Escenario**: los APMs preparan su agenda del día siguiente desde sus notebooks, en horario laboral o nocturno. Expectativa de datos a día vencido (batch nocturno aceptable)
- **Fuentes de datos existentes**: 3 warehouses/datasets externos a AWS, cada uno en su propia plataforma (típicamente SQL Server, Synapse, Databricks o similar)
- **Patrón de uso**: mixto. El APM consulta datos puntuales (quién, dónde, cuándo), hace preguntas analíticas (rankings, tendencias, comparativos) y ocasionalmente pide análisis profundos multi-fuente ("qué médicos crecen en prescripción de mis productos foco y los estoy visitando poco")

### Objetivo del MLP

Construir un asistente conversacional que:

1. Responda preguntas **rápidas** (<500 ms data side) con la misma velocidad que un dashboard
2. Responda preguntas **conversacionales** (2–5 segundos end-to-end) con análisis ad-hoc sobre datos frescos
3. Entregue **análisis profundos** cross-source (15–60 segundos) sin romper la experiencia del APM — vía experiencia asincrónica con notificación
4. Conserve la libertad del LLM de "hablar con los datos" — **no** pre-cocina respuestas
5. Tenga costo operativo predecible y escale linealmente con usuarios


---

## Las 3 fuentes de datos de la industria pharma

En la industria farmacéutica argentina (y latinoamericana) los laboratorios trabajan con una combinación típica de **1 fuente interna + 2 fuentes externas estándar de la industria**. Cada una aporta un tipo distinto de información y los datos solo cobran sentido cuando se cruzan entre sí.

### Fuente 1 — Sistema interno (CRM + gestión de visitas)

Es el sistema propio del laboratorio. Guarda todo lo que el laboratorio conoce y controla:

- **Cartera médica**: qué APM atiende a qué médicos
- **Agenda de visitas**: planificadas, realizadas, con tiempos y tipos
- **Muestras entregadas**: qué producto, qué cantidad, lote, fecha
- **Productos foco del ciclo actual**: qué promoción se está empujando por línea/región
- **Estructura del producto**: familia, línea, categoría (foco/hiperfoco), ciclos de promoción, grillas
- **Perfil del médico**: datos personales, especialidad, hobbies, matrícula

**Tamaño típico**: tablas pequeñas-medianas (miles a decenas de miles de rows por tabla). Schema normalizado con decenas de tablas relacionadas. Cambios diarios.

### Fuente 2 — Prescripciones (CloseUp / CUP)

[CloseUp](https://www.closeupsolutions.com/) es un proveedor externo estándar en pharma latinoamericana. Vende datasets de **prescripciones médicas** capturadas en farmacias. Es la única forma que tiene un laboratorio de saber qué recetan los médicos — incluido qué productos de competidores recetan.

Contiene:

- Tabla de **prescripciones** (fact table muy grande: decenas o centenas de millones de rows históricas)
- Maestros de **médicos con identificador propio** (CDGMED), distinto del identificador interno del laboratorio
- Maestros de **mercados** (agrupaciones de productos competidores en una misma categoría terapéutica)
- Tabla de **visitados/no visitados** por representante

**Tamaño típico**: fact table de prescripciones en el orden de los GB-TB. Schema dimensional (star schema clásico). Actualización mensual o quincenal.

### Fuente 3 — Ventas de mercado (IQVIA)

[IQVIA](https://www.iqvia.com/) es el proveedor global dominante de datos de mercado farmacéutico. Vende datasets de **ventas a farmacias y distribuidoras**, agregados por producto, droga, clase terapéutica, laboratorio, período y geografía.

Contiene:

- Fact table de **ventas valorizadas** (`fact_mercado_valor`) con unidades, dosis, valor en ARS y USD
- Dimensiones estándar: **droga, forma farmacéutica, presentación, laboratorio, clase terapéutica, combinación, período**
- Relaciones entre presentaciones y drogas/formas para poder agregar a distintos niveles

**Tamaño típico**: fact table grande (cientos de millones de rows). Schema dimensional puro. Actualización mensual.

### El desafío: las claves no coinciden entre fuentes

Las 3 fuentes **no comparten identificadores de productos ni de médicos**. Cada una usa su propia codificación:

- **Productos**: código interno del laboratorio (SKU propio) vs código CUP (de CloseUp) vs código EAN-11 o idProducto (de IQVIA)
- **Médicos**: id interno del CRM del laboratorio vs CDGMED de CloseUp (no hay intersección en IQVIA porque IQVIA no tiene nivel médico)

Para cruzar las 3 fuentes existen **tablas maestras de integración** (el típico `maestro_integrador_producto` y `maestro_medicos`) que mapean los IDs entre sí. **Estas tablas maestras son críticas** — sin ellas, ninguna pregunta cross-source es posible.


---

## Las preguntas que generan valor real

Los APMs hacen preguntas de **3 niveles de valor muy distintos**. Diseñar bien el sistema empieza por entender esa diferencia.

### Preguntas de bajo valor (un dashboard las resuelve)

Preguntas operativas, puntuales, con una sola fuente de datos. Hoy están en tableros estáticos que el APM consulta antes de salir. No son el diferencial del agente, pero **sí tienen que responder rápido** porque son las más frecuentes.

Ejemplos del patrón:

- *"¿Cuáles son mis objetivos de visita este mes?"*
- *"¿A qué médicos todavía no visité en el ciclo actual?"*
- *"¿Cuándo fue la última visita al Dr. X?"*
- *"¿Qué promocioné en la última visita al Dr. X?"*

**Fuentes involucradas**: solo el CRM interno del laboratorio.
**Patrón**: lookup por ID o filtro simple sobre cartera.
**Latencia esperada**: <2 segundos end-to-end.
**Frecuencia**: múltiples veces por día por APM.

### Preguntas de valor medio (el APM intuye la respuesta)

Preguntas donde el APM ya tiene cierta noción de la respuesta pero quiere confirmarla con datos, o donde quiere ver un ranking ordenado. Siguen siendo operativas pero agregan agregaciones.

Ejemplos del patrón:

- *"¿Cuáles son los médicos que visito con más/menos frecuencia?"*
- *"¿Cuáles son los 5 productos que más prescribe el Dr. X?"*
- *"¿Cuáles son los 5 productos de mi laboratorio que más prescribe el Dr. X?"*

**Fuentes involucradas**: CRM interno y/o prescripciones (CloseUp).
**Patrón**: agregación con group by + order + limit, típicamente acotada a un médico o un APM.
**Latencia esperada**: 2–5 segundos end-to-end.
**Frecuencia**: varias veces por semana.

### Preguntas de gran valor (el agente muestra lo que ningún dashboard puede)

Esta es la categoría donde el agente **justifica su existencia**. Son preguntas analíticas complejas que cruzan las 3 fuentes, requieren combinar prescripciones + cartera + productos foco + ventas de mercado, y devuelven insights accionables que hoy ningún APM puede obtener por sí mismo.

Ejemplos del patrón:

- *"Recomendame a qué médicos debería visitar según sus prescripciones y mis productos foco"* — cruza CRM interno (cartera + foco) con CloseUp (prescripciones) y la tabla maestra de productos
- *"¿Qué médicos vienen creciendo en prescripción de mis productos foco y los estoy visitando poco?"* — cruza frecuencia de visitas (CRM interno) con evolución trimestral de prescripciones (CloseUp)
- *"¿A qué médicos debería visitar primero para crecer con el producto X?"* — ranking sobre cartera cruzado con market share y evolución del médico
- *"¿En qué productos de mi laboratorio tengo Evolución Trimestral negativa en unidades, tomando todos los mercados que trabajo?"* — cruza mercados del APM (CRM interno) con ventas IQVIA
- *"De los medicamentos que le promociono / no le promociono al Dr. X, ¿cuál es el que más prescribe?"* — cruza agenda (CRM interno) con prescripciones (CloseUp)

**Fuentes involucradas**: las 3 en simultáneo, con joins multi-tabla vía maestros de integración.
**Patrón**: queries analíticas con varias agregaciones, ventanas temporales (YoY, evolución trimestral, MAT — Moving Annual Total), filtros por cartera del APM.
**Latencia esperada**: aquí está el giro — **15 a 60 segundos** si se hacen ad-hoc sobre los datasets completos. Esto fuerza una experiencia distinta (ver sección "Los 3 carriles").
**Frecuencia**: 1–3 veces por día por APM. Son preguntas "pensadas" que el APM hace cuando planifica su semana o prepara una visita estratégica.

### La conclusión operativa

Un sistema que intenta servir **las 3 categorías con la misma infraestructura** termina quedando corto para todas. Las preguntas de bajo valor se vuelven lentas. Las de gran valor quedan fuera de alcance. La manera de hacerlo bien es reconocer que son **3 productos en uno** y diseñar una arquitectura que los sirva con criterios propios.


---

## Por qué la demo actual no alcanza

La demo usa DynamoDB como única fuente. Eso funciona para el set de preguntas de Peccy (12 médicos sintéticos) pero se quiebra en producción por 4 razones concretas:

### 1. DynamoDB no hace joins

Todas las preguntas de gran valor requieren cruzar 2 o 3 fuentes. DynamoDB no soporta joins nativamente, y cada camino alternativo tiene problemas:

- **Denormalizar en una sola tabla**: el tamaño explota porque habría que replicar las prescripciones por cada médico × cada producto foco × cada mercado. Además, cada fuente se actualiza en cadencias distintas (mensual CloseUp, quincenal/mensual IQVIA, diario el CRM interno), lo que hace muy costoso mantener la denormalización consistente.
- **Hacer múltiples queries + hacer el join en la aplicación**: funciona para volúmenes chicos y relaciones simples. A escala de millones de prescripciones o para preguntas con varias dimensiones, esta estrategia deja de ser sostenible en latencia y en código.
- **Limitar el alcance del producto a preguntas sin cruces**: implicaría renunciar precisamente a las preguntas de gran valor, que son el principal diferenciador del asistente sobre un dashboard tradicional.

Por eso el diseño incorpora un engine SQL por encima del data lake. Es lo que permite servir las preguntas cruzadas sin sacrificar alcance ni UX.

### 2. DynamoDB no está diseñado para workloads analíticos sobre grandes volúmenes históricos

Este punto no es un tema de "DynamoDB es caro". Es un tema de propósito: la documentación oficial de AWS recomienda **no usar DynamoDB para workloads OLAP** y derivar esos workloads a servicios pensados para analytics.

- El whitepaper de AWS [Best Practices for Migrating from RDBMS to DynamoDB → Unsuitable workloads](https://docs.aws.amazon.com/whitepapers/latest/best-practices-for-migrating-from-rdbms-to-dynamodb/unsuitable-workloads.html) lista las aplicaciones **OLAP** como uno de los casos de uso que no conviene servir con DynamoDB por su modelo de datos dimensional y la falta de joins entre fact y dimension tables.
- La guía [Evaluate your DynamoDB table usage patterns](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/CostOptimization_TableUsagePatterns.html) recomienda explícitamente **exportar a S3 y consultar con Athena** cuando se necesitan queries analíticas sobre tablas grandes, en lugar de hacer Scans dentro de DynamoDB.
- El post del AWS Database Blog [SQL to NoSQL: Modernizing data access layer with Amazon DynamoDB](https://aws.amazon.com/blogs/database/sql-to-nosql-modernizing-data-access-layer-with-amazon-dynamodb/) sugiere derivar las "complex analytical queries or large-scale reporting needs" a **Amazon Redshift, Amazon Athena, o Amazon SageMaker Lakehouse**.

Con una fact table de prescripciones con decenas o centenas de millones de filas, y con la necesidad de cruzar fuentes heterogéneas en query time, el fit natural es un lake queryable (S3 + Iceberg + Athena o un warehouse tipo Redshift), no DynamoDB. Como consecuencia derivada, el costo también termina siendo menor: storage columnar sobre S3 con compresión y partitioning es órdenes de magnitud más barato que la misma tabla en DynamoDB. Pero el motivo principal de la decisión es de diseño, no de precio: **es servir cada tipo de query con el servicio que mejor se ajusta**.

### 3. Las tres fuentes cambian con frecuencias distintas

- CRM interno del laboratorio cambia varias veces por día
- CloseUp actualiza mensual o quincenalmente
- IQVIA actualiza mensualmente

Un único pipeline que refresca todo cada noche es subóptimo. Necesitamos pipelines separados con frecuencias propias.

### 4. El UX de las preguntas complejas se decide, no se asume

Cuando el agente cruza CRM interno + CloseUp + IQVIA para producir un ranking inteligente de médicos a visitar, el tiempo de respuesta depende del motor analítico, de cómo se descomponga la pregunta, del modelo de fundación y del volumen de datos. El [blog oficial de AWS sobre text-to-SQL con Amazon Bedrock](https://aws.amazon.com/blogs/machine-learning/text-to-sql-solution-powered-by-amazon-bedrock/) reporta ~3-5 segundos para queries SQL **simples** sobre Redshift con GraphRAG; para queries complejas el blog no publica un número y aclara que depende del caso.

Frente a eso, la pregunta de diseño no es "¿sincrónico o asincrónico?" sino **¿qué experiencia se quiere ofrecer para esta clase de pregunta?**:

- **Preguntas operativas del día a día** ("¿cuáles son mis visitas de hoy?", "últimos productos presentados al Dr. X"): el APM las hace entre visitas y necesita feedback inmediato con streaming visible. El UX tolera poco más de unos pocos segundos sin información visible en pantalla.
- **Preguntas planificadas de gran valor** ("¿a qué médicos visitar la semana que viene para crecer con producto X?"): el APM las hace al planificar la agenda. Tolera bien esperar más tiempo a cambio de un análisis de mayor profundidad, y puede seguir trabajando o recibir una notificación cuando el resultado esté listo.

#### Dos rutas arquitectónicas, ambas válidas

Sobre esa base, hay dos rutas razonables para el MLP, cada una con su propio tradeoff:

- **Ruta A — Athena-first con carril asincrónico para análisis profundos**. Athena es serverless, más económico y más simple de operar sobre el data lake. Para queries complejas multi-fuente puede demorar decenas de segundos, por lo que conviene complementarlo con un carril async (cola + worker + notificación) para preguntas planificadas de gran valor. El APM sigue trabajando mientras el análisis se procesa. Es una UX válida cuando el tipo de pregunta lo tolera.
- **Ruta B — Redshift-first con el patrón del blog oficial de AWS**. Redshift es column-oriented, paralelizable y más rápido para agregaciones grandes. Combinado con GraphRAG (Neptune + OpenSearch) para el contexto semántico, validación AST de SQL y parallel agent execution, el patrón permite que más preguntas se respondan sincrónicamente con streaming. Los datos exactos de latencia para queries complejas hay que medirlos en cada implementación.

Ninguna de las dos rutas es objetivamente mejor. La elección depende de:

1. **El mix real de preguntas** que hagan los APMs (qué porcentaje es operativo, cuánto es planificado).
2. **La UX que quiere darse** al APM para cada tipo de pregunta.
3. **El presupuesto de infraestructura** disponible en cada fase.
4. **La tolerancia a la complejidad operativa**: Redshift + Neptune + OpenSearch es más potente pero más piezas para mantener.

Este documento describe en detalle la **Ruta A** como implementación de referencia porque es la más simple y económica para validar el MLP, y permite migrar a la Ruta B más adelante con inversión incremental. La arquitectura de ingesta, la capa semántica y los principios de diseño se mantienen iguales en ambas rutas; cambia el motor analítico y, con él, la distribución sincrónica/asincrónica de las respuestas.

**Lo importante no es elegir la ruta de entrada en frío, sino reconocer que la decisión es empírica**: requiere un set de 15-20 preguntas representativas del APM, medirlas contra las dos rutas, y validar con el cliente cuál UX genera más valor para su equipo.

---

## Principios de diseño del MLP

Antes de entrar a la arquitectura, cinco principios que guían cada decisión:

### 1. El agente mantiene siempre libertad de razonamiento

No pre-cocinamos respuestas. El LLM decide qué tools invocar en cada pregunta. Lo que pre-computamos son **datos agregados** que los tools pueden leer. Si el APM hace una pregunta que no anticipamos, el agente la responde igual — solo con un poco más de latencia.

### 2. Hot, warm y async son carriles distintos con SLA distinto

Cada pregunta se clasifica en el momento de razonamiento del agente. El agente tiene tools de tres tipos; cada uno lee de su storage óptimo. No hay un tool "universal" que haga todo porque eso obliga a comprometer algún SLA.

### 3. El data lake es fuente única de verdad para analítica

Las 3 fuentes se replican a S3 como **tablas Iceberg independientes**. No las pre-joineamos durante la ingesta. Athena queryea las 3 según haga falta, con los maestros de integración. Esto deja el schema original intacto y fácil de debuggear.

### 4. Pre-computación agresiva pero selectiva

Las preguntas de medio y gran valor que sabemos que el APM hace **todos los días** se materializan en Redis/DynamoDB durante el batch nocturno. Así el 80% de las preguntas comunes responden en <500 ms. El 20% restante va ad-hoc a Athena.

### 5. Experiencia async para análisis profundos

Preguntas de gran valor que requieren 15–60 segundos de cómputo no bloquean al APM. Se despachan a un job, el APM recibe confirmación inmediata ("Analizando, te aviso cuando esté listo"), sigue navegando la app, y recibe una notificación push cuando el resultado está listo.


---

## Arquitectura objetivo

```mermaid
flowchart TB
    subgraph Ext["🏢 Fuentes de datos externas a AWS"]
        CRMINT[("Sistema interno<br/>del laboratorio<br/>CRM + visitas + foco")]
        CUP[("CloseUp<br/>Prescripciones")]
        IQVIA[("IQVIA<br/>Ventas de mercado")]
    end

    subgraph Ingest["📥 Ingesta (pipelines independientes)"]
        DMS1["DMS · nightly"]
        DMS2["DMS · monthly"]
        DMS3["DMS · monthly"]
    end

    subgraph Lake["🗂️ Data Lake — S3 Iceberg"]
        S3CRM[("CRM tables")]
        S3CUP[("CUP tables")]
        S3IQV[("IQVIA tables")]
        MAESTROS[("Maestros<br/>de integración")]
        GLUE["Glue Catalog<br/>+ ETL"]
    end

    subgraph Hot["⚡ Hot path"]
        DDB[("DynamoDB<br/>cartera + agenda + foco")]
    end

    subgraph Warm["♨️ Warm path"]
        REDIS[("ElastiCache Redis<br/>KPIs pre-computados")]
        ATHENA["Amazon Athena<br/>queries ad-hoc cross-source"]
    end

    subgraph Async["🧠 Análisis profundo (async)"]
        SQS["SQS queue"]
        WORKER["Lambda / Fargate<br/>worker de análisis"]
        STORE[("S3 + DynamoDB<br/>resultados")]
        SNS["SNS / WebSocket push<br/>notificación al APM"]
    end

    subgraph Agent["🤖 AgentCore + Strands"]
        AGT["Text Agent + semantic_layer.yaml"]
    end

    CRMINT --> DMS1 --> S3CRM
    CUP --> DMS2 --> S3CUP
    IQVIA --> DMS3 --> S3IQV

    S3CRM --> GLUE
    S3CUP --> GLUE
    S3IQV --> GLUE
    MAESTROS --> GLUE

    GLUE -->|nightly refill| DDB
    GLUE -->|nightly materialize KPIs| REDIS
    GLUE --> ATHENA

    AGT -->|carril instantáneo| DDB
    AGT -->|carril conversacional| REDIS
    AGT -->|carril conversacional fallback| ATHENA
    AGT -->|carril análisis profundo| SQS
    SQS --> WORKER
    WORKER --> ATHENA
    WORKER --> STORE
    WORKER --> SNS

    classDef ext fill:#6B7280,stroke:#374151,color:#fff
    classDef aws fill:#FF9900,stroke:#232F3E,color:#fff
    classDef data fill:#3F8624,stroke:#232F3E,color:#fff
    classDef agent fill:#8C4FFF,stroke:#232F3E,color:#fff
    classDef async fill:#DD344C,stroke:#232F3E,color:#fff

    class CRMINT,CUP,IQVIA ext
    class DMS1,DMS2,DMS3,ATHENA,GLUE aws
    class S3CRM,S3CUP,S3IQV,MAESTROS,DDB,REDIS data
    class AGT agent
    class SQS,WORKER,STORE,SNS async
```

### Piezas clave y qué hace cada una

| Componente | Rol | Cuándo se usa |
|---|---|---|
| **AWS DMS** (x3) | Replica cada fuente externa a S3 con su propia cadencia | Ingesta nocturna/mensual |
| **S3 + Apache Iceberg** | Almacena las 3 fuentes como tablas independientes, versionables, con schema evolution | Source of truth analítico |
| **Glue Data Catalog + ETL** | Indexa metadata, normaliza y prepara las tablas curadas | Una vez al día post-ingesta |
| **DynamoDB** | Vista materializada hot de cartera, agenda, productos foco, últimas visitas | Queries del carril instantáneo |
| **ElastiCache Redis** | KPIs pre-computados por APM (rankings, alertas, evolución propia) | Queries del carril conversacional |
| **Athena** | Engine SQL serverless sobre el lake, queryea las 3 fuentes con joins vía maestros | Carril conversacional (fallback) + carril async |
| **SQS + Worker (Lambda/Fargate)** | Cola de análisis profundos + worker que ejecuta queries multi-fuente largas | Carril async |
| **SNS / WebSocket push** | Notifica al APM cuando el análisis profundo termina | Cierre del carril async |
| **AgentCore Runtime** | Ejecuta el agente Strands con el LLM configurado vía Bedrock | Toda pregunta del APM |


---

## Los 3 carriles de respuesta

Cada pregunta del APM se resuelve por uno de estos 3 carriles. **El agente Strands decide cuál usar** según el tool que invoca. El APM no elige manualmente.

### Carril 1 — Instantáneo (<500 ms data, 2–3 s total)

**Para qué**: preguntas operativas y de bajo valor. Lookup por ID, filtro simple sobre cartera, últimas visitas.

**Cómo funciona**: el tool del agente lee directamente de DynamoDB, que tiene una vista pre-denormalizada del sistema interno (cartera, agenda, productos foco del APM, últimas visitas por médico). Refresh nocturno.

**Streaming sincrónico**: el agente streamea la respuesta por WebSocket como en la demo actual. El APM ve la respuesta aparecer palabra por palabra.

**Ejemplos de preguntas**:

- *"¿Cuándo fue la última visita al Dr. Peralta?"*
- *"¿Qué promocioné en la última visita?"*
- *"¿Cuántos médicos tengo asignados?"*
- *"¿Qué médicos tengo en Belgrano?"*
- *"¿Cuáles son mis visitas de hoy?"*

### Carril 2 — Conversacional (2–5 s total)

**Para qué**: preguntas de valor medio y algunas de gran valor que son frecuentes. Rankings, top-N, agregaciones acotadas al APM o a un médico específico.

**Cómo funciona (ruta feliz)**: el tool del agente intenta primero **Redis**. Si hay un KPI pre-computado que matchea la pregunta (ej. "top 5 productos más prescritos por el Dr. X en mi cartera"), lo devuelve en <10 ms. El KPI fue calculado durante el batch nocturno usando Athena + maestros de integración.

**Cómo funciona (ruta de fallback)**: si la pregunta es una variante del set pre-computado o el APM la hace sobre un médico/zona fuera del cache, el tool cae a **Athena**. Query típica de 1–3 segundos sobre Iceberg con partitioning. Opcionalmente el resultado se guarda en Redis con TTL corto para futuras consultas similares.

**Streaming sincrónico**: el agente streamea mientras espera. El agente puede empezar con un prefacio ("Déjame revisar tus prescripciones...") antes de invocar el tool, llenando el tiempo que el APM percibe.

**Ejemplos de preguntas**:

- *"¿Cuáles son los médicos que visito con menos frecuencia?"* (ranking sobre CRM interno)
- *"¿Cuáles son los 5 productos que más prescribe el Dr. X?"* (agregación sobre CloseUp)
- *"¿Cuáles son los 10 médicos más prescriptores en el mercado de cardiología?"* (ranking sobre CloseUp)
- *"¿En qué productos tengo EVO Trimestral negativa tomando todos mis mercados?"* (cruzando IQVIA con mercados del APM en el CRM interno)

### Carril 3 — Análisis profundo async (15–60 s total, con notificación)

**Para qué**: preguntas de gran valor que requieren cruzar las 3 fuentes con agregaciones complejas, ventanas temporales y rankings multi-criterio. Son preguntas "pensadas" que el APM hace cuando planifica.

**Cómo funciona**: cuando el agente detecta que la pregunta entra en esta categoría (lo decide el LLM basándose en descripciones de tools y la capa semántica), no ejecuta la query inline. En su lugar:

1. **Encola el trabajo** en SQS con el payload de la pregunta estructurada
2. **Responde inmediatamente** al APM por el WebSocket: *"Estoy analizando tu cartera cruzada con prescripciones y productos foco. Esto puede tardar hasta un minuto; te aviso cuando esté listo. Mientras tanto podés seguir trabajando."*
3. Un **worker separado** (Lambda de 10 min o Fargate task) toma el mensaje de SQS, ejecuta las queries Athena cross-source, procesa los resultados
4. El worker **guarda el resultado** en S3 (si es un reporte rich) y/o DynamoDB (si es corto)
5. **Notifica al APM** vía SNS push a la app o vía WebSocket (si sigue conectado) con un link al resultado
6. Cuando el APM abre el resultado, lo ve renderizado como una "tarjeta de análisis" — con tablas, gráficos, y opcionalmente un resumen generado por el agente

**No bloquea al APM**: el usuario puede hacer otras preguntas, navegar el dashboard, irse a una visita. El resultado lo espera cuando vuelve.

**Ejemplos de preguntas** (son preguntas que justifican toda la arquitectura):

- *"Recomendame a qué médicos debería visitar según sus prescripciones y mis productos foco"* — cruza cartera + foco (CRM interno) + prescripciones (CloseUp) + maestros + scoring
- *"¿Qué médicos vienen creciendo en prescripción de mis productos foco y los estoy visitando poco?"* — análisis YoY + frecuencia de visitas + productos foco
- *"¿A qué médicos debería visitar primero para crecer con el producto X?"* — ranking multi-criterio sobre toda la cartera
- *"De los medicamentos que le promociono al Dr. X, ¿cuál es el que más prescribe?"* — intersección agenda + prescripciones + integrador de productos

### Comparación rápida de los 3 carriles

| Dimensión | Instantáneo | Conversacional | Análisis profundo (async) |
|---|---|---|---|
| Storage | DynamoDB | Redis + Athena | Athena sobre Iceberg |
| Latencia data | <30 ms | 10 ms – 3 s | 10 – 50 s |
| Latencia total percibida | 2–3 s | 2–5 s | Inmediato (ack) + 15–60 s (notificación) |
| Conexión | WS streaming sync | WS streaming sync | WS ack + SNS push async |
| Patrón de query | GetItem / Query | KPI lookup / SQL acotado | SQL cross-source con joins |
| Fuentes típicas | 1 (CRM interno) | 1–2 | 3 con maestros |
| Frecuencia por APM | decenas/día | unas/día | 1–3/día |


---

## Ingesta: warehouse externo → AWS

Cada una de las 3 fuentes se replica a AWS con su propia cadencia. No hay un único pipeline universal; cada fuente tiene características propias.

### Sistema interno (CRM del laboratorio)

- **Origen**: base corporativa (típicamente SQL Server, Oracle, PostgreSQL). Schema normalizado con decenas de tablas.
- **Cadencia**: batch nocturno (las operaciones OLTP cierran al final del día)
- **Herramienta**: AWS DMS en modo Full Load o CDC
- **Destino**: S3 Iceberg particionado por `fecha_carga` (snapshot diario)
- **Particularidad**: hay vistas maestras construidas sobre el schema normalizado que ya denormalizan parte del trabajo. Podemos replicar las vistas directamente para simplificar el ETL.

### Prescripciones (CloseUp)

- **Origen**: dataset que CloseUp entrega mensual o quincenalmente. Puede llegar como archivos (Parquet, CSV) a un FTP/S3 del cliente, o como tablas en un warehouse compartido.
- **Cadencia**: mensual (a veces quincenal)
- **Herramienta**: si es archivos, una Lambda que detecta llegada y mueve a landing zone. Si es warehouse, DMS en modo Full Load mensual.
- **Destino**: S3 Iceberg particionado por `anio_mes`
- **Particularidad**: la fact table es grande. El ETL debe ser idempotente (si la carga se ejecuta dos veces, no duplica prescripciones).

### Ventas de mercado (IQVIA)

- **Origen**: IQVIA entrega el dataset mensualmente, típicamente como archivos comprimidos o vía su portal.
- **Cadencia**: mensual
- **Herramienta**: típicamente un cliente SFTP más un ingest Lambda que convierte a Parquet
- **Destino**: S3 Iceberg particionado por `anio_mes`
- **Particularidad**: el schema viene bien estructurado (dimensional star schema), requiere transformación mínima.

### Maestros de integración

Las tablas maestras (`maestro_integrador_producto`, `maestro_medicos`, `Familia_Interno_a_Marca_CUP`) son pequeñas pero **críticas**. Se cargan manualmente o vía script cuando cambian (baja frecuencia). Viven en S3 Iceberg como tablas chicas, queryeables vía Athena junto con las demás.

### AWS DMS: configuración

DMS se configura como una **replication instance** (EC2 managed) o como **DMS Serverless** (on-demand). Para el caso:

- **Serverless** para la carga del CRM interno: batch nocturno, con la instancia prendida solo durante la ventana de ingesta.
- **On-demand scheduled tasks** para CloseUp e IQVIA: se ejecutan una vez al mes coincidiendo con la cadencia de publicación de cada fuente.

La ventaja operativa es que DMS gestiona el state de replicación, el schema evolution y el handling de tipos de datos heterogéneos sin que haya que escribir código de ingesta. El pricing on-demand lo hace económico cuando la cadencia es baja.


---

## Almacenamiento: data lake con 3 dominios

Todo el histórico vive en **S3 como Apache Iceberg**, con 3 dominios separados + maestros. Las tablas nunca se pre-joinean durante la ingesta — eso ocurre en query time (Athena) o durante la materialización de KPIs (nightly job).

### Estructura del bucket

```
s3://pharmassist-lake/
├── crm/                      ← sistema interno, cadencia diaria
│   ├── cartera_medica/
│   ├── agenda/
│   ├── agenda_producto/
│   ├── familia_producto/
│   ├── detalle_promocion_producto/
│   ├── linea_apm/
│   ├── grilla/
│   └── ... (resto del schema del CRM interno)
├── cup/                      ← CloseUp, cadencia mensual
│   ├── medico/
│   ├── prescricao/          ← fact table grande
│   ├── mercados/
│   ├── mercados_productos/
│   └── marca/
├── iqvia/                    ← IQVIA, cadencia mensual
│   ├── dim_droga/
│   ├── dim_presentacion/
│   ├── dim_laboratorio/
│   ├── dim_periodo/
│   ├── fact_mercado_valor/  ← fact table grande
│   └── ... (resto del schema IQVIA)
└── maestros/                 ← tablas de integración, cadencia baja
    ├── maestro_integrador_producto/
    ├── maestro_medicos/
    └── familia_interno_a_marca_cup/
```

### Cómo se relacionan S3, Parquet e Iceberg

Antes de entrar al detalle de partitioning, conviene aclarar tres conceptos que suelen mezclarse:

- **Amazon S3** es el servicio de storage de objetos donde viven los archivos. Es la capa de persistencia.
- **Apache Parquet** es un formato de archivo **columnar**: guarda los datos agrupados por columna en lugar de por fila. Eso acelera muchísimo las queries analíticas que leen pocas columnas de tablas grandes, y comprime mejor que los formatos row-based. Un archivo `prescripciones.parquet` es eso: un archivo físico en S3 con ese formato interno.
- **Apache Iceberg** es un formato de **tabla abierto** que se construye por encima de muchos archivos Parquet. Iceberg agrega una capa de metadatos que transforma esa colección de archivos en algo que se comporta como una tabla de base de datos: con schema, transacciones ACID, evolución de schema y time travel.

En el data lake de PharmAssist, las tres capas conviven:

- Los datos físicos están en **S3** como archivos **Parquet** (compresión + lectura columnar).
- Esos archivos están organizados como tablas **Iceberg** (metadatos, versioning, schema evolution).
- Los engines de consulta (Athena, Redshift Spectrum, EMR) leen las tablas Iceberg sin replicar datos.

### Particionado para performance

El particionado es una técnica **independiente del formato** que divide los archivos de una tabla en subdirectorios según los valores de una o más columnas de alta selectividad. Se aplica tanto a Parquet directo como a tablas Iceberg, y es lo que hace que los engines de consulta puedan descartar grandes porciones de datos antes de leerlos (**partition pruning**).

Cada fact table del lake se particiona por las columnas que los APMs usan con más frecuencia en sus queries:

| Tabla | Particionado |
|---|---|
| `cup/prescricao` | `anio, mes, cdgreg_pmix` (región del APM) |
| `iqvia/fact_mercado_valor` | `idperiodo` (año-mes) |
| `crm/agenda` | `fecha_visita` |

La combinación de los tres elementos es la que hace eficientes las queries:

- **Parquet** hace que escanear una columna sea barato (no necesita leer las otras).
- **Iceberg** permite que el engine sepa qué archivos existen sin escanear S3.
- **Particionado** hace que el engine pueda saltar archivos completos que no contienen datos del período o región consultada.

Así, una query del estilo *"prescripciones del Dr. X en los últimos 12 meses"* escanea decenas de MB de un universo que podría ser de TB. Athena cobra por TB escaneado, por lo que queries bien particionadas son económicas por diseño.

### Por qué Iceberg y no solo Parquet

Si Parquet ya resuelve el problema del formato columnar, vale la pena explicar qué agrega Iceberg por encima:

- **Schema evolution**: cuando CloseUp agrega una columna nueva al mes siguiente, las queries existentes no se rompen. Iceberg maneja la coexistencia de versiones de schema.
- **Time travel**: se pueden consultar los datos tal como eran hace 3 meses, útil para auditar un insight o reproducir un análisis.
- **Transacciones ACID**: si el ETL falla en medio de una carga, el lake no queda en un estado inconsistente. La carga se commitea completa o no se ve.
- **Compactación automática**: con el tiempo, los archivos chicos se vuelven un problema de performance. Iceberg los compacta en archivos más grandes de forma administrada.
- **Engine agnóstico**: Athena, EMR, Redshift Spectrum, Databricks y otras herramientas leen la misma tabla Iceberg sin necesidad de replicar datos.

Con Parquet puro habría que resolver cada una de estas cosas a mano. Iceberg los trae incluidos.

### Glue Data Catalog

El catalog central que describe todas las tablas con su schema, ubicación, formato y particiones. Athena, Glue ETL, y cualquier herramienta de BI que el cliente conecte en el futuro usan este catalog como fuente de verdad del data lake.


---

## Capa semántica: el agente entiende el negocio

El LLM por sí solo no sabe qué es un "producto foco", cómo se calcula "Evolución Trimestral", ni que el `CDGMED` de CloseUp se cruza con el `id` de `doctor` del CRM interno vía la tabla `maestroMedicos`. La **capa semántica** es el artefacto que le enseña ese conocimiento de dominio.

### Qué contiene

Un archivo YAML (o colección de archivos) inyectado al system prompt del agente, con 4 bloques:

**1. Entidades del dominio** con sus atributos, tabla física y tags semánticos:

```yaml
entidades:
  Medico:
    descripcion: "Profesional de la salud visitado por un APM."
    id_interno: crm.doctor.id
    id_externo_prescripciones: cup.medico.CDGMED
    cruce: maestros.maestro_medicos (codInterno ↔ codCUP)
    atributos_clave:
      - especialidad: crm.doctor.especialidad_id → crm.especialidad.nombre
      - cartera_APM: crm.cartera_medica (apm_id → doctor_id)

  Producto:
    descripcion: "Producto farmacéutico del laboratorio o de competidores."
    id_laboratorio: crm.familia_producto.id
    id_closeup: cup.marca.codigo_marca
    id_iqvia: iqvia.dim_presentacion.idProducto
    cruce: maestros.maestro_integrador_producto
    categoria_comercial:
      - foco: detalle_promocion_producto.id_categoria = 'foco'
      - hiperfoco: detalle_promocion_producto.id_categoria = 'hiperfoco'
```

**2. Métricas del negocio** con su fórmula expresada en SQL o pseudocódigo:

```yaml
metricas:
  evolucion_trimestral_prescripciones:
    alias: [EVO_TRM, EVO trimestral]
    definicion: |
      Porcentaje de variación de prescripciones del trimestre actual vs
      el mismo trimestre del año anterior, por médico y producto/mercado.
    formula_pseudocodigo: |
      (px_trimestre_actual - px_trimestre_anterior_mismo_año)
      / px_trimestre_anterior_mismo_año * 100
    fuente: cup.prescricao
    ventana_temporal: trimestre vs trimestre Y-1

  productos_foco_del_apm:
    definicion: "Productos marcados como Foco o Hiperfoco en el ciclo activo para las líneas asignadas al APM."
    tablas: [crm.linea_apm, crm.grilla, crm.detalle_promocion_producto, crm.categoria, crm.ciclo]
    sql_template: |
      SELECT DISTINCT fp.*
      FROM crm.linea_apm la
      JOIN crm.grilla g ON g.id_linea = la.id_linea
      JOIN crm.detalle_promocion_producto dpp ON dpp.id_grilla = g.id
      JOIN crm.categoria c ON c.id = dpp.id_categoria
      JOIN crm.ciclo ci ON ci.id = dpp.id_ciclo
      JOIN crm.familia_producto fp ON fp.id = dpp.id_familia_producto
      WHERE la.apm_id = :apm_id
        AND c.nombre IN ('foco', 'hiperfoco')
        AND ci.activo = true
```

**3. Queries canónicas** — ejemplos de queries conocidas que el agente puede adaptar:

```yaml
queries_canonicas:
  ranking_medicos_prescriptores_en_mercado:
    pregunta_ejemplo: "Los 10 médicos más prescriptores en el mercado X"
    carril: conversacional
    sql: |
      SELECT m.CDGMED, m.nombre, SUM(p.cantidad) as px_total
      FROM cup.prescricao p
      JOIN cup.medico m ON m.CDGMED = p.CDGMED
      JOIN cup.mercados_productos mp ON mp.CDG_PROD = p.CDGPRO
      WHERE mp.CDG_MERCADO = :mercado_id
        AND p.DATA >= CURRENT_DATE - INTERVAL '12' MONTH
      GROUP BY m.CDGMED, m.nombre
      ORDER BY px_total DESC
      LIMIT 10
```

**4. Reglas del negocio** (las consideraciones del documento del cliente):

```yaml
reglas_negocio:
  - "Si un producto no tiene codProductoCUP, significa que no tuvo prescripciones."
  - "Si un producto no tiene codProductoBarrasEAN11 ni idProducto de IQVIA, no tuvo ventas."
  - "Un médico lo atiende el laboratorio solo si tiene codInterno en maestro_medicos."
  - "Los productos foco son a nivel APM (por sus líneas); los productos objetivo son a nivel médico."
  - "Para productos de promoción usar detalle_promocion_producto con categoria foco/hiperfoco."
```

### Cómo se inyecta

El `semantic_layer.yaml` se carga al iniciar el agente y se pasa como parte de su system prompt. Cuando el APM hace una pregunta, el agente tiene todo el contexto necesario para:

1. **Identificar qué entidades están involucradas** (médico, producto foco, prescripciones)
2. **Elegir qué tool invocar** (instantáneo, conversacional o async)
3. **Adaptar una query canónica** al contexto específico del APM
4. **Aplicar reglas de negocio** (filtros correctos, interpretaciones correctas de métricas)

### Por qué YAML es suficiente para el MLP

Para el MLP, un `semantic_layer.yaml` inyectado al prompt resuelve la necesidad sin infraestructura extra: versionable en Git, fácil de editar por un ingeniero de datos, y el agente lo entiende sin preparación especial. La capa semántica como YAML es un patrón probado en agentes text-to-SQL recientes.

Cuando el archivo crezca mucho (por ejemplo, supere los ~50 KB, o aparezcan más de 3 fuentes con relaciones complejas entre sí), conviene evaluar migrar a un **grafo semántico queryable**. Esa es una etapa posterior del roadmap y se decide con métricas de uso reales.

Algunas opciones para cuando llegue ese momento:

- **Amazon Neptune** — grafo gestionado por AWS, integra bien con el resto del stack. Es la opción obvia dentro de AWS pero agrega un costo fijo no trivial; hay que validar que el caso de uso justifica la inversión.
- **Apache AGE** — extensión de PostgreSQL que agrega capacidades de grafo sobre una base Postgres estándar.
- **Neo4j Community Edition** — open source, muy maduro en el mundo de grafos. Requiere operar una instancia (EC2 o ECS).
- **JanusGraph** — grafo distribuido open source, corre sobre Cassandra/HBase. Más complejo pero escala horizontalmente.

El MLP no incluye ninguno de estos: YAML es un buen punto de partida. La decisión de migrar se posterga hasta que exista una métrica concreta que la justifique (tamaño del YAML, cantidad de fuentes, patrones de consulta que pidan navegación de grafo).

### Validación del YAML

Un paso a menudo ignorado: testear que el agente con la capa semántica responde bien las 12 preguntas de referencia. Se arma un test suite que corre contra el agente con prompts conocidos y chequea que genera el SQL correcto (o invoca el tool correcto). Este test corre antes de cada redeploy del `semantic_layer.yaml`.


---

## Experiencia async para análisis profundo

Este es el patrón más importante de todo el MLP. Convierte las preguntas de gran valor en una experiencia aceptable, y es lo que diferencia al agente de un dashboard estático.

### Flujo detallado

```mermaid
sequenceDiagram
    actor APM
    participant SPA as Frontend SPA
    participant WS as WebSocket
    participant AGT as AgentCore
    participant Q as SQS
    participant W as Lambda Worker
    participant AT as Athena
    participant ST as DynamoDB + S3
    participant NT as SNS / Push

    APM->>SPA: "¿Qué médicos crecen en foco y los visito poco?"
    SPA->>WS: enviar prompt
    WS->>AGT: invocar agente
    AGT->>AGT: analiza pregunta, detecta que es carril async

    Note over AGT: Invoca tool despachar_analisis_profundo

    AGT->>Q: enqueue job_id + pregunta + apm_id + contexto
    AGT-->>WS: stream respuesta inmediata
    WS-->>SPA: "Estoy cruzando cartera + prescripciones + foco. Te aviso cuando termine."
    SPA-->>APM: muestra chip "Análisis en curso"

    Note over APM,SPA: El APM sigue usando la app libremente

    Q->>W: trigger Lambda worker
    W->>AT: query 1: cartera del APM + productos foco
    AT-->>W: resultado
    W->>AT: query 2: prescripciones + EVO trimestral por médico
    AT-->>W: resultado
    W->>AT: query 3: join via maestro_medicos, ranking final
    AT-->>W: resultado
    W->>W: aplicar scoring, generar reporte
    W->>ST: guardar resultado (JSON + gráficos en S3)
    W->>NT: publicar notificación

    NT-->>SPA: push "Tu análisis está listo 🎯"
    APM->>SPA: abre la notificación
    SPA->>ST: GET resultado
    ST-->>SPA: reporte estructurado
    SPA-->>APM: renderiza tarjeta con ranking + explicación
```

### Qué ve el APM

**Momento 1 — pregunta y ack inmediato** (2 segundos):

```
APM: "Recomendame a qué médicos debería visitar según sus prescripciones
     y mis productos foco."

Agente: Perfecto, voy a cruzar tu cartera de médicos con el histórico
        de prescripciones de los últimos 12 meses y tus productos foco
        del ciclo actual. Es un análisis que requiere un poco de tiempo
        (hasta un minuto). Te aviso cuando esté listo — podés seguir
        trabajando mientras tanto.

        [Chip en pantalla: "Análisis en curso • Recomendación de visitas"]
```

**Momento 2 — el APM sigue trabajando** (45 segundos)

El APM navega el dashboard, mira la agenda de hoy, hace otras preguntas cortas. El chip sigue visible en una esquina indicando que hay un análisis en proceso.

**Momento 3 — notificación cuando está listo**

```
🎯 Tu análisis está listo

Recomendación de visitas priorizadas:
1. Dra. Florencia Peralta — crecimiento +18% en ALACIR, visitada hace 45 días
2. Dr. Nicolás Peralta — prescribe APSICO (no foco) pero nunca PAMOXET
3. Dra. Lucía Giménez — EVO positiva en foco, cadencia trimestral incumplida
4. ...

[Ver análisis completo]  [Pedir reestructurar agenda]
```

### Componentes del carril async

**SQS (cola de trabajos)**
- Recibe los jobs serializados (apm_id, pregunta, contexto)
- Permite al agente responder inmediatamente sin esperar el cómputo
- Retry automático si el worker falla
- Costo marginal para este volumen (SQS on-demand es muy barato)

**Worker (Lambda o Fargate)**
- Lambda de hasta 10 minutos si el análisis es simple
- Fargate task si requiere más tiempo o más memoria
- El worker tiene su propia capa semántica para entender la pregunta y ejecutar la serie de queries Athena
- Opcionalmente invoca de nuevo al modelo para generar un resumen en lenguaje natural del resultado
- Costo marginal por ejecución (serverless, dura segundos)

**Storage del resultado**
- **DynamoDB** para la metadata del análisis (job_id, estado, timestamp, resumen corto)
- **S3** para payloads más pesados (tablas de datos, JSON completo, gráficos generados)
- **TTL de 7 días**: si el APM no consulta el resultado en 7 días, se borra automáticamente

**Notificación al APM**
- **WebSocket push** si el APM sigue conectado (común, dado que los APMs trabajan con la app abierta)
- **SNS mobile push** si la app tiene soporte PWA instalada
- **Email** como fallback si el APM cerró la app (opcional)

### Ventajas de este patrón

1. **No hay timeout que importe**. El WebSocket del chat solo carga el ack de 2 segundos. El cómputo largo corre en un worker sin límite de API Gateway ni AgentCore session.
2. **El APM sigue productivo**. No se queda esperando un spinner. Puede hacer otras preguntas, navegar, llamar a un médico.
3. **Escala bien**. Múltiples análisis en paralelo no bloquean al agente — cada uno es un worker independiente.
4. **Reintento automático**. Si un worker falla, SQS lo reintenta. El APM ni se entera.
5. **Mejora la percepción de valor**. Un análisis que se siente "profesional" — el APM asocia latencia con profundidad.


---

## Expectativas de latencia y cómo planificarlas

No existe un número único de latencia para este tipo de sistema. El tiempo total percibido por el APM es la suma de varias partes (lookup de datos, invocación del modelo, generación de tokens, red) y cada una depende del motor elegido, del volumen y del perfil del modelo. Cualquier cifra concreta en un documento de este tipo sería una estimación no verificada y puede generar expectativas incorrectas.

Lo que sí conviene planificar desde el inicio son **objetivos de latencia por tipo de pregunta** (SLOs), y después medirlos empíricamente en cada fase:

| Tipo de pregunta | UX deseado | Fuente de datos típica | Cómo medir |
|---|---|---|---|
| Operativa / lookup directo | Respuesta percibida como inmediata, con streaming visible apenas llega la pregunta | DynamoDB u otra vista hot materializada | P50 y P95 de tiempo hasta el primer token (TTFT) y hasta el final de respuesta |
| Conversacional con cache hit | Respuesta fluida, similar a una conversación natural | Redis con KPIs pre-computados | Hit rate del cache + P95 end-to-end |
| Conversacional con cache miss | Tolerable con streaming y un prefacio natural del agente | Athena o Redshift sobre el lake | P95 de la query + P95 end-to-end |
| Análisis profundo | Sincrónico con espera visible, o asincrónico con notificación al terminar | Athena con múltiples queries, o Redshift con agentes en paralelo | Tasa de éxito, P95 del job, tasa de abandono del APM antes del resultado |

Cómo fijar los SLOs concretos:

1. Armar un set de **15 a 20 preguntas representativas** del APM, cubriendo los cuatro tipos.
2. Medirlas contra la arquitectura elegida (Ruta A o Ruta B, o una combinación) con datos reales o realistas.
3. Comparar esas mediciones con lo que el APM espera. La brecha más importante a cubrir es entre expectativa y realidad, no entre un número absoluto y otro.
4. Iterar sobre las palancas que corresponde a cada carril: caching, escalonado de modelos, prompt caching, provisioned throughput, particionado del lake, agentes en paralelo.

El documento oficial de AWS sobre text-to-SQL reporta que queries SQL simples sobre su deployment de referencia se generan en aproximadamente 3 a 5 segundos ([fuente](https://aws.amazon.com/blogs/machine-learning/text-to-sql-solution-powered-by-amazon-bedrock/)). Es un punto de referencia útil, pero no un contrato: cada implementación tiene que medir lo propio.

### Qué tener presente al planificar

- **Las preguntas operativas son las más frecuentes**. Optimizar su latencia es lo que hace que el sistema se sienta rápido para el APM en su día a día.
- **Las preguntas de gran valor son las más diferenciadoras**. Aunque se hagan pocas veces al día, son las que justifican el producto sobre un dashboard tradicional. Un análisis profundo con buena UX asincrónica puede ser más valioso que un análisis forzado a responder rápido a costa de perder profundidad.
- **El modelo de fundación suele dominar el tiempo de respuesta** en los carriles sincrónicos. Para bajar la latencia de una pregunta conversacional, la palanca más efectiva suele ser cambiar a un modelo más rápido (o a una variante "lite" del mismo proveedor), antes que optimizar la data.
- **El carril asincrónico saca al modelo del camino crítico** para los análisis profundos. El worker puede invocar al modelo para el resumen final sin bloquear la app del APM.

---

## Plan de evolución por fases

Cada fase es **deployable y operable de forma independiente**, entrega valor medible al cliente, y permite validar asumptions antes de seguir. El camino completo son 5 fases de ~2-3 semanas cada una.

### Fase 0 — Demo actual (ya implementada)

- CSVs sintéticos → DynamoDB → Agent Strands
- 1 APM (Peccy), 12 médicos
- Stack AgentCore + modo voz Nova Sonic + frontend
- **Valor**: mostrar capacidad técnica, alineación con el cliente sobre UX

### Fase 1 — Ingesta del CRM interno a S3 Iceberg

**Duración**: 2 semanas

**Qué se hace**:
- Configurar DMS con credenciales del sistema interno del cliente
- Replicar las 15+ tablas del CRM interno a `s3://pharmassist-lake/crm/`
- Glue Crawler descubre el schema y registra en Data Catalog
- Athena queryea las tablas como prueba
- Cargar tablas maestras (`maestro_integrador_producto`, `maestro_medicos`)

**Valor entregado**: los datos reales del cliente están en AWS y son queryeables. El equipo de datos del cliente valida que los datos llegaron bien.

### Fase 2 — Refill nocturno de DynamoDB + migración del agente a datos reales

**Duración**: 2 semanas

**Qué se hace**:
- Glue ETL job nocturno que toma lo relevante de Iceberg y lo escribe en DynamoDB
- Los 15 tools del agente que hoy leen de DynamoDB siguen funcionando sin cambios — apuntan a datos reales
- Migración del usuario Peccy a APMs reales del cliente (con sus carteras)
- Testing contra preguntas de bajo y medio valor

**Valor entregado**: el agente responde preguntas del **carril instantáneo** con datos productivos. Primera demo "real" al cliente con sus propios APMs.

### Fase 3 — Ingesta CloseUp + IQVIA + carril conversacional

**Duración**: 3 semanas

**Qué se hace**:
- Configurar ingesta mensual de CloseUp y IQVIA a S3 Iceberg
- Construir `semantic_layer.yaml` con las 3 fuentes, métricas y queries canónicas
- Agregar tools al agente que queryean Athena cross-source
- ElastiCache Redis para KPIs pre-computados por APM
- Glue ETL nocturno que materializa los KPIs del carril conversacional

**Valor entregado**: el agente responde preguntas de **valor medio** (top prescriptores, EVO trimestral, rankings acotados). Este es el primer punto donde el agente hace cosas que un dashboard no.

### Fase 4 — Carril async para análisis profundo

**Duración**: 3 semanas

**Qué se hace**:
- SQS queue + Lambda worker para jobs async
- Tool del agente `despachar_analisis_profundo` que encola y responde inmediatamente
- DynamoDB + S3 para storage de resultados
- SNS / WebSocket push para notificaciones
- UI en el frontend: chip de "análisis en curso", panel de análisis, notificaciones

**Valor entregado**: el agente responde las preguntas de **gran valor**. Este es el diferenciador completo del producto. Es el momento del "wow" para los usuarios y stakeholders.

### Fase 5 — Hardening y observabilidad

**Duración**: 2 semanas

**Qué se hace**:
- Métricas por carril (P50/P95 de latencia, hit rate de Redis, costo Athena)
- Alertas CloudWatch (latencia degradada, errores de ETL, cola SQS con lag)
- Load testing con perfil realista (50-200 APMs concurrentes)
- Documentación operativa para el equipo del cliente
- Runbooks para incidentes comunes

**Valor entregado**: el sistema está listo para producción continua, observable, operable por el equipo del cliente.


---

## Elección de modelo

La elección del modelo de fundación es una decisión independiente de la arquitectura. El sistema está diseñado para ser agnóstico al modelo: cada carril de respuesta puede apuntar a un modelo distinto según el tradeoff deseado entre calidad de redacción, latencia y costo por consulta. Los precios oficiales de cada modelo deben consultarse siempre contra la fuente al momento de decidir, porque el espacio evoluciona rápido.

### Modelo del prototipo actual

El prototipo de PharmAssist corre sobre **Claude Opus 4.7** vía Amazon Bedrock, elegido por su capacidad para seguir instrucciones complejas, manejar tool-use encadenado y producir respuestas bien redactadas en español argentino. Es un modelo premium orientado a razonamiento agentic. Referencias: [anuncio Claude Opus 4.7 en Bedrock](https://aws.amazon.com/blogs/aws/aws-weekly-roundup-claude-opus-4-7-in-amazon-bedrock-aws-interconnect-ga-and-more-april-20-2026/), [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).

### Alternativa para escalar: Amazon Nova 2 Lite

**Amazon Nova 2 Lite** es una alternativa disponible en Bedrock con un perfil muy distinto: reasoning model de uso general, optimizado para costo y velocidad, con un contexto de 1 millón de tokens, tool-use, web grounding y tres niveles de intensidad de razonamiento (low/medium/high). Para las preguntas operativas de alta frecuencia que el APM hace a diario, Nova 2 Lite ofrece un órden de magnitud de diferencia en el costo por consulta respecto a modelos premium como Opus 4.7. Referencias: [anuncio oficial Nova 2 Lite](https://aws.amazon.com/blogs/aws/introducing-amazon-nova-2-lite-a-fast-cost-effective-reasoning-model/), [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).

### Cómo aprovechar el ahorro sin perder calidad

La estrategia recomendada no es migrar todo el tráfico a un modelo más chico, sino **escalonar el modelo por carril de respuesta**:

- **Carril instantáneo y conversacional cache-hit** → modelo económico tipo Nova 2 Lite. Preguntas operativas ("¿cuáles son mis visitas hoy?", "últimos productos presentados al Dr. X") donde la respuesta es casi mecánica y el volumen es alto (~10 consultas/día por APM).
- **Carril conversacional cache-miss y análisis profundo async** → modelo premium tipo Claude Opus 4.7. Preguntas que requieren cruzar fuentes, redactar interpretaciones sutiles o producir un resumen profesional del resultado (~1-3 consultas/día por APM).

El agente Strands puede decidir el modelo junto con el tool, porque la decisión del carril ya está tomada en ese punto. Implementación: dos `BedrockModel` configurados, y el agente (o un router previo) elige en runtime.

### Otras palancas de optimización

Palancas específicas de cada proveedor que vale la pena considerar una vez en producción con métricas reales:

- **Prompt caching** — el system prompt + la capa semántica son largos y estables. Tanto Anthropic como Amazon Nova ofrecen prompt caching en Bedrock, que cobra una fracción del input después de la primera request para los tokens cacheados.
- **Provisioned throughput** — descuentos significativos sobre on-demand con compromiso mensual, útil si el volumen se estabiliza y es predecible.
- **Redis Serverless** si el uso es variable: cobra solo por ECU-hour activo, útil para picos diarios concentrados.
- **Archivar prescripciones históricas (> 24 meses) a S3 Glacier** — reduce el storage cost del lake para esa partición.
- **Intelligent tiering en S3** para el lake — mueve automáticamente datos fríos a Infrequent Access.

Ninguna de estas palancas debería aplicarse antes del MLP. Todas se evalúan con métricas reales de producción y con SLOs concretos.

---

## Resumen ejecutivo

El MLP productivo de PharmAssist para la industria farmacéutica argentina se construye sobre **tres pilares**:

**Pilar 1 — Data lake unificado**. Las 3 fuentes (sistema interno + CloseUp + IQVIA) replicadas a S3 Iceberg con cadencias independientes. Las tablas maestras de integración permiten los joins cross-source en query time. El lake es la fuente única de verdad analítica.

**Pilar 2 — Carriles de respuesta con UX explícita por tipo de pregunta**. Las preguntas operativas se sirven con baja latencia y streaming visible; las planificadas de gran valor pueden responderse sincrónicamente con streaming o con un carril asincrónico que le avisa al APM cuando el análisis está listo. La elección entre un esquema Athena-first (Ruta A, más económico) o Redshift-first (Ruta B, siguiendo el [patrón oficial text-to-SQL de AWS](https://aws.amazon.com/blogs/machine-learning/text-to-sql-solution-powered-by-amazon-bedrock/)) es empírica y depende del mix real de preguntas y del UX deseado.

**Pilar 3 — Capa semántica en el agente**. Un `semantic_layer.yaml` con entidades, métricas, queries canónicas y reglas de negocio, inyectado al system prompt. El LLM entiende productos foco, EVO trimestral, market share y cruces entre fuentes. Esto permite responder preguntas nuevas sin redeploy de código.

**La arquitectura responde al dilema original** de cómo dar "insights on-the-go" a los APMs sin comprometer latencia ni flexibilidad. Las preguntas de bajo valor responden tan rápido como un dashboard. Las de gran valor ofrecen análisis que ningún dashboard puede dar, con una experiencia async que no obliga al usuario a esperar mirando una pantalla.

**El camino a producción** es de ~12 semanas divididas en 5 fases. Cada fase entrega valor medible y permite al cliente validar asumptions antes de comprometer la siguiente inversión. La capa semántica como ontología queryable es el componente que permite al agente responder preguntas nuevas sin redeploy, y es el que debe cuidarse con más atención durante la evolución del producto.

---

## Referencias

- [AWS DMS — Database Migration Service](https://docs.aws.amazon.com/dms/)
- [Apache Iceberg on AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/apache-iceberg-on-aws/introduction.html)
- [Amazon Athena](https://docs.aws.amazon.com/athena/)
- [ElastiCache for Redis](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/WhatIs.html)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [CloseUp Solutions](https://www.closeupsolutions.com/) — datasets de prescripciones
- [IQVIA](https://www.iqvia.com/) — datasets de ventas de mercado farmacéutico
