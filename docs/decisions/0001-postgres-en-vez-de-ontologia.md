# ADR 0001 — Base relacional PostgreSQL en vez de una ontología o grafo de conocimiento

- **Estado**: aceptada
- **Ámbito**: capa de datos del agente (`query_db` → Aurora PostgreSQL)
- **Alternativas descartadas**: ontología formal + capa semántica; grafo de propiedades (Neptune Analytics / Apache AGE / Neo4j) con GraphRAG

## Contexto

El agente tiene que responder preguntas en lenguaje natural que cruzan dos mundos de datos: el **CRM interno** del laboratorio (a quién visito, qué le presenté, qué tengo que promocionar este ciclo) y la **auditoría de prescripciones y ventas** de proveedores de mercado (qué prescribe realmente ese médico, con qué share y cómo evoluciona).

Cuando arrancamos el diseño, la opción de una **ontología** o un **grafo de conocimiento** estaba sobre la mesa y documentada. En [`../research-external-schemas.md`](../research-external-schemas.md) figura el plan de modelar las relaciones de prescripción como aristas con propiedades (`Médico —prescribe[weight=share, evo=crecimiento]→ Marca`) en Neptune Analytics, y en [`../road-to-prod.md`](../road-to-prod.md) la "Ruta B" contempla Redshift + GraphRAG (Neptune + OpenSearch) siguiendo el patrón del blog oficial de AWS de text-to-SQL. El roadmap todavía conserva esos specs (`semantic-layer`, `semantic-graph-neptune`) como fases posteriores opcionales.

Terminamos implementando lo contrario: **una base relacional PostgreSQL y un agente que genera SQL**. Este documento explica por qué, porque es la decisión de arquitectura menos obvia del proyecto.

## Decisión

Modelar los datos como **21 tablas relacionales normalizadas en Amazon Aurora PostgreSQL Serverless v2**, y resolver las preguntas con un **CodeAgent que genera SQL** (`query_db`) en vez de tools de dominio, ontología formal o traversals de grafo.

El conocimiento semántico que el modelo relacional no expresa por sí solo (los caminos de JOIN válidos, las reglas de negocio, cómo se calcula EVO TRM) vive en el **system prompt** del agente, no en una capa de datos separada.

## Razones

### 1. Los datos de origen ya son relacionales

El CRM del laboratorio es una base SQL relacional. La query de producción que nos compartieron para validar el dominio es T-SQL con CTEs y JOINs de seis niveles. Elegir un grafo habría implicado agregar una **transformación semántica** en la ingesta: mapear tablas a nodos y aristas, mantener ese mapeo, y debuggear problemas en dos representaciones distintas del mismo hecho.

Manteniendo el modelo relacional, el schema del repo es reconocible para cualquier analista del laboratorio. Eso hizo que la validación fuera directa: pudimos comparar los resultados del agente contra las queries que ellos ya corrían.

### 2. Las preguntas reales son agregaciones, no traversals

Esta es la razón de fondo. Un grafo gana cuando la **profundidad del recorrido es variable o desconocida**: caminos más cortos, N-hop, detección de comunidades, propagación de influencia.

Revisamos las 15 preguntas priorizadas por el cliente (la tabla completa está en [`../research-external-schemas.md`](../research-external-schemas.md)). Todas, sin excepción, son **filtros y agregaciones sobre caminos de profundidad fija y conocida**:

| Pregunta | Qué operación es realmente |
|---|---|
| "Top 10 prescriptores en mercado X" | `ORDER BY` + `LIMIT` sobre un JOIN de 3 tablas |
| "Médicos con EVO TRM negativa" | resta de dos columnas + filtro |
| "Medicamentos que NO promociono y más prescribe el Dr. X" | anti-join entre promoción y prescripción |
| "Médicos a visitar para crecer con el producto X" | JOIN de 5-6 niveles + ranking |
| "Médicos no visitados en el ciclo actual" | `LEFT JOIN` + `IS NULL` |

