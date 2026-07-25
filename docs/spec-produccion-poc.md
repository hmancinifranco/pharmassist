# Spec: POC de Producción — Modelo de Datos Real con CodeAgent

## Objetivo

Demostrar la **factibilidad técnica y de performance** de PharmAssist operando con el modelo de datos real del cliente (52 tablas, datos de prescripciones de mercado, lógica de productos foco/hiperfoco, cálculos de EVO TRM on-the-fly). El entregable es un sistema desplegado en AWS que un APM puede usar conversacionalmente y recibir respuestas correctas y rápidas (<6 segundos por interacción) basadas en datos mocked que simulan volúmenes realistas.

**Innovación clave:** En lugar de implementar 15+ tools con SQL hardcodeado, usamos `strands-code-agent` (`CodeAgent`) que genera SQL dinámicamente y ejecuta cálculos con pandas en un REPL persistente. Esto logra +7% accuracy, 78% menos tokens, y 56% más velocidad vs tool-calling tradicional (según benchmarks de AWS).

## Contexto del Problema

El proyecto actualmente opera con 3 CSVs simples (crm_medicos, apm_visitas, ventas_reportadas). El cliente real tiene:
- **52 tablas** relacionales con JOINs de 5-6 niveles
- **Datos de prescripciones de mercado** (fuente externa CUP/IQVIA) que determinan qué médicos prescriben qué marcas
- **Grillas de promoción** con ciclos temporales y categorías foco/hiperfoco
- **Tablas analíticas** (`UltimaMillaMarca`, `UltimaMillaMedico`) que se consultan on-the-fly
- Una expectativa de que el agente **calcule agregaciones en tiempo real** durante la conversación

El APM habla con el agente y espera respuestas con datos en <6 segundos. No hay tablas pre-computadas de respuestas — todo se calcula al momento de la pregunta.

## Alcance

### Incluido:
1. Modelo de datos en Aurora PostgreSQL Serverless con las tablas del DER del cliente
2. Seed data mocked que simula volúmenes realistas (ver sección "Volúmenes de Prueba")
3. `CodeAgent` con `Toolkit` personalizado que accede a la BD y genera SQL dinámicamente
4. System prompt con schema de la BD + reglas de negocio farmacéutico (EVO TRM, Foco/Hiperfoco, ciclos)
5. Deploy completo en AWS (CDK)
6. Prueba end-to-end: las 14 preguntas tipo del cliente respondidas correctamente en <6 segundos

### Fuera de alcance:
- Integración real con fuentes externas IQVIA
- Pipeline de ETL de datos crudos de prescripciones
- Actualización periódica automática de datos UltimaMilla
- Multi-tenancy (múltiples APMs con auth)
- Voice mode

---

## Arquitectura del Agente: CodeAgent con REPL Persistente

### Referencia de implementación

