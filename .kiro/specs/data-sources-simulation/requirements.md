# Requirements — data-sources-simulation

## Overview

Crear una infraestructura que simule los 3 warehouses externos de un laboratorio farmacéutico (CRM interno, CloseUp prescripciones, IQVIA ventas de mercado) usando RDS PostgreSQL en una VPC separada. Incluye generación de datos sintéticos coherentes entre fuentes con volúmenes representativos.

## User Stories

### US-1: Infraestructura de simulación

**Como** ingeniero de datos que desarrolla el pipeline de ingesta,
**quiero** tener 3 bases de datos relacionales con schemas realistas en una VPC separada,
**para** simular el escenario real donde DMS replica datos desde warehouses externos a AWS.

**Acceptance Criteria:**
- [ ] Existe una VPC "externa" con subnets privadas y un RDS PostgreSQL accesible
- [ ] El RDS tiene 3 schemas separados: `crm_interno`, `closeup`, `iqvia`
- [ ] Cada schema tiene las tablas definidas en `docs/research-external-schemas.md`
- [ ] La VPC "externa" es distinta de la VPC default donde corren los servicios actuales
- [ ] El RDS usa una instancia pequeña (db.t3.micro o db.t4g.micro) para minimizar costos
- [ ] La infraestructura se provisiona con CDK (stack `DataSourcesStack`)

### US-2: Schema del CRM interno

**Como** agente IA que necesita responder preguntas operativas,
**quiero** que el schema CRM tenga todas las tablas del sistema interno del laboratorio,
**para** poder consultar cartera médica, agenda, productos foco, y tablas UltimaMilla.

**Acceptance Criteria:**
- [ ] Tablas core: `apm`, `doctor`, `zona`, `especialidad`, `cartera_medica`, `cartera_medica_estado`
- [ ] Tablas de producto: `linea`, `linea_apm`, `familia_producto`, `catalogo_productos`
- [ ] Tablas de promoción: `ciclo`, `grilla`, `categoria`, `detalle_promocion_producto`
- [ ] Tablas de visitas: `agenda`, `agenda_producto`, `agenda_muestra`, `datos_visita`, `visita_planificada`
- [ ] Tablas de tags: `tag`, `tag_doctor`
- [ ] Tablas UltimaMilla: `ultima_milla_medico`, `ultima_milla_marca`, `ultima_milla_objetivo`
- [ ] Campos de validación en agenda: `inactivo`, `visita_exitosa`

### US-3: Schema de CloseUp (prescripciones)

**Como** agente IA que necesita responder preguntas de prescripciones,
**quiero** que el schema CloseUp tenga un star schema con fact table de prescripciones,
**para** poder consultar qué prescriben los médicos por producto, mercado y período.

**Acceptance Criteria:**
- [ ] Fact table `prescripcion` con campos: CDGMED, CDGPRO, CDGMAR, CDGMED_REG, CDGESP1, CDGREG_PMIX, CDGLAB, CDGCLA4, px_farma, px_delivery, fecha, tipo_dom
- [ ] Dimensiones: `medico` (PK=CDGMED), `marca`, `mercado`, `mercado_producto`, `representante`
- [ ] Tablas de visitados: `medico_rep_novisitado`, `medico_representante`, `medico_visitado`
- [ ] Tabla `mercado_modulo_linea`
- [ ] Índices en prescripcion: por CDGMED, CDGPRO, fecha, CDGREG_PMIX

### US-4: Schema de IQVIA (ventas de mercado)

**Como** agente IA que necesita responder preguntas de ventas,
**quiero** que el schema IQVIA tenga un star schema con fact table de ventas valorizadas,
**para** poder consultar ventas por producto, período, geografía y clase terapéutica.

**Acceptance Criteria:**
- [ ] Fact table `fact_mercado_valor` con: idProducto, idPeriodo, idGeografia, idClase, unidades, dosis, valor ARS, valor USD
- [ ] Dimensiones: `dim_periodo`, `dim_droga`, `dim_forma_farmaceutica`, `dim_laboratorio`, `dim_clase_terapeutica`, `dim_presentacion`, `dim_geografia`, `dim_clase`, `dim_combinacion_droga`
- [ ] Relaciones: `rel_presentacion_droga`, `rel_presentacion_forma`, `rel_producto_laboratorio`
- [ ] Campos de cruce en dim_presentacion: idProducto, adCodigoHeredado (EAN-11)

### US-5: Tablas maestras de integración

**Como** pipeline de datos que necesita cruzar las 3 fuentes,
**quiero** tablas maestras que mapeen identificadores entre fuentes,
**para** poder hacer joins cross-source en Athena.

**Acceptance Criteria:**
- [ ] `maestro_medicos`: cod_interno (CRM) ↔ cod_closeup (CDGMED)
- [ ] `maestro_integrador_producto`: cod_interno ↔ cod_closeup (CDG_PROD) ↔ cod_iqvia (idProducto/EAN-11)
- [ ] `familia_interno_a_marca_cup`: id_familia_producto → codMarcaCUP (relación N:M con posibles duplicados)
- [ ] Los maestros viven en un schema separado `maestros` dentro del mismo RDS
- [ ] Reglas: si no tiene cod_closeup → no tuvo prescripciones; si no tiene cod_iqvia → no tuvo ventas

### US-6: Datos sintéticos coherentes

**Como** equipo de desarrollo que necesita validar queries cross-source,
**quiero** datos sintéticos que sean coherentes entre las 3 fuentes,
**para** que las queries de validación devuelvan resultados realistas.

**Acceptance Criteria:**
- [ ] Los médicos en `maestro_medicos` existen tanto en `crm_interno.doctor` como en `closeup.medico`
- [ ] Los productos en `maestro_integrador_producto` existen en las tablas correspondientes de cada fuente
- [ ] Las prescripciones son de productos que existen en `closeup.marca`
- [ ] Los productos foco del CRM tienen mapeo en los maestros
- [ ] Volúmenes: ~50 APMs, ~3000 médicos, ~150 productos, ~3M prescripciones, ~2M ventas IQVIA
- [ ] Distribución Pareto en prescripciones (pocos médicos prescriben mucho)
- [ ] Crecimiento YoY mix de positivos y negativos
- [ ] 24 meses de historial en fact tables

### US-7: Validación del schema

**Como** desarrollador que va a construir el pipeline DMS,
**quiero** poder ejecutar queries de prueba sobre cada schema individual,
**para** confirmar que los datos tienen sentido antes de configurar la ingesta.

**Acceptance Criteria:**
- [ ] Query de prueba CRM: "médicos asignados a un APM con sus productos foco"
- [ ] Query de prueba CloseUp: "top 5 productos prescritos por un médico"
- [ ] Query de prueba IQVIA: "ventas de un producto por período"
- [ ] Query de prueba cross-source (via maestros): "prescripciones de productos foco de un APM"
- [ ] Todas las queries devuelven resultados no vacíos con datos coherentes
