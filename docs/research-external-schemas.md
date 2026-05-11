# Investigación: Schemas de Fuentes Externas para Simulación

> Documento de investigación para diseñar los schemas sintéticos de RDS que simulen las 3 fuentes de datos externas del road-to-prod. Basado en información pública de IQVIA, Close-Up International, y patrones estándar de la industria farmacéutica.

## Contexto

Los datasets de IQVIA y Close-Up son propietarios — no publican sus schemas. Sin embargo, entre la documentación pública de ambos proveedores, los patrones de Oracle Siebel Pharma Analytics (que modela exactamente estos datasets), y el conocimiento de dominio del `road-to-prod.md`, podemos reconstruir schemas representativos que respeten:

1. La estructura dimensional real (star schema)
2. Las relaciones entre entidades
3. Los volúmenes relativos (fact tables grandes, dimensiones chicas)
4. Las claves que NO coinciden entre fuentes (el desafío central)

---

## Fuente 1: Sistema Interno del Laboratorio (CRM)

### Características
- Schema **normalizado** (OLTP), no dimensional
- Decenas de tablas relacionadas
- Cambios diarios (operacional)
- Tamaño: miles a decenas de miles de rows por tabla

### Schema propuesto para simulación

```sql
-- ============================================================
-- SCHEMA: crm_interno
-- Simula el sistema CRM propio del laboratorio
-- ============================================================

-- Tabla de APMs (visitadores médicos)
CREATE TABLE crm_interno.apm (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) UNIQUE NOT NULL,  -- ej: "APM-001"
    nombre          VARCHAR(100) NOT NULL,
    apellido        VARCHAR(100) NOT NULL,
    email           VARCHAR(200),
    telefono        VARCHAR(50),
    zona_id         INTEGER REFERENCES crm_interno.zona(id),
    gerente_id      INTEGER REFERENCES crm_interno.apm(id),  -- supervisor
    activo          BOOLEAN DEFAULT true,
    fecha_ingreso   DATE
);

-- Zonas geográficas
CREATE TABLE crm_interno.zona (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) UNIQUE NOT NULL,
    nombre          VARCHAR(100) NOT NULL,       -- ej: "Belgrano", "Palermo"
    region          VARCHAR(100),                -- ej: "CABA Norte"
    provincia       VARCHAR(100)                 -- ej: "Buenos Aires"
);

-- Especialidades médicas
CREATE TABLE crm_interno.especialidad (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) UNIQUE NOT NULL,
    nombre          VARCHAR(100) NOT NULL        -- ej: "Cardiología", "Gastroenterología"
);

-- Médicos (tabla central del CRM)
CREATE TABLE crm_interno.doctor (
    id              SERIAL PRIMARY KEY,
    matricula_nacional VARCHAR(20) UNIQUE,       -- MN (clave interna del lab)
    nombre          VARCHAR(100) NOT NULL,
    apellido        VARCHAR(100) NOT NULL,
    email           VARCHAR(200),
    telefono1       VARCHAR(50),
    telefono2       VARCHAR(50),
    especialidad_id INTEGER REFERENCES crm_interno.especialidad(id),
    zona_id         INTEGER REFERENCES crm_interno.zona(id),
    direccion       TEXT,
    hospital        VARCHAR(200),
    facultad        VARCHAR(200),
    intereses       TEXT,                        -- hobbies, rapport
    fecha_nacimiento DATE,
    cadencia        VARCHAR(20) NOT NULL         -- Mensual|Trimestral|Semestral|Anual|Digital
        CHECK (cadencia IN ('Mensual','Trimestral','Semestral','Anual','Digital')),
    activo          BOOLEAN DEFAULT true,
    latitud         DECIMAL(10,7),
    longitud        DECIMAL(10,7)
);

-- Cartera médica: asignación APM ↔ Doctor
CREATE TABLE crm_interno.cartera_medica (
    id              SERIAL PRIMARY KEY,
    apm_id          INTEGER NOT NULL REFERENCES crm_interno.apm(id),
    doctor_id       INTEGER NOT NULL REFERENCES crm_interno.doctor(id),
    fecha_asignacion DATE NOT NULL,
    activa          BOOLEAN DEFAULT true,
    UNIQUE(apm_id, doctor_id)
);

-- Líneas de producto del laboratorio
CREATE TABLE crm_interno.linea (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) UNIQUE NOT NULL,
    nombre          VARCHAR(100) NOT NULL        -- ej: "Línea Cardio", "Línea Gastro"
);

-- Asignación de líneas a APMs
CREATE TABLE crm_interno.linea_apm (
    id              SERIAL PRIMARY KEY,
    apm_id          INTEGER NOT NULL REFERENCES crm_interno.apm(id),
    linea_id        INTEGER NOT NULL REFERENCES crm_interno.linea(id),
    UNIQUE(apm_id, linea_id)
);

-- Familias de producto (SKU del laboratorio)
CREATE TABLE crm_interno.familia_producto (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(30) UNIQUE NOT NULL,  -- código interno del lab
    nombre          VARCHAR(200) NOT NULL,        -- ej: "PAMOXET 20mg x 30"
    principio_activo VARCHAR(200),                -- ej: "Omeprazol"
    linea_id        INTEGER REFERENCES crm_interno.linea(id),
    tipo            VARCHAR(10) CHECK (tipo IN ('OTC', 'RX')),
    presentacion    VARCHAR(100),                 -- ej: "Comprimidos x 30"
    activo          BOOLEAN DEFAULT true
);

-- Ciclos promocionales
CREATE TABLE crm_interno.ciclo (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL,         -- ej: "Ciclo 2026-Q1"
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE NOT NULL,
    activo          BOOLEAN DEFAULT false
);

-- Grilla: qué productos se promocionan en qué línea durante un ciclo
CREATE TABLE crm_interno.grilla (
    id              SERIAL PRIMARY KEY,
    linea_id        INTEGER NOT NULL REFERENCES crm_interno.linea(id),
    ciclo_id        INTEGER NOT NULL REFERENCES crm_interno.ciclo(id),
    orden           INTEGER                       -- orden de presentación
);

-- Categorías de promoción
CREATE TABLE crm_interno.categoria (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(30) UNIQUE NOT NULL   -- 'foco', 'hiperfoco', 'recordatorio', 'lanzamiento'
);

-- Detalle de promoción: qué producto, en qué grilla, con qué categoría
CREATE TABLE crm_interno.detalle_promocion_producto (
    id                  SERIAL PRIMARY KEY,
    grilla_id           INTEGER NOT NULL REFERENCES crm_interno.grilla(id),
    familia_producto_id INTEGER NOT NULL REFERENCES crm_interno.familia_producto(id),
    categoria_id        INTEGER NOT NULL REFERENCES crm_interno.categoria(id),
    orden_presentacion  INTEGER
);


-- Agenda de visitas (historial)
CREATE TABLE crm_interno.agenda (
    id              SERIAL PRIMARY KEY,
    apm_id          INTEGER NOT NULL REFERENCES crm_interno.apm(id),
    doctor_id       INTEGER NOT NULL REFERENCES crm_interno.doctor(id),
    fecha_visita    DATE NOT NULL,
    tipo_visita     VARCHAR(20) NOT NULL
        CHECK (tipo_visita IN ('Presencial','Virtual','Telefonica')),
    zona_id         INTEGER REFERENCES crm_interno.zona(id),
    notas           TEXT,
    duracion_min    INTEGER
);

-- Productos presentados en cada visita
CREATE TABLE crm_interno.agenda_producto (
    id              SERIAL PRIMARY KEY,
    agenda_id       INTEGER NOT NULL REFERENCES crm_interno.agenda(id),
    familia_producto_id INTEGER NOT NULL REFERENCES crm_interno.familia_producto(id),
    orden           INTEGER,
    muestras_entregadas INTEGER DEFAULT 0
);

-- Visitas planificadas (futuras)
CREATE TABLE crm_interno.visita_planificada (
    id              SERIAL PRIMARY KEY,
    apm_id          INTEGER NOT NULL REFERENCES crm_interno.apm(id),
    doctor_id       INTEGER NOT NULL REFERENCES crm_interno.doctor(id),
    fecha_planificada DATE NOT NULL,
    motivo          TEXT,
    estado          VARCHAR(20) DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente','confirmada','cancelada','realizada'))
);
```