El approach se basa en [`strands-code-agent`](https://github.com/aws-samples/sample-strands-code-agent) y el ejemplo de referencia [`sample-StrandsDataAnalyst`](https://github.com/aws-samples/sample-StrandsDataAnalyst) — un Data Analyst Agent basado en Strands SDK con capacidad de introspeccionar schemas SQL, escribir queries, procesar datos con pandas, y generar respuestas.

### ¿Por qué CodeAgent en lugar de 15 tools fijas?

| Aspecto | Tool-calling tradicional | CodeAgent con REPL |
|---------|--------------------------|---------------------|
| Preguntas soportadas | Solo las que tienen tool | Cualquiera que se pueda resolver con SQL + pandas |
| Agregar nueva pregunta | Escribir nueva tool + SQL | Solo agregar regla al system prompt |
| Accuracy (benchmark) | Baseline | +7% |
| Tokens consumidos | Baseline | 78% menos input, 67% menos output |
| Velocidad | Baseline | 56% más rápido |
| JOINs complejos | Hardcodeados por dev | Generados por el LLM según el schema |
| Mantenimiento | Alto (15+ functions SQL) | Bajo (schema + reglas de negocio) |

### Diseño del CodeAgent

```python
from strands_code_agent import CodeAgent, Toolkit
from strands.models import BedrockModel
import pandas as pd

# Funciones expuestas al REPL del agente
def query_db(sql: str) -> pd.DataFrame:
    """Ejecuta una consulta SQL contra la BD de prescripciones y devuelve un DataFrame.
    
    La BD contiene tablas de cartera médica, visitas, productos foco, 
    y datos de prescripciones de mercado (UltimaMilla).
    """
    conn = get_db_connection()  # Aurora PostgreSQL
    return pd.read_sql(sql, conn)

def get_apm_id() -> str:
    """Devuelve el ID del APM que está usando el sistema."""
    return current_apm_id

def get_ciclo_actual_id() -> int:
    """Devuelve el ID del ciclo promocional actual."""
    df = query_db("SELECT id FROM ciclo ORDER BY fin DESC LIMIT 1")
    return int(df.iloc[0]['id'])

# Toolkit personalizado para farmacéutica
PHARMA_TOOLKIT = Toolkit(
    authorized_imports=["pandas", "numpy"],
    init_code="""
import pandas as pd
import numpy as np
# Contexto del APM cargado al inicio de sesión
APM_ID = get_apm_id()
CICLO_ACTUAL = get_ciclo_actual_id()
""",
    domain_specific_code=[query_db, get_apm_id, get_ciclo_actual_id],
)

model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
    region_name="us-east-1",
)

agent = CodeAgent(
    model=model,
    system_prompt=SYSTEM_PROMPT,  # Incluye schema + reglas de negocio
    toolkits=[PHARMA_TOOLKIT],
)
```

### System Prompt (contenido clave)

El system prompt incluye:
1. **Schema completo de la BD** — nombres de tablas, columnas, tipos, FKs
2. **Reglas de negocio** — cómo calcular EVO TRM, qué son productos foco/hiperfoco, qué es un ciclo
3. **Patrones de consulta** — ejemplos de SQL para las preguntas más comunes
4. **Contexto del APM** — el agente sabe que `APM_ID` y `CICLO_ACTUAL` ya están disponibles en el REPL
5. **Instrucciones de respuesta** — responder en español argentino, conversacional, con datos concretos

### Flujo de una interacción

```
APM pregunta: "Recomendame a qué médicos debería visitar según sus prescripciones 
               y mis productos Foco"

→ LLM razona y genera código Python:

  # 1. Obtener productos foco del APM en el ciclo actual
  productos_foco = query_db(f"""
    SELECT DISTINCT fp.id, fp.nombre, cp.abreviatura as categoria
    FROM detalle_promocion_producto dpp
    JOIN grilla g ON g.id = dpp.id_grilla
    JOIN linea_apm la ON la.id_linea = g.id_linea
    JOIN familia_producto fp ON fp.id = dpp.id_familia_producto
    JOIN categoria_promocion cp ON cp.id = dpp.id_categoria_promocion
    WHERE la.id_apm = '{APM_ID}'
      AND dpp.id_ciclo = {CICLO_ACTUAL}
      AND dpp.id_categoria_promocion IN ('1', '2')
  """)
  
  # 2. Obtener códigos de marca CUP para esos productos
  ids_familia = ','.join([f"'{x}'" for x in productos_foco['id']])
  marcas_cup = query_db(f"""
    SELECT id_familia_producto_apx, codMarcaCUP 
    FROM familia_APX_a_Marca_CUP 
    WHERE id_familia_producto_apx IN ({ids_familia})
  """)
  
  # 3. Obtener top prescriptores de esas marcas en la cartera del APM
  ids_marca = ','.join([f"'{x}'" for x in marcas_cup['codMarcaCUP']])
  resultado = query_db(f"""
    SELECT d.primerApellido, d.primerNombre, esp.nombre as especialidad,
           umm.marcaNombre, umm.ShareMarcaMercado, umm.IEMarcaTrim
    FROM cartera_medica cm
    JOIN doctor d ON d.id = cm.doctor_id
    JOIN especialidad esp ON esp.id = d.especialidad_id
    JOIN UltimaMillaMedico ume ON ume.idMedicoAPX = cm.doctor_id
    JOIN UltimaMillaMarca umm ON umm.idMedicoCUP = ume.idMedicoCUP
    WHERE cm.apm_id = '{APM_ID}' AND cm.inactivo = false
      AND umm.idMarca IN ({ids_marca})
    ORDER BY umm.ShareMarcaMercado DESC
    LIMIT 15
  """)
  
  # 4. Agrupar por producto y dar top 3 por cada uno
  resultado_merged = resultado.merge(marcas_cup, left_on='marcaNombre', ...)
  top_por_producto = resultado_merged.groupby('nombre_producto').head(3)
  print(top_por_producto.to_string())

→ REPL ejecuta el código y devuelve resultados
→ LLM genera respuesta conversacional al APM
```

---

## Capa de Datos: Aurora PostgreSQL Serverless v2

### ¿Por qué PostgreSQL?

- JOINs de 5-6 niveles con aggregations son la norma — PostgreSQL los resuelve nativamente
- El scope de cada consulta está acotado a un APM (filtra temprano, reduce filas)
- Con 1.5M filas en la tabla más grande y filtro por cartera del APM (~150 médicos), cada query escanea ~7,500 filas — trivial para PostgreSQL
- El `CodeAgent` genera SQL estándar que PostgreSQL ejecuta sin adaptación

### ¿Por qué no DynamoDB?
- DynamoDB no soporta JOINs nativos
- El CodeAgent genera SQL dinámico — necesita un motor SQL real

### ¿Por qué no ClickHouse (por ahora)?
- Los volúmenes del POC (1.5M max) no lo justifican
- Si los volúmenes reales son 10x+ mayores, se puede migrar `UltimaMillaMarca` a ClickHouse sin cambiar el CodeAgent (solo cambia el connection string)

### Configuración:
- Aurora PostgreSQL Serverless v2 (min 0.5 ACU, max 4 ACU)
- Índices compuestos: `(apm_id)` en cartera_medica y agenda, `(idMedicoCUP, idMarca)` en UltimaMillaMarca, `(id_ciclo, id_categoria_promocion)` en detalle_promocion_producto
- VPC con subnets privadas
- Secrets Manager para credenciales
- Región: us-east-1

---

## Modelo de Datos

### Tablas Core

#### `apm`
| Campo | Tipo | Notas |
|-------|------|-------|
| id | VARCHAR PK | Identificador del APM (ej: '4301') |
| primerNombre | VARCHAR | |
| primerApellido | VARCHAR | |
| email | VARCHAR | |
| id_linea | VARCHAR FK → linea | Línea de negocio |
| gerente_regional_id | VARCHAR FK → apm | |
| codigoPromotor | VARCHAR | |
| inactivo | BOOLEAN | |

#### `doctor`
| Campo | Tipo | Notas |
|-------|------|-------|
| id | VARCHAR PK | |
| primerNombre | VARCHAR | |
| primerApellido | VARCHAR | |
| matriculaNacional | VARCHAR | |
| especialidad_id | VARCHAR FK → especialidad | |
| loyalty_id | VARCHAR FK → loyalty_doctor | |
| categoria_id | VARCHAR FK → categoria_doctor | |
| inactivo | BOOLEAN | |

#### `agenda` (visitas)
| Campo | Tipo | Notas |
|-------|------|-------|
| id | VARCHAR PK | |
| inicio | TIMESTAMP | Fecha/hora de la visita |
| fin | TIMESTAMP | |
| apm_id | VARCHAR FK → apm | |
| doctor_id | VARCHAR FK → doctor | |
| visita_exitosa | BOOLEAN | |
| observaciones | TEXT | |
| visita_tipo | VARCHAR | Presencial/Virtual/Telefónica |
| inactivo | BOOLEAN | |

#### `agenda_producto` (productos promocionados en visita)
| Campo | Tipo | Notas |
|-------|------|-------|
| id | VARCHAR PK | |
| id_agenda | VARCHAR FK → agenda | |
| id_producto | VARCHAR FK → producto | Apunta a familia_producto |

#### `cartera_medica` (relación APM-Doctor activa)
| Campo | Tipo | Notas |
|-------|------|-------|
| id | VARCHAR PK | |
| apm_id | VARCHAR FK → apm | |
| doctor_id | VARCHAR FK → doctor | |
| datos_visita_id | VARCHAR FK → datos_visita | |
| inactivo | BOOLEAN | False = activa |

### Tablas de Catálogo

#### `especialidad`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| nombre | VARCHAR |

#### `linea`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| nombre | VARCHAR |
| abreviatura | VARCHAR |

#### `linea_apm`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| id_apm | VARCHAR FK → apm |
| id_linea | VARCHAR FK → linea |

#### `producto`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| nombre | VARCHAR |
| id_linea | VARCHAR FK → linea |

#### `familia_producto`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| nombre | VARCHAR |
| principio_activo | VARCHAR |
| accion_terapeutica | VARCHAR |

#### `ciclo`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| inicio | DATE |
| fin | DATE |
| nombre | VARCHAR |

#### `grilla`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| nombre_grilla | VARCHAR |
| id_linea | VARCHAR FK → linea |

#### `categoria_promocion`
| Campo | Tipo | Notas |
|-------|------|-------|
| id | VARCHAR PK | '1' = HP, '2' = FC |
| abreviatura | VARCHAR | HP, FC |
| nombre_categoria | VARCHAR | |

#### `detalle_promocion_producto`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| id_familia_producto | VARCHAR FK → familia_producto |
| id_grilla | VARCHAR FK → grilla |
| id_categoria_promocion | VARCHAR FK → categoria_promocion |
| id_ciclo | VARCHAR FK → ciclo |

#### `datos_visita`
| Campo | Tipo | Notas |
|-------|------|-------|
| id | VARCHAR PK | |
| frecuencia | VARCHAR | Mensual, Trimestral, Semestral, Anual |
| institucion_id | VARCHAR FK → institucion | |

#### `loyalty_doctor`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| nombre | VARCHAR |

#### `institucion`
| Campo | Tipo |
|-------|------|
| id | VARCHAR PK |
| nombre | VARCHAR |

### Tablas Analíticas de Prescripción

#### `UltimaMillaMedico`
| Campo | Tipo | Notas |
|-------|------|-------|
| idMedicoCUP | VARCHAR | ID en sistema CUP |
| idMedicoAPX | VARCHAR FK → doctor.id | ID en sistema interno |
| IETrim | DECIMAL | Índice de Evolución Trimestral |
| ShareTrim | DECIMAL | Share trimestre actual |
| ShareTrim_1 | DECIMAL | Share trimestre anterior |
| ShareMes | DECIMAL | |

#### `UltimaMillaMarca`
| Campo | Tipo | Notas |
|-------|------|-------|
| idMedicoCUP | VARCHAR | |
| idMarca | VARCHAR | ID marca en CUP |
| idMercado | VARCHAR | |
| idLaboratorio | VARCHAR | `'ELE'` = laboratorio propio; `LAB_A`..`LAB_E` = competencia |
| marcaNombre | VARCHAR | |
| ShareMarcaMercado | DECIMAL | Share de la marca en su mercado |
| ShareMarcaMes | DECIMAL | |
| IEMarcaTrim | DECIMAL | |
| ShareMarcaTrim | DECIMAL | |
| ShareMarcaTrim_1 | DECIMAL | |

#### `UltimaMillaObjetivoMarcaMercado`
| Campo | Tipo |
|-------|------|
| idEspecialidad | VARCHAR FK → especialidad |
| idMarca | VARCHAR |
| idMercado | VARCHAR |
| marcaNombre | VARCHAR |

#### `familia_APX_a_Marca_CUP` (tabla puente)
| Campo | Tipo | Notas |
|-------|------|-------|
| id_familia_producto_apx | VARCHAR FK → familia_producto.id | |
| codMarcaCUP | VARCHAR | = UltimaMillaMarca.idMarca |

---

## Volúmenes de Prueba (Seed Data Mocked)

| Tabla | Filas | Justificación |
|-------|-------|---------------|
| apm | 200 | ~200 APMs activos |
| doctor | 30,000 | Universo de médicos |
| especialidad | 50 | Especialidades médicas |
| linea | 5 | Líneas de negocio |
| linea_apm | 300 | Algunos APMs cubren >1 línea |
| producto | 150 | Productos del laboratorio |
| familia_producto | 40 | Familias de producto |
| ciclo | 12 | Últimos 12 ciclos (1 año) |
| grilla | 10 | 2 grillas por línea |
| categoria_promocion | 2 | HP y FC |
| detalle_promocion_producto | 100 | ~10 familias foco por grilla/ciclo |
| cartera_medica | 25,000 | ~125 médicos por APM |
| datos_visita | 25,000 | 1 por cada cartera_medica |
| agenda | 150,000 | ~750 visitas por APM en 12 meses |
| agenda_producto | 300,000 | ~2 productos por visita |
| loyalty_doctor | 5 | Niveles A, B, C, D, E |
| institucion | 500 | Hospitales/clínicas |
| UltimaMillaMedico | 30,000 | 1 fila por médico (snapshot) |
| **UltimaMillaMarca** | **1,500,000** | 30,000 médicos × ~50 marcas |
| UltimaMillaObjetivoMarcaMercado | 500 | Combinaciones esp×marca×mercado |
| familia_APX_a_Marca_CUP | 60 | ~1.5 marcas CUP por familia |

**Tabla crítica para performance:** `UltimaMillaMarca` con 1.5M filas — el CodeAgent generará queries que filtran esta tabla por la cartera del APM (~150 médicos × ~50 marcas = ~7,500 filas escaneadas).

---

## Presupuesto de Latencia

| Fase | Target | Notas |
|------|--------|-------|
| LLM reasoning + generación de código | ~2-3s | Claude genera Python con SQL |
| Ejecución del código (queries + pandas) | <1s | REPL ejecuta, PostgreSQL resuelve |
| LLM generation (respuesta final) | ~1-2s | Claude genera respuesta conversacional |
| **Total por interacción** | **<6s** | |

---

## Preguntas End-to-End a Validar

### Categoría 1: Prescripciones y Productos Foco
1. "Recomendame a qué médicos debería visitar según sus prescripciones y mis productos Foco"
2. "Qué médicos vienen creciendo en prescripción de mis productos foco y los estoy visitando poco?"
3. "A qué médicos debería visitar primero para crecer con las prescripciones del producto X"
4. "Cuales son los 10 médicos más prescriptores en X mercado?"
5. "En qué productos propios tengo EVO TRM negativa?"
6. "En qué médicos tengo EVO TRM negativa?"

### Categoría 2: Análisis de Promoción
7. "De los medicamentos que no le promociono a X médico, cuál es el que más prescribe?"
8. "De los medicamentos que sí le promociono a X médico, cuál es el que más prescribe?"
9. "Cuales son los 5 productos que más prescribe X médico?"
10. "Cuales son los 5 productos propios que más prescribe X médico?"

### Categoría 3: Gestión de Visitas
11. "Cuales son mis objetivos de visita este mes?"
12. "Que médicos todavía no visite en el ciclo actual?"
13. "Cuando fue la última visita a X médico?"
14. "Que promocioné en la última visita a X médico?"

### Criterios de éxito:
- ✅ Respuesta correcta (el SQL generado devuelve datos consistentes con la lógica esperada)
- ✅ Latencia total <6 segundos
- ✅ Respuesta en español argentino, conversacional, con datos concretos
- ✅ El agente maneja preguntas variantes (reformulaciones) sin necesidad de tools nuevas

---

## Fórmulas y Reglas de Negocio (para el System Prompt)

### EVO TRM
```
EVO TRM = ShareMarcaTrim - ShareMarcaTrim_1
```
Positiva = crece prescripción. Negativa = pierde.

### Productos Foco
Familias de producto con categoría HP (Hiperfoco) o FC (Foco) en el ciclo actual del APM.

### Cruce APX → CUP
`familia_APX_a_Marca_CUP` traduce productos internos a marcas de mercado.

### Objetivo de visitas
Suma de frecuencias de la cartera médica activa del APM.

---

## Infraestructura CDK (nuevos recursos)

- **Aurora PostgreSQL Serverless v2** cluster (min 0.5 ACU, max 4 ACU)
- **VPC** con subnets privadas para Aurora
- **Security Group** para acceso desde Lambda/AgentCore
- **Secrets Manager** para credenciales de BD
- **Lambda** para seed data (carga inicial de datos mocked)
- **IAM Role** con permisos para AgentCore Code Interpreter (si se usa como sandbox)

---

## Riesgos y Mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| El LLM genera SQL incorrecto | Respuesta errónea | Schema detallado en system prompt + ejemplos de queries correctos |
| `UltimaMillaMarca` con 1.5M filas es lenta | Latencia >1s | Índice `(idMedicoCUP, idMarca)` + filtro por cartera reduce a ~7,500 filas |
| Aurora cold start | Primera consulta lenta | Min ACU = 0.5 para mantener warm |
| `strands-code-agent` no soporta AgentCore deploy | No se puede desplegar | Fallback: usar AgentCore Code Interpreter como sandbox alternativo |
| Volúmenes reales 10x mayores | Performance degrada | Migrar UltimaMillaMarca a ClickHouse (solo cambia connection string) |
| SQL injection via LLM | Seguridad | Read-only user en PostgreSQL + parameterized queries en `query_db` |

---

## Deploy y Validación End-to-End

### Deploy en AWS

El spec **incluye el despliegue completo a AWS** como parte obligatoria antes de cerrar. No se considera terminado solo con `cdk synth` — el sistema debe estar corriendo en la nube con datos cargados y el agente respondiendo.

**Pasos de deploy:**
1. `cdk deploy` del stack completo (Aurora + VPC + Secrets + Lambda seed)
2. Ejecución de la Lambda de seed data que carga las 1.5M+ filas en Aurora
3. Verificación post-deploy de que Aurora está activa y las tablas están pobladas (query de validación)
4. Deploy del CodeAgent a AgentCore (`agentcore deploy`) o alternativa (Lambda + API Gateway si strands-code-agent no es compatible con AgentCore)
5. Verificación de que el agente responde al menos una pregunta simple correctamente

**Si el deploy falla:** se diagnostica y resuelve antes de cerrar el spec. No se deja al usuario resolver errores de deploy manualmente.

### Prueba End-to-End en la Nube

Una vez desplegado, se ejecuta un **smoke test automatizado** que:
1. Invoca al agente con cada una de las 14 preguntas tipo
2. Mide la latencia total de cada interacción (desde invoke hasta response)
3. Valida que la respuesta contiene datos concretos (no genéricos ni errores)
4. Verifica que el SQL generado es correcto ejecutándolo directamente contra Aurora y comparando resultados
5. Genera un reporte con:
   - ✅/❌ por cada pregunta
   - Latencia por fase (LLM + SQL + response)
   - SQL generado para cada pregunta (para auditoría)

**Criterio de éxito del POC:**
- ≥12 de 14 preguntas respondidas correctamente (≥85%)
- Latencia promedio <6 segundos
- Ninguna pregunta con latencia >10 segundos
- El agente maneja al menos 2 reformulaciones sin tools nuevas

---

## Entregables

1. **Schema SQL** (DDL con índices) para Aurora PostgreSQL
2. **Script de seed data** (Python/Lambda) que genera 1.5M+ filas mocked con distribuciones realistas
3. **CDK Stack** extendido con Aurora + VPC + Secrets
4. **CodeAgent** con Toolkit personalizado y system prompt completo
5. **Deploy exitoso a AWS** — infraestructura levantada, datos cargados, agente respondiendo
6. **Test e2e automatizado** que ejecuta las 14 preguntas contra el agente desplegado
7. **Reporte de performance** con correctitud + latencia desglosada por fase