Ninguna requiere recorrer una cantidad indeterminada de saltos. El JOIN más profundo tiene seis niveles y esos seis niveles **están conocidos de antemano** — son los cinco caminos documentados en [`../data-model.md`](../data-model.md). SQL expresa eso de forma natural; un grafo no aportaría capacidad de consulta que no tengamos.

### 3. Las relaciones de valor ya vienen pre-computadas

El insight que más pesó. Las tablas de última milla (`"UltimaMillaMedico"`, `"UltimaMillaMarca"`) son **vistas materializadas cross-source que ya existen en el CRM del laboratorio**: traen los datos de prescripción ya cruzados y agregados contra el CRM.

Dicho de otro modo: la arista `Médico —prescribe[weight=share]→ Marca` que planeábamos crear en Neptune **ya existe**, como una fila de `"UltimaMillaMarca"` con el peso en la columna `"ShareMarcaMercado"` y la evolución en `"ShareMarcaTrim" - "ShareMarcaTrim_1"`.

Modelar eso como aristas en un grafo no habría agregado poder expresivo. Habría agregado una **copia de los datos** que hay que sincronizar, con su propio pipeline y su propia ventana de desactualización.

### 4. Los LLM escriben SQL mucho mejor que openCypher o SPARQL

Práctica, pero decisiva. El volumen de SQL en los datos de entrenamiento de un modelo como Claude es órdenes de magnitud mayor que el de openCypher, Gremlin o SPARQL. En la práctica eso se traduce en menos alucinación de sintaxis, mejor manejo de casos raros (acá: los identificadores entrecomillados case-sensitive del schema) y recuperación más limpia cuando una query falla.

Además el ecosistema alrededor es más maduro para lo que necesitábamos:

- **Validación**: verificar que una sentencia sea de solo lectura es trivial en SQL (prefijo + lista de keywords prohibidas). En un lenguaje de grafos el análisis es menos estándar.
- **Contención**: `SET LOCAL statement_timeout` y un rol `GRANT SELECT` acotan el daño de una query mal generada con primitivas nativas del motor.

### 5. Auditabilidad para el usuario final

El panel **"¿De dónde salió esto?"** muestra al APM el SQL exacto que se ejecutó. Un APM no lee SQL, pero **cualquier analista del laboratorio sí**, y eso es lo que permite que el equipo del cliente audite una respuesta y confíe en el sistema.

Mostrar un `MATCH (m:Medico)-[:PRESCRIBE]->(...)` habría cerrado esa puerta. En un dominio donde el usuario toma decisiones comerciales con estos números, la trazabilidad legible es un requisito de producto, no una comodidad de debugging.

### 6. Costo y complejidad operativa

| Opción | Piezas a operar | Costo base aprox. |
|---|---|---|
| **Aurora PostgreSQL Serverless v2** | 1 (más NAT de la VPC) | ~$43/mes (piso 0,5 ACU) |
| Neptune + OpenSearch (GraphRAG) | 3+ (grafo, índice vectorial, pipeline de sincronización) | varias veces mayor, con pisos por instancia |

Para un producto que todavía estaba validando si el enfoque conversacional resolvía el problema, sumar dos servicios con costo base y un pipeline de sincronización era gasto y complejidad sin una pregunta que lo justificara.

### 7. Evidencia empírica antes que especulación

La decisión no se tomó en el pizarrón. El POC (`produccion-poc/`) se construyó justamente para medirla: **21 tablas, ~2M filas, JOINs de 5-6 niveles**, y un set de 14 preguntas representativas.

Resultado: **85,7% de respuestas correctas (12/14) con latencia menor a 6 segundos por interacción.** Con ese número sobre la mesa, invertir en un grafo pasó a ser una optimización sin problema que resolver.

## La capa semántica sí hacía falta — pero en el prompt

Descartar la ontología **no** significó descartar el conocimiento semántico. Un schema relacional no dice por sí solo que `doctor.id` se cruza con `"UltimaMillaMedico"."idMedicoAPX"`, ni que EVO TRM es una resta de dos columnas, ni que los shares son proporciones y no porcentajes. Sin eso, el LLM genera SQL sintácticamente válido y semánticamente equivocado.