### Volúmenes sugeridos para simulación

| Tabla | Rows | Justificación |
|-------|------|---------------|
| `apm` | 50-100 | Simula un equipo de campo mediano |
| `doctor` | 2,000-5,000 | ~30-50 médicos por APM |
| `zona` | 50-100 | Barrios/localidades |
| `cartera_medica` | 5,000-10,000 | Asignaciones activas |
| `familia_producto` | 100-200 | Portfolio del laboratorio |
| `agenda` | 50,000-100,000 | ~2 años de historial, ~5 visitas/día/APM |
| `agenda_producto` | 150,000-300,000 | ~3 productos por visita |
| `ciclo` | 8-12 | Últimos 2-3 años de ciclos |
| `grilla` | 200-400 | Líneas × ciclos |
| `detalle_promocion_producto` | 500-1,000 | Productos en grillas |

---

## Fuente 2: Close-Up (Prescripciones)

### Características
- Schema **dimensional** (star schema clásico)
- Fact table de prescripciones MUY grande
- Actualización mensual o quincenal
- Cubre ~90% de los médicos del país via panel de farmacias (~20-25% de prescripciones capturadas, proyectadas al total)
- Identificador propio de médico: `CDGMED` (NO coincide con el id interno del laboratorio)
- Identificador propio de producto: código de marca CUP

### Schema propuesto para simulación

```sql
-- ============================================================
-- SCHEMA: closeup
-- Simula los datos de prescripciones de Close-Up International
-- Star schema con fact table central de prescripciones
-- ============================================================

-- Dimensión: Médicos (con identificador propio de CloseUp)
CREATE TABLE closeup.medico (
    CDGMED          VARCHAR(20) PRIMARY KEY,      -- ID propio de CloseUp (NO es el MN del lab)
    nombre          VARCHAR(200),
    especialidad    VARCHAR(100),
    localidad       VARCHAR(100),
    provincia       VARCHAR(100),
    cdgreg_pmix     VARCHAR(20),                  -- código de región/brick de CloseUp
    activo          BOOLEAN DEFAULT true
);

-- Dimensión: Marcas/Productos (con código propio de CloseUp)
CREATE TABLE closeup.marca (
    codigo_marca    VARCHAR(20) PRIMARY KEY,       -- ID propio de CloseUp
    nombre_marca    VARCHAR(200) NOT NULL,         -- ej: "PAMOXET 20 MG COMP X 30"
    laboratorio     VARCHAR(200),                  -- nombre del laboratorio fabricante
    principio_activo VARCHAR(200),
    forma_farmaceutica VARCHAR(100),               -- ej: "Comprimidos"
    concentracion   VARCHAR(50)                    -- ej: "20 mg"
);

-- Dimensión: Mercados (agrupaciones terapéuticas de CloseUp)
CREATE TABLE closeup.mercado (
    CDG_MERCADO     VARCHAR(20) PRIMARY KEY,
    nombre_mercado  VARCHAR(200) NOT NULL,         -- ej: "Antiulcerosos", "Antihipertensivos"
    clase_terapeutica VARCHAR(200)
);

-- Relación: qué productos pertenecen a qué mercado
CREATE TABLE closeup.mercado_producto (
    id              SERIAL PRIMARY KEY,
    CDG_MERCADO     VARCHAR(20) NOT NULL REFERENCES closeup.mercado(CDG_MERCADO),
    CDG_PROD        VARCHAR(20) NOT NULL,          -- código de producto en CloseUp
    codigo_marca    VARCHAR(20) REFERENCES closeup.marca(codigo_marca),
    UNIQUE(CDG_MERCADO, CDG_PROD)
);

-- Dimensión: Representantes (visitadores según CloseUp)
CREATE TABLE closeup.representante (
    id_rep          VARCHAR(20) PRIMARY KEY,
    nombre          VARCHAR(200),
    laboratorio     VARCHAR(200)
);

-- FACT TABLE: Prescripciones (tabla central, la más grande)
-- Cada row = un médico prescribió un producto en un período
CREATE TABLE closeup.prescripcion (
    id              BIGSERIAL PRIMARY KEY,
    CDGMED          VARCHAR(20) NOT NULL,          -- FK a medico
    CDGPRO          VARCHAR(20) NOT NULL,          -- código de producto prescrito
    anio            SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    cdgreg_pmix     VARCHAR(20),                   -- región/brick del médico
    cantidad        INTEGER NOT NULL,              -- unidades prescritas (proyectadas)
    recetas         INTEGER,                       -- número de recetas
    -- Partitioning columns para performance
    CONSTRAINT fk_medico FOREIGN KEY (CDGMED) REFERENCES closeup.medico(CDGMED)
);

-- Índices para queries frecuentes
CREATE INDEX idx_prescripcion_medico ON closeup.prescripcion(CDGMED);
CREATE INDEX idx_prescripcion_producto ON closeup.prescripcion(CDGPRO);
CREATE INDEX idx_prescripcion_periodo ON closeup.prescripcion(anio, mes);
CREATE INDEX idx_prescripcion_region ON closeup.prescripcion(cdgreg_pmix);

-- Tabla de visitados/no visitados por representante
CREATE TABLE closeup.visitado (
    id              SERIAL PRIMARY KEY,
    CDGMED          VARCHAR(20) NOT NULL REFERENCES closeup.medico(CDGMED),
    id_rep          VARCHAR(20) NOT NULL REFERENCES closeup.representante(id_rep),
    anio            SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    visitado        BOOLEAN NOT NULL,              -- true = visitado en ese período
    UNIQUE(CDGMED, id_rep, anio, mes)
);
```

