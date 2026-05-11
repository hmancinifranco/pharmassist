-- ============================================================
-- SCHEMA: closeup
-- Datos de prescripciones (Close-Up International)
-- Star schema con fact table central
-- ============================================================

CREATE SCHEMA IF NOT EXISTS closeup;

-- Dimensión: Médicos
CREATE TABLE closeup.medico (
    CDGMED          VARCHAR(20) PRIMARY KEY,
    nombre          VARCHAR(200),
    apellido        VARCHAR(200),
    especialidad    VARCHAR(100),
    localidad       VARCHAR(100),
    provincia       VARCHAR(100),
    barrio          VARCHAR(100),
    cdgreg_pmix     VARCHAR(20),
    activo          BOOLEAN DEFAULT true
);

-- Dimensión: Marcas/Productos
CREATE TABLE closeup.marca (
    codigo_marca    VARCHAR(20) PRIMARY KEY,
    nombre_marca    VARCHAR(200) NOT NULL,
    laboratorio     VARCHAR(200),
    principio_activo VARCHAR(200),
    forma_farmaceutica VARCHAR(100),
    concentracion   VARCHAR(50)
);

-- Dimensión: Mercados
CREATE TABLE closeup.mercado (
    CDG_MERCADO     VARCHAR(20) PRIMARY KEY,
    nombre_mercado  VARCHAR(200) NOT NULL,
    abreviatura     VARCHAR(50),
    clase_terapeutica VARCHAR(200),
    path_tipo       VARCHAR(200)
);

-- Relación: productos en mercados
CREATE TABLE closeup.mercado_producto (
    id              SERIAL PRIMARY KEY,
    CDG_MERCADO     VARCHAR(20) NOT NULL REFERENCES closeup.mercado(CDG_MERCADO),
    CDG_PROD        VARCHAR(20) NOT NULL,
    codigo_marca    VARCHAR(20) REFERENCES closeup.marca(codigo_marca),
    codigo_laboratorio VARCHAR(20),
    codigo_pais     VARCHAR(10),
    anio_edicion    SMALLINT,
    mes_edicion     SMALLINT,
    UNIQUE(CDG_MERCADO, CDG_PROD)
);

-- Mercados con módulos y líneas
CREATE TABLE closeup.mercado_modulo_linea (
    id              SERIAL PRIMARY KEY,
    CDG_MERCADO     VARCHAR(20) NOT NULL REFERENCES closeup.mercado(CDG_MERCADO),
    edicion         VARCHAR(50),
    descripcion     VARCHAR(200),
    codigo_usuario  VARCHAR(20),
    codigo_pais     VARCHAR(10)
);

-- Dimensión: Representantes
CREATE TABLE closeup.representante (
    id_rep          VARCHAR(20) PRIMARY KEY,
    nombre          VARCHAR(200),
    laboratorio     VARCHAR(200)
);

-- FACT TABLE: Prescripciones
CREATE TABLE closeup.prescripcion (
    id              BIGSERIAL PRIMARY KEY,
    CDGMED          VARCHAR(20) NOT NULL,
    CDGPRO          VARCHAR(20) NOT NULL,
    CDGMAR          VARCHAR(20),
    CDGMED_REG      VARCHAR(20),
    CDGESP1         VARCHAR(20),
    CDGREG_PMIX     VARCHAR(20),
    CDGLAB          VARCHAR(20),
    CDGCLA4         VARCHAR(20),
    cantidad        INTEGER NOT NULL,
    px_farma        INTEGER,
    px_delivery     INTEGER,
    fecha           DATE NOT NULL,
    tipo_dom        CHAR(1) DEFAULT 'C',
    CONSTRAINT fk_medico FOREIGN KEY (CDGMED) REFERENCES closeup.medico(CDGMED)
);

-- Médico-Representante
CREATE TABLE closeup.medico_representante (
    id              SERIAL PRIMARY KEY,
    CDGMED          VARCHAR(20) NOT NULL REFERENCES closeup.medico(CDGMED),
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

-- Médicos no visitados por representante
CREATE TABLE closeup.medico_rep_novisitado (
    id              SERIAL PRIMARY KEY,
    CDGMED          VARCHAR(20) NOT NULL REFERENCES closeup.medico(CDGMED),
    CDGMED_REG      VARCHAR(20),
    CDGREP          VARCHAR(20) NOT NULL,
    CDGR            VARCHAR(20),
    CDGD            VARCHAR(20),
    nombre_rep      VARCHAR(200)
);

-- Médicos visitados
CREATE TABLE closeup.medico_visitado (
    id              SERIAL PRIMARY KEY,
    CDGMED          VARCHAR(20) NOT NULL REFERENCES closeup.medico(CDGMED),
    CDGMED_REG      VARCHAR(20),
    codigo_cliente  VARCHAR(20)
);

-- Índices para queries frecuentes
CREATE INDEX idx_prescripcion_medico ON closeup.prescripcion(CDGMED);
CREATE INDEX idx_prescripcion_producto ON closeup.prescripcion(CDGPRO);
CREATE INDEX idx_prescripcion_fecha ON closeup.prescripcion(fecha);
CREATE INDEX idx_prescripcion_region ON closeup.prescripcion(CDGREG_PMIX);
CREATE INDEX idx_prescripcion_lab ON closeup.prescripcion(CDGLAB);
CREATE INDEX idx_mercado_producto_mercado ON closeup.mercado_producto(CDG_MERCADO);
CREATE INDEX idx_mercado_producto_prod ON closeup.mercado_producto(CDG_PROD);