Ese conocimiento se resolvió en `agentcore/prompts/system_prompt.py`: el DDL completo, los cinco caminos de JOIN, diez reglas de negocio y ejemplos de queries canónicas. Es, en efecto, **una ontología ligera expresada en lenguaje natural** en el prompt.

El tradeoff es explícito. A favor: se versiona con git, se edita sin migrar datos, y el LLM la consume directamente. En contra: consume tokens de contexto en cada request y no es reutilizable por otros consumidores (por ejemplo, una herramienta de BI).

## Consecuencias

**Positivas**

- Una sola pieza de datos que operar, con costo base bajo y predecible.
- Fidelidad al modelo de origen: la validación contra las queries del cliente es directa.
- Trazabilidad legible de punta a punta (SQL visible en la UI).
- Sin pipeline de sincronización adicional ni ventana de desactualización.
- El agente responde preguntas que no anticipamos, porque genera SQL nuevo en vez de elegir entre tools pre-armadas.

**Negativas, asumidas conscientemente**

- **El system prompt es grande.** El DDL y las reglas consumen contexto en cada invocación. Mitigación posible: prompt caching.
- **Text-to-SQL puede errar en la semántica.** Los 2 fallos de 14 del POC fueron de este tipo. Se mitiga con reglas explícitas, ejemplos canónicos y el panel de provenance para que el usuario detecte una respuesta rara — pero no se elimina.
- **Acoplamiento al schema.** Si el modelo de origen cambia, hay que actualizar el prompt. No hay una capa de indirección que lo absorba.
- **Preguntas de profundidad variable no son naturales.** "Comunidades de prescripción", "médicos similares por patrón de prescripción" o cadenas de influencia se expresan mal en SQL.
- **La capa semántica no es reutilizable** fuera del agente.

## Cuándo revisar esta decisión

Un grafo pasaría a estar justificado si aparece cualquiera de estos disparadores:

1. **Traversals de profundidad desconocida**: preguntas sobre cadenas de influencia entre médicos, o recorridos donde la cantidad de saltos es parte de la respuesta.
2. **Similitud y recomendación colaborativa**: "médicos parecidos a este por patrón de prescripción" — filtrado colaborativo sobre un grafo bipartito es más natural que en SQL.
3. **Entity resolution difusa entre muchas fuentes**: hoy el cruce CRM ↔ mercado es una tabla de equivalencias exacta (`familia_APX_a_Marca_CUP`). Con más fuentes y matching probabilístico, un grafo ayuda a mantener la identidad de las entidades.
4. **Razonamiento sobre relaciones no materializadas**: si el valor pasa a estar en relaciones inferidas en vez de pre-computadas por la fuente.
5. **Latencia inaceptable con volúmenes reales**: si al escalar, los JOINs de 6 niveles dejan de cumplir el SLA y las optimizaciones relacionales se agotan.

El camino de migración está previsto y es incremental: primero formalizar la capa semántica del prompt en un artefacto declarativo (spec `semantic-layer`), y solo después evaluar moverla a un grafo (spec `semantic-graph-neptune`). Ninguno de los dos pasos exige rehacer la capa relacional: Aurora seguiría siendo la fuente de verdad transaccional.

## Referencias

- [`../data-model.md`](../data-model.md) — el modelo relacional y los cinco caminos de JOIN
- [`../research-external-schemas.md`](../research-external-schemas.md) — schemas de las fuentes, las 15 preguntas priorizadas y el plan original de grafo
- [`../road-to-prod.md`](../road-to-prod.md) — Ruta A (Athena-first) vs Ruta B (Redshift + GraphRAG)
- [`../spec-produccion-poc.md`](../spec-produccion-poc.md) — el POC que midió la viabilidad del enfoque
- [`../../agentcore/prompts/system_prompt.py`](../../agentcore/prompts/system_prompt.py) — la capa semántica en el prompt
- [Text-to-SQL con Amazon Bedrock](https://aws.amazon.com/blogs/machine-learning/text-to-sql-solution-powered-by-amazon-bedrock/) — patrón de referencia de AWS