### Volúmenes sugeridos para simulación

| Tabla | Rows | Justificación |
|-------|------|---------------|
| `medico` | 10,000-20,000 | Universo de médicos que CloseUp trackea en la zona |
| `marca` | 2,000-5,000 | Productos de todos los laboratorios en los mercados relevantes |
| `mercado` | 50-100 | Categorías terapéuticas |
| `mercado_producto` | 5,000-10,000 | Productos × mercados |
| `prescripcion` | **3,000,000-5,000,000** | 24 meses × 15,000 médicos × ~10 productos/mes |
| `representante` | 500-1,000 | Reps de todos los laboratorios |
| `visitado` | 200,000-500,000 | Médicos × reps × meses |

**Nota sobre volumen**: en producción real, la fact table de prescripciones puede tener cientos de millones de rows (todos los médicos del país × todos los productos × todos los meses históricos). Para simulación, 3-5M rows es suficiente para que Athena muestre tiempos de query realistas y el partitioning tenga sentido.


---

## Fuente 3: IQVIA (Ventas de Mercado)

### Características
- Schema **dimensional puro** (star schema)
- Fact table de ventas valorizadas (unidades + valor monetario)
- Actualización mensual
- NO tiene nivel médico (solo agregado por producto × período × geografía)
- Identificador propio de producto: `idProducto` (código EAN-11 o interno IQVIA)
- Dimensiones estándar: droga, forma farmacéutica, presentación, laboratorio, clase terapéutica, período

### Schema propuesto para simulación

```sql
-- ============================================================
-- SCHEMA: iqvia
-- Simula los datos de ventas de mercado de IQVIA
-- Star schema puro con fact table de ventas valorizadas
-- ============================================================

-- Dimensión: Período (año-mes)
CREATE TABLE iqvia.dim_periodo (
    idPeriodo       VARCHAR(10) PRIMARY KEY,       -- ej: "2026-01", "2025-12"
    anio            SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    trimestre       SMALLINT NOT NULL,             -- 1-4
    semestre        SMALLINT NOT NULL,             -- 1-2
    nombre_mes      VARCHAR(20)                    -- "Enero", "Febrero"...
);

-- Dimensión: Droga (principio activo)
CREATE TABLE iqvia.dim_droga (
    idDroga         VARCHAR(20) PRIMARY KEY,
    nombre_droga    VARCHAR(200) NOT NULL,         -- ej: "Omeprazol", "Enalapril"
    grupo_quimico   VARCHAR(200),
    subgrupo_quimico VARCHAR(200)
);

-- Dimensión: Forma farmacéutica
CREATE TABLE iqvia.dim_forma (
    idForma         VARCHAR(20) PRIMARY KEY,
    nombre_forma    VARCHAR(100) NOT NULL          -- ej: "Comprimidos", "Cápsulas", "Inyectable"
);

-- Dimensión: Laboratorio
CREATE TABLE iqvia.dim_laboratorio (
    idLaboratorio   VARCHAR(20) PRIMARY KEY,
    nombre_laboratorio VARCHAR(200) NOT NULL,      -- ej: "Roemmers", "Bagó", "Pfizer"
    pais_origen     VARCHAR(100),
    tipo            VARCHAR(50)                    -- "Nacional", "Multinacional"
);

-- Dimensión: Clase terapéutica (ATC-like)
CREATE TABLE iqvia.dim_clase_terapeutica (
    idClase         VARCHAR(20) PRIMARY KEY,
    nivel1          VARCHAR(200),                  -- ej: "Sistema Cardiovascular"
    nivel2          VARCHAR(200),                  -- ej: "Agentes que actúan sobre el sistema RAA"
    nivel3          VARCHAR(200),                  -- ej: "Inhibidores de la ECA"
    nivel4          VARCHAR(200)                   -- ej: "Enalapril"
);

-- Dimensión: Presentación (el producto comercial específico)
CREATE TABLE iqvia.dim_presentacion (
    idProducto      VARCHAR(20) PRIMARY KEY,       -- ID propio de IQVIA (NO es el del lab)
    nombre_producto VARCHAR(300) NOT NULL,         -- ej: "LOTRIAL 10 MG COMP X 30"
    idDroga         VARCHAR(20) REFERENCES iqvia.dim_droga(idDroga),
    idForma         VARCHAR(20) REFERENCES iqvia.dim_forma(idForma),
    idLaboratorio   VARCHAR(20) REFERENCES iqvia.dim_laboratorio(idLaboratorio),
    idClase         VARCHAR(20) REFERENCES iqvia.dim_clase_terapeutica(idClase),
    concentracion   VARCHAR(50),                   -- ej: "10 mg"
    unidades_envase INTEGER,                       -- ej: 30
    codigo_barras   VARCHAR(20),                   -- EAN-11 (otra clave de cruce)
    tipo            VARCHAR(10) CHECK (tipo IN ('OTC', 'RX'))
);

-- Dimensión: Geografía (canal de distribución / zona)
CREATE TABLE iqvia.dim_geografia (
    idGeografia     VARCHAR(20) PRIMARY KEY,
    nombre          VARCHAR(200) NOT NULL,         -- ej: "CABA Norte", "GBA Sur"
    provincia       VARCHAR(100),
    region          VARCHAR(100),
    canal           VARCHAR(50)                    -- "Farmacias", "Droguerías", "Hospitales"
);

-- FACT TABLE: Ventas de mercado valorizadas
-- Cada row = ventas de un producto en un período en una geografía
CREATE TABLE iqvia.fact_mercado_valor (
    id              BIGSERIAL PRIMARY KEY,
    idProducto      VARCHAR(20) NOT NULL REFERENCES iqvia.dim_presentacion(idProducto),
    idPeriodo       VARCHAR(10) NOT NULL REFERENCES iqvia.dim_periodo(idPeriodo),
    idGeografia     VARCHAR(20) NOT NULL REFERENCES iqvia.dim_geografia(idGeografia),
    unidades        INTEGER NOT NULL,              -- unidades vendidas
    valores_ars     DECIMAL(15,2),                 -- valor en pesos argentinos
    valores_usd     DECIMAL(15,2),                 -- valor en dólares (referencia)
    dosis           DECIMAL(15,2),                 -- DDD (Defined Daily Doses)
    crecimiento_yoy DECIMAL(8,2),                  -- % crecimiento vs mismo período año anterior
    market_share_unidades DECIMAL(8,4),            -- share en unidades dentro de su clase
    market_share_valores  DECIMAL(8,4)             -- share en valores dentro de su clase
);

-- Índices para queries frecuentes
CREATE INDEX idx_fact_periodo ON iqvia.fact_mercado_valor(idPeriodo);
CREATE INDEX idx_fact_producto ON iqvia.fact_mercado_valor(idProducto);
CREATE INDEX idx_fact_geo ON iqvia.fact_mercado_valor(idGeografia);
```

### Volúmenes sugeridos para simulación

| Tabla | Rows | Justificación |
|-------|------|---------------|
| `dim_periodo` | 36-48 | 3-4 años de meses |
| `dim_droga` | 500-1,000 | Principios activos del mercado |
| `dim_forma` | 20-30 | Formas farmacéuticas |
| `dim_laboratorio` | 100-200 | Laboratorios del mercado argentino |
| `dim_clase_terapeutica` | 200-500 | Clases ATC relevantes |
| `dim_presentacion` | 5,000-10,000 | Productos comerciales |
| `dim_geografia` | 50-100 | Zonas/canales |
| `fact_mercado_valor` | **2,000,000-4,000,000** | 8,000 productos × 36 meses × ~15 geografías |

---

## Tablas Maestras de Integración

### El problema central

Las 3 fuentes usan identificadores distintos para los mismos conceptos:

| Concepto | CRM Interno | CloseUp | IQVIA |
|----------|-------------|---------|-------|
| Médico | `doctor.id` (MN) | `medico.CDGMED` | ❌ No tiene |
| Producto | `familia_producto.codigo` | `marca.codigo_marca` | `dim_presentacion.idProducto` |

### Schema de maestros

```sql
-- ============================================================
-- SCHEMA: maestros
-- Tablas de integración que permiten cruzar las 3 fuentes
-- Son pequeñas pero CRÍTICAS
-- ============================================================

-- Maestro de médicos: mapea ID interno del lab ↔ CDGMED de CloseUp
CREATE TABLE maestros.maestro_medicos (
    id              SERIAL PRIMARY KEY,
    cod_interno     INTEGER NOT NULL,              -- FK conceptual a crm_interno.doctor.id
    cod_closeup     VARCHAR(20) NOT NULL,          -- FK conceptual a closeup.medico.CDGMED
    nombre_verificado VARCHAR(200),                -- para validación manual
    fecha_mapeo     DATE,
    confianza       VARCHAR(20) DEFAULT 'alta'     -- alta|media|baja (calidad del match)
        CHECK (confianza IN ('alta','media','baja')),
    UNIQUE(cod_interno),
    UNIQUE(cod_closeup)
);

-- Maestro integrador de productos: mapea código lab ↔ código CUP ↔ código IQVIA
CREATE TABLE maestros.maestro_integrador_producto (
    id              SERIAL PRIMARY KEY,
    cod_interno     VARCHAR(30),                   -- FK conceptual a crm_interno.familia_producto.codigo
    cod_closeup     VARCHAR(20),                   -- FK conceptual a closeup.marca.codigo_marca
    cod_iqvia       VARCHAR(20),                   -- FK conceptual a iqvia.dim_presentacion.idProducto
    codigo_barras   VARCHAR(20),                   -- EAN-11 (clave alternativa de cruce)
    nombre_unificado VARCHAR(300),                 -- nombre canónico del producto
    principio_activo VARCHAR(200),
    fecha_mapeo     DATE,
    -- Al menos uno de los 3 códigos debe existir
    CONSTRAINT al_menos_un_codigo CHECK (
        cod_interno IS NOT NULL OR cod_closeup IS NOT NULL OR cod_iqvia IS NOT NULL
    )
);

-- Familia interna a marca CloseUp (relación N:M posible)
-- Un producto interno puede mapear a varias marcas CUP (presentaciones distintas)
CREATE TABLE maestros.familia_interno_a_marca_cup (
    id              SERIAL PRIMARY KEY,
    cod_interno     VARCHAR(30) NOT NULL,          -- familia_producto.codigo
    codigo_marca    VARCHAR(20) NOT NULL,          -- closeup.marca.codigo_marca
    relacion        VARCHAR(50) DEFAULT 'exacta'   -- exacta|parcial|generico
        CHECK (relacion IN ('exacta','parcial','generico')),
    UNIQUE(cod_interno, codigo_marca)
);
```

### Volúmenes sugeridos

| Tabla | Rows | Justificación |
|-------|------|---------------|
| `maestro_medicos` | 2,000-5,000 | Solo médicos que el lab atiende Y CloseUp trackea |
| `maestro_integrador_producto` | 200-500 | Productos del lab + competidores clave |
| `familia_interno_a_marca_cup` | 300-600 | Relaciones producto interno → marca CUP |

### Reglas de negocio de los maestros (del road-to-prod)

1. Si un producto **no tiene** `cod_closeup` → no tuvo prescripciones registradas
2. Si un producto **no tiene** `cod_iqvia` ni `codigo_barras` → no tuvo ventas registradas
3. Un médico lo atiende el laboratorio **solo si** tiene `cod_interno` en `maestro_medicos`
4. Los productos foco son a nivel APM (por sus líneas); los productos objetivo son a nivel médico


---

## Queries de Validación Cross-Source

Estas son las queries que el sistema debe poder responder cruzando las 3 fuentes. Sirven como test de que los schemas y maestros están bien diseñados.

### Query 1: "Top 5 productos que más prescribe el Dr. X" (CRM + CloseUp)

```sql
-- Requiere: maestro_medicos para cruzar doctor.id → CDGMED
SELECT m.codigo_marca, mk.nombre_marca, SUM(p.cantidad) as total_prescripciones
FROM closeup.prescripcion p
JOIN closeup.marca mk ON mk.codigo_marca = p.CDGPRO  -- asumiendo CDGPRO = codigo_marca
JOIN maestros.maestro_medicos mm ON mm.cod_closeup = p.CDGMED
WHERE mm.cod_interno = :doctor_id
  AND p.anio >= EXTRACT(YEAR FROM CURRENT_DATE) - 1
GROUP BY m.codigo_marca, mk.nombre_marca
ORDER BY total_prescripciones DESC
LIMIT 5;
```

### Query 2: "Productos foco del APM con EVO trimestral negativa" (CRM + IQVIA)

```sql
-- Requiere: maestro_integrador_producto para cruzar cod_interno → cod_iqvia
WITH productos_foco AS (
    SELECT fp.codigo as cod_interno, fp.nombre
    FROM crm_interno.linea_apm la
    JOIN crm_interno.grilla g ON g.linea_id = la.linea_id
    JOIN crm_interno.detalle_promocion_producto dpp ON dpp.grilla_id = g.id
    JOIN crm_interno.categoria c ON c.id = dpp.categoria_id
    JOIN crm_interno.ciclo ci ON ci.id = g.ciclo_id
    JOIN crm_interno.familia_producto fp ON fp.id = dpp.familia_producto_id
    WHERE la.apm_id = :apm_id
      AND c.nombre IN ('foco', 'hiperfoco')
      AND ci.activo = true
)
SELECT pf.nombre, fmv.idPeriodo, fmv.crecimiento_yoy
FROM productos_foco pf
JOIN maestros.maestro_integrador_producto mip ON mip.cod_interno = pf.cod_interno
JOIN iqvia.fact_mercado_valor fmv ON fmv.idProducto = mip.cod_iqvia
WHERE fmv.crecimiento_yoy < 0
  AND fmv.idPeriodo >= '2025-10'  -- último trimestre
ORDER BY fmv.crecimiento_yoy ASC;
```

### Query 3: "Médicos que crecen en prescripción de mis foco y los visito poco" (las 3 fuentes)

```sql
-- La query más compleja: cruza CRM + CloseUp + maestros
WITH productos_foco AS (
    -- Productos foco del APM (CRM interno)
    SELECT fp.codigo as cod_interno
    FROM crm_interno.linea_apm la
    JOIN crm_interno.grilla g ON g.linea_id = la.linea_id
    JOIN crm_interno.detalle_promocion_producto dpp ON dpp.grilla_id = g.id
    JOIN crm_interno.categoria c ON c.id = dpp.categoria_id
    JOIN crm_interno.ciclo ci ON ci.id = g.ciclo_id
    JOIN crm_interno.familia_producto fp ON fp.id = dpp.familia_producto_id
    WHERE la.apm_id = :apm_id
      AND c.nombre IN ('foco', 'hiperfoco')
      AND ci.activo = true
),
codigos_cup_foco AS (
    -- Mapear productos foco a códigos CloseUp
    SELECT fimc.codigo_marca
    FROM productos_foco pf
    JOIN maestros.familia_interno_a_marca_cup fimc ON fimc.cod_interno = pf.cod_interno
),
prescripciones_por_medico AS (
    -- Prescripciones de productos foco por médico (últimos 6 meses vs 6 meses anteriores)
    SELECT
        p.CDGMED,
        SUM(CASE WHEN (p.anio * 12 + p.mes) >= (EXTRACT(YEAR FROM CURRENT_DATE) * 12 + EXTRACT(MONTH FROM CURRENT_DATE) - 6)
                 THEN p.cantidad ELSE 0 END) as px_recientes,
        SUM(CASE WHEN (p.anio * 12 + p.mes) >= (EXTRACT(YEAR FROM CURRENT_DATE) * 12 + EXTRACT(MONTH FROM CURRENT_DATE) - 12)
                  AND (p.anio * 12 + p.mes) < (EXTRACT(YEAR FROM CURRENT_DATE) * 12 + EXTRACT(MONTH FROM CURRENT_DATE) - 6)
                 THEN p.cantidad ELSE 0 END) as px_anteriores
    FROM closeup.prescripcion p
    WHERE p.CDGPRO IN (SELECT codigo_marca FROM codigos_cup_foco)
    GROUP BY p.CDGMED
    HAVING SUM(p.cantidad) > 0
),
medicos_creciendo AS (
    SELECT CDGMED,
           px_recientes,
           px_anteriores,
           CASE WHEN px_anteriores > 0
                THEN ((px_recientes - px_anteriores)::DECIMAL / px_anteriores * 100)
                ELSE 100 END as crecimiento_pct
    FROM prescripciones_por_medico
    WHERE px_recientes > px_anteriores
),
frecuencia_visitas AS (
    -- Última visita y frecuencia del APM a cada médico (CRM interno)
    SELECT
        cm.doctor_id,
        MAX(a.fecha_visita) as ultima_visita,
        COUNT(a.id) as total_visitas_12m
    FROM crm_interno.cartera_medica cm
    LEFT JOIN crm_interno.agenda a ON a.doctor_id = cm.doctor_id AND a.apm_id = cm.apm_id
        AND a.fecha_visita >= CURRENT_DATE - INTERVAL '12 months'
    WHERE cm.apm_id = :apm_id AND cm.activa = true
    GROUP BY cm.doctor_id
)
SELECT
    d.nombre || ' ' || d.apellido as medico,
    d.especialidad_id,
    mc.crecimiento_pct,
    fv.ultima_visita,
    fv.total_visitas_12m,
    CURRENT_DATE - fv.ultima_visita as dias_sin_visitar
FROM medicos_creciendo mc
JOIN maestros.maestro_medicos mm ON mm.cod_closeup = mc.CDGMED
JOIN crm_interno.doctor d ON d.id = mm.cod_interno
JOIN frecuencia_visitas fv ON fv.doctor_id = d.id
WHERE fv.total_visitas_12m <= 2  -- "los visito poco"
ORDER BY mc.crecimiento_pct DESC, fv.total_visitas_12m ASC
LIMIT 20;
```

---

## Consideraciones para la Generación de Datos Sintéticos

### Coherencia entre fuentes

Los datos sintéticos deben ser **coherentes entre sí**:

1. Los médicos en `maestro_medicos` deben existir tanto en `crm_interno.doctor` como en `closeup.medico`
2. Los productos en `maestro_integrador_producto` deben existir en las tablas correspondientes de cada fuente
3. Las prescripciones deben ser de productos que existen en `closeup.marca`
4. Las ventas IQVIA deben ser de productos que existen en `iqvia.dim_presentacion`
5. Los productos foco del CRM deben tener mapeo en los maestros (para que las queries cross-source funcionen)

### Realismo en los datos

- **Prescripciones**: distribución Pareto (pocos médicos prescriben mucho, muchos prescriben poco)
- **Ventas**: estacionalidad (gripes en invierno, alergias en primavera)
- **Crecimiento YoY**: mix de positivos y negativos, con tendencia general positiva
- **Cadencias**: distribución realista (mayoría Trimestral/Semestral, pocos Mensual)
- **Especialidades**: concentración en las más comunes (Clínica Médica, Cardiología, Gastro, Pediatría)

### Script de generación

Recomiendo un script Python con `faker` + `numpy` que:

1. Genera las dimensiones primero (médicos, productos, zonas)
2. Genera los maestros de integración (asegurando coherencia)
3. Genera las fact tables con distribuciones realistas
4. Exporta a CSV o inserta directamente en RDS

---

## Impacto en la Estructura de Specs

Esta investigación confirma y refina la estructura de specs propuesta:

### Spec 1 (`data-sources-simulation`) se descompone en:

- **1a**: Crear VPC + RDS + schemas vacíos (DDL)
- **1b**: Script de generación de datos sintéticos (Python)
- **1c**: Validación: queries de prueba sobre cada schema individual

### Spec 4 (`maestros-integration`) es más crítico de lo esperado:

Los maestros son el pegamento entre fuentes. Sin ellos, ninguna query cross-source funciona. Conviene:
- Generarlos como parte del script de datos sintéticos (spec 1b)
- Pero validarlos como spec separado con queries de prueba cross-source

### Spec 5 (`athena-cross-source`) tiene queries de referencia claras:

Las 3 queries de validación de este documento son el test suite mínimo para validar que el lake funciona end-to-end.

---

## Actualización: Validación con Estructura Real del Cliente

> Basado en documentación proporcionada por el cliente (descripciones de tablas y preguntas priorizadas). Se mantiene nomenclatura agnóstica (CRM interno, no nombre propio del sistema).

### Tablas adicionales descubiertas en CRM interno

Las siguientes tablas no estaban en el modelo original y son necesarias:

```sql
-- Tags/Hobbies de médicos (para rapport)
CREATE TABLE crm_interno.tag (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    tipo            VARCHAR(50),                   -- 'deporte', 'hobby', 'aficion'
    activo          BOOLEAN DEFAULT true
);

CREATE TABLE crm_interno.tag_doctor (
    tag_id          INTEGER NOT NULL REFERENCES crm_interno.tag(id),
    doctor_id       INTEGER NOT NULL REFERENCES crm_interno.doctor(id),
    PRIMARY KEY (tag_id, doctor_id)
);

-- Estado de la cartera médica (historial de movimientos)
CREATE TABLE crm_interno.cartera_medica_estado (
    id              SERIAL PRIMARY KEY,
    apm_id          INTEGER NOT NULL REFERENCES crm_interno.apm(id),
    doctor_id       INTEGER NOT NULL REFERENCES crm_interno.doctor(id),
    estado          VARCHAR(50) NOT NULL,          -- 'alta', 'baja', 'no_aprobada', 'transferida'
    gerente_id      INTEGER REFERENCES crm_interno.apm(id),
    aprobador_id    INTEGER REFERENCES crm_interno.apm(id),
    fecha           TIMESTAMP NOT NULL,
    motivo          TEXT
);

-- Muestras entregadas en visitas
CREATE TABLE crm_interno.agenda_muestra (
    id              SERIAL PRIMARY KEY,
    agenda_id       INTEGER NOT NULL REFERENCES crm_interno.agenda(id),
    familia_producto_id INTEGER NOT NULL REFERENCES crm_interno.familia_producto(id),
    cantidad        INTEGER NOT NULL,
    lote            VARCHAR(50),
    codigo_producto VARCHAR(50)
);

-- Catálogo de productos (puente entre familia_producto y códigos externos)
CREATE TABLE crm_interno.catalogo_productos (
    id              SERIAL PRIMARY KEY,
    codigo_sap      VARCHAR(30),
    familia_producto_id INTEGER REFERENCES crm_interno.familia_producto(id),
    especialidad_id INTEGER REFERENCES crm_interno.especialidad(id),
    codigo_dispro   VARCHAR(30),
    codigo_ean      VARCHAR(20),                   -- EAN del producto (clave de cruce con IQVIA)
    activo          BOOLEAN DEFAULT true
);

-- Datos de visita (frecuencia y configuración)
CREATE TABLE crm_interno.datos_visita (
    id              SERIAL PRIMARY KEY,
    institucion_id  INTEGER,
    especialidad_id INTEGER REFERENCES crm_interno.especialidad(id),
    frecuencia      VARCHAR(20),                   -- frecuencia esperada de visitas
    turno_preferido VARCHAR(20)
);

-- Vistas pre-computadas de prescripciones (UltimaMilla)
-- Estas tablas viven en CRM pero contienen datos cruzados con CUP

-- Resumen de prescripciones por médico (EVO trimestral + shares)
CREATE TABLE crm_interno.ultima_milla_medico (
    id              SERIAL PRIMARY KEY,
    id_medico_cup   VARCHAR(20) NOT NULL,          -- CDGMED de CloseUp
    id_medico_crm   INTEGER,                       -- id interno del CRM
    evo_trimestral  DECIMAL(8,2),                  -- índice de evolución trimestral de Px
    share_lab_ytd   DECIMAL(8,4),                  -- % prescripción lab vs total YTD
    share_lab_mensual DECIMAL(8,4),                -- % prescripción lab vs total mensual
    share_lab_mat   DECIMAL(8,4),                  -- % prescripción lab vs total MAT
    categoria_medico VARCHAR(10)                   -- categorización del médico (potencial)
);

-- Prescripciones por médico × marca × mercado (shares)
CREATE TABLE crm_interno.ultima_milla_marca (
    id              SERIAL PRIMARY KEY,
    id_medico_cup   VARCHAR(20) NOT NULL,          -- CDGMED de CloseUp
    id_marca        VARCHAR(20) NOT NULL,          -- código de marca CUP
    id_mercado      VARCHAR(20) NOT NULL,          -- código de mercado CUP
    share_marca_mercado DECIMAL(8,4),              -- % de la marca en el mercado
    share_marca_total   DECIMAL(8,4),              -- % de la marca vs todo lo que prescribe
    categoria_medico VARCHAR(10)
);

-- Relación mercado → marca → especialidad (para productos objetivo)
CREATE TABLE crm_interno.ultima_milla_objetivo (
    id              SERIAL PRIMARY KEY,
    id_mercado      VARCHAR(20) NOT NULL,
    nombre_marca    VARCHAR(200) NOT NULL,
    id_especialidad INTEGER
);
```

### Campos adicionales en tabla `prescricao` de CloseUp

La tabla de prescripciones tiene más campos de los modelados originalmente:

```sql
-- Actualización de closeup.prescripcion con campos reales
ALTER TABLE closeup.prescripcion ADD COLUMN CDGMAR VARCHAR(20);        -- código de marca
ALTER TABLE closeup.prescripcion ADD COLUMN CDGMED_REG VARCHAR(20);    -- código médico en región
ALTER TABLE closeup.prescripcion ADD COLUMN CDGESP1 VARCHAR(20);       -- código especialidad
ALTER TABLE closeup.prescripcion ADD COLUMN CDGLAB VARCHAR(20);        -- código laboratorio
ALTER TABLE closeup.prescripcion ADD COLUMN CDGCLA4 VARCHAR(20);       -- código clase terapéutica
ALTER TABLE closeup.prescripcion ADD COLUMN px_farma INTEGER;          -- canal farma
ALTER TABLE closeup.prescripcion ADD COLUMN px_delivery INTEGER;       -- canal delivery
ALTER TABLE closeup.prescripcion ADD COLUMN fecha DATE;                -- fecha de prescripción
ALTER TABLE closeup.prescripcion ADD COLUMN tipo_dom CHAR(1);          -- 'C'=CUP, 'A'=Alternativo
```

### Tablas adicionales en CloseUp

```sql
-- Médicos no visitados por representante
CREATE TABLE closeup.medico_rep_novisitado (
    CDGMED          VARCHAR(20) NOT NULL,
    CDGMED_REG      VARCHAR(20),
    CDGREP          VARCHAR(20) NOT NULL,          -- código representante
    CDGR            VARCHAR(20),                   -- código gerente regional
    CDGD            VARCHAR(20),                   -- código gerente distrital
    nombre_rep      VARCHAR(200)
);

-- Relación médico-representante
CREATE TABLE closeup.medico_representante (
    CDGMED          VARCHAR(20) NOT NULL,
    CDGMED_REG      VARCHAR(20),
    CDGR            VARCHAR(20),
    CDGD            VARCHAR(20),
    CDGREP          VARCHAR(20) NOT NULL,
    CDGREP_NOM      VARCHAR(200),
    local           VARCHAR(200),
    bairro          VARCHAR(100),
    cap             VARCHAR(20),
    CDGESP1         VARCHAR(20)
);

-- Mercados con módulos y líneas
CREATE TABLE closeup.mercado_modulo_linea (
    CDG_MERCADO     VARCHAR(20) NOT NULL REFERENCES closeup.mercado(CDG_MERCADO),
    edicion         VARCHAR(50),
    descripcion     VARCHAR(200),
    codigo_usuario  VARCHAR(20),
    codigo_pais     VARCHAR(10)
);
```

### Tabla adicional en IQVIA

```sql
-- Clase (agrupación de mercado para fact_mercado_valor)
CREATE TABLE iqvia.dim_clase (
    idClase         VARCHAR(20) PRIMARY KEY,
    codClase        VARCHAR(20),
    descripcion     VARCHAR(200) NOT NULL
);

-- Agregar FK en fact_mercado_valor
ALTER TABLE iqvia.fact_mercado_valor ADD COLUMN idClase VARCHAR(20) REFERENCES iqvia.dim_clase(idClase);
```

### Distinción clave: Productos Foco vs Productos Objetivo

| Concepto | Nivel | Tablas involucradas | Lógica |
|----------|-------|--------------------|----|
| **Productos Foco/Hiperfoco** | A nivel APM (por sus líneas) | familia_producto → detalle_promocion_producto → grilla → categoría → ciclo → linea → linea_apm | Qué productos debe promocionar el APM en el ciclo actual |
| **Productos Objetivo** | A nivel médico | ultima_milla_medico → ultima_milla_marca → ultima_milla_objetivo → marca | Qué productos debería prescribir un médico específico según su perfil |

### Regla de validación de visitas

Una visita en la tabla `agenda` es válida **solo si**:
- `inactivo = False`
- `visita_exitosa = True`

Agregar estos campos al schema:

```sql
ALTER TABLE crm_interno.agenda ADD COLUMN inactivo BOOLEAN DEFAULT false;
ALTER TABLE crm_interno.agenda ADD COLUMN visita_exitosa BOOLEAN DEFAULT true;
```

### Preguntas priorizadas por el cliente (test suite para la ontología)

| # | Prioridad | Pregunta | Fuentes | Carril esperado |
|---|-----------|----------|---------|-----------------|
| 1 | Gran valor | Recomendame médicos según prescripciones y productos foco | CRM + CUP + maestros | Async |
| 2 | Gran valor | Médicos creciendo en foco que visito poco | CRM + CUP + maestros | Async |
| 3 | Gran valor | Médicos a visitar para crecer con producto X | CRM + CUP + maestros | Async |
| 4 | Gran valor | Top 10 prescriptores en mercado X | CUP | Conversacional |
| 5 | Gran valor | Productos con EVO TRM negativa (unidades, todos mis mercados) | IQVIA | Conversacional |
| 6 | Gran valor | Médicos con EVO TRM negativa (prescripciones) | CUP | Conversacional |
| 7 | Gran valor | Medicamentos que NO promociono y más prescribe Dr. X | CRM + CUP | Conversacional |
| 8 | Gran valor | Medicamentos que SÍ promociono y más prescribe Dr. X | CRM + CUP | Conversacional |
| 9 | Medio valor | Médicos que visito con menos/más frecuencia | CRM | Conversacional |
| 10 | Medio valor | Top 5 productos que prescribe Dr. X | CUP | Conversacional |
| 11 | Medio valor | Top 5 productos del laboratorio que prescribe Dr. X | CUP | Conversacional |
| 12 | Bajo valor | Objetivos de visita este mes | CRM | Instantáneo |
| 13 | Bajo valor | Médicos no visitados en ciclo actual | CRM | Instantáneo |
| 14 | Bajo valor | Última visita a Dr. X | CRM | Instantáneo |
| 15 | Bajo valor | Qué promocioné en última visita a Dr. X | CRM | Instantáneo |

### Reglas de routing por tipo de pregunta (del cliente)

- Preguntas de **ventas** → IQVIA
- Preguntas de **prescripciones/recetas** → CloseUp (CUP)
- Preguntas de **visitas/objetivos/productos foco o hiperfoco/agenda/cartera médica** → CRM interno

### Insight para la ontología futura

Las tablas "UltimaMilla" son un patrón interesante: son **vistas materializadas cross-source** que ya viven en el CRM interno. Contienen datos de CloseUp (prescripciones) pre-agregados y cruzados con el CRM. Esto significa que:

1. Para el carril **conversacional**, muchas preguntas de "valor medio" se pueden responder directamente desde estas tablas sin ir a CloseUp raw
2. Para el carril **instantáneo**, si las cargamos en DynamoDB durante el refill nocturno, las queries de share y EVO trimestral responden en <30ms
3. Para la **ontología**, representan relaciones pre-computadas entre entidades (Médico→prescribe→Marca con peso=share)

Cuando migremos a Neptune Analytics, estas relaciones se modelan como aristas con propiedades (weight=share, evo=crecimiento), lo que permite traversals tipo "médicos con arista prescribe→marca_foco con weight creciente y sin arista visita_reciente".

---

## Fuentes de esta investigación

- [IQVIA Available Data](https://www.iqvia.com/en/insights/the-iqvia-institute/available-iqvia-data) — descripción pública de datasets
- [IQVIA MIDAS](https://secure.constellation.iqvia.com/MIDAS-DEMO) — gold standard de ventas globales
- [Close-Up International profile](https://intuitionlabs.ai/articles/close-up-international-company-profile) — overview de servicios
- [Bridge to Data — Close-Up profiles](https://www.bridgetodata.org/index.php/node/107435) — descripción del panel de farmacias
- [Oracle Siebel Pharma Analytics](https://docs.oracle.com/cd/E12102_01/books/AnyInstAdm784/AnyInstAdmMetadata16.html) — dimensiones estándar de pharma analytics (ATC, producto, territorio, período)
- [IQVIA Canada Academics](https://www.iqvia.com/en-gb/locations/canada/solutions/academics-and-researchers) — dimensiones disponibles: product form, ATC, age groups, gender, region, payer
- Documento `road-to-prod.md` del proyecto — conocimiento de dominio específico del cliente
- Documentación del cliente: `DescripcionesTablas.docx` — estructura real de tablas por fuente
- Documentación del cliente: `Preguntas con Prioridades y Origen.docx` — preguntas priorizadas con fuentes de datos

Content was rephrased for compliance with licensing restrictions.
