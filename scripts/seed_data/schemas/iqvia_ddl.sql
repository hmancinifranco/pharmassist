-- ============================================================
-- SCHEMA: iqvia
-- Datos de ventas de mercado (IQVIA)
-- Star schema puro con fact table de ventas valorizadas
-- ============================================================

CREATE SCHEMA IF NOT EXISTS iqvia;

-- Dimensión: Período
CREATE TABLE iqvia.dim_periodo (
    idPeriodo       VARCHAR(10) PRIMARY KEY,
    anio            SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    trimestre       SMALLINT NOT NULL,
    semestre        SMALLINT NOT NULL,
    nombre_mes      VARCHAR(20)
);

-- Dimensión: Droga (principio activo)
CREATE TABLE iqvia.dim_droga (
    idDroga         VARCHAR(20) PRIMARY KEY,
    codDroga        VARCHAR(20),
    descripcion     VARCHAR(200) NOT NULL
);

-- Dimensión: Forma farmacéutica
CREATE TABLE iqvia.dim_forma_farmaceutica (
    idForma         VARCHAR(20) PRIMARY KEY,
    codFormaFarmaceutica VARCHAR(20),
    codNomenclatura VARCHAR(20),
    descripcion     VARCHAR(100) NOT NULL
);

-- Dimensión: Laboratorio
CREATE TABLE iqvia.dim_laboratorio (
    idLaboratorio   VARCHAR(20) PRIMARY KEY,
    codLaboratorio  VARCHAR(20),
    codNomenclatura VARCHAR(20),
    descripcion     VARCHAR(200) NOT NULL
);

-- Dimensión: Clase terapéutica
CREATE TABLE iqvia.dim_clase_terapeutica (
    idClase         VARCHAR(20) PRIMARY KEY,
    codClaseTerapeutica VARCHAR(20),
    adCodigoHeredado VARCHAR(20),
    descripcion     VARCHAR(200) NOT NULL
);

-- Dimensión: Combinación de droga
CREATE TABLE iqvia.dim_combinacion_droga (
    idCombinacion   VARCHAR(20) PRIMARY KEY,
    descripcion     VARCHAR(100) NOT NULL,
    descripcion_combinacion VARCHAR(200)
);

-- Dimensión: Presentación (producto comercial)
CREATE TABLE iqvia.dim_presentacion (
    idProducto      VARCHAR(20) PRIMARY KEY,
    codigo          VARCHAR(30),
    descripcion     VARCHAR(300) NOT NULL,
    adCodigoHeredado VARCHAR(20),
    idClaseTerapeutica VARCHAR(20) REFERENCES iqvia.dim_clase_terapeutica(idClase),
    idCombinacion   VARCHAR(20) REFERENCES iqvia.dim_combinacion_droga(idCombinacion),
    fecha_lanzamiento DATE,
    concentracion   VARCHAR(50)
);

-- Dimensión: Clase (agrupación de mercado)
CREATE TABLE iqvia.dim_clase (
    idClase         VARCHAR(20) PRIMARY KEY,
    codClase        VARCHAR(20),
    descripcion     VARCHAR(200) NOT NULL
);

-- Dimensión: Geografía
CREATE TABLE iqvia.dim_geografia (
    idGeografia     VARCHAR(20) PRIMARY KEY,
    nombre          VARCHAR(200) NOT NULL,
    provincia       VARCHAR(100),
    region          VARCHAR(100),
    canal           VARCHAR(50)
);

-- Relación: presentación ↔ droga
CREATE TABLE iqvia.rel_presentacion_droga (
    id              SERIAL PRIMARY KEY,
    idPresentacion  VARCHAR(20) NOT NULL REFERENCES iqvia.dim_presentacion(idProducto),
    idDroga         VARCHAR(20) NOT NULL REFERENCES iqvia.dim_droga(idDroga),
    UNIQUE(idPresentacion, idDroga)
);

-- Relación: presentación ↔ forma farmacéutica
CREATE TABLE iqvia.rel_presentacion_forma (
    id              SERIAL PRIMARY KEY,
    idPresentacion  VARCHAR(20) NOT NULL REFERENCES iqvia.dim_presentacion(idProducto),
    idFormaFarmaceutica VARCHAR(20) NOT NULL REFERENCES iqvia.dim_forma_farmaceutica(idForma),
    UNIQUE(idPresentacion, idFormaFarmaceutica)
);

-- Relación: producto ↔ laboratorio
CREATE TABLE iqvia.rel_producto_laboratorio (
    id              SERIAL PRIMARY KEY,
    idProducto      VARCHAR(20) NOT NULL REFERENCES iqvia.dim_presentacion(idProducto),
    idLaboratorio   VARCHAR(20) NOT NULL REFERENCES iqvia.dim_laboratorio(idLaboratorio),
    UNIQUE(idProducto, idLaboratorio)
);

-- FACT TABLE: Ventas de mercado valorizadas
CREATE TABLE iqvia.fact_mercado_valor (
    id              BIGSERIAL PRIMARY KEY,
    idClase         VARCHAR(20) REFERENCES iqvia.dim_clase(idClase),
    idProducto      VARCHAR(20) NOT NULL REFERENCES iqvia.dim_presentacion(idProducto),
    idPeriodo       VARCHAR(10) NOT NULL REFERENCES iqvia.dim_periodo(idPeriodo),
    idGeografia     VARCHAR(20) REFERENCES iqvia.dim_geografia(idGeografia),
    unidades        INTEGER NOT NULL,
    dosis           DECIMAL(15,2),
    valor           DECIMAL(15,2),
    valorUSD        DECIMAL(15,2)
);

-- Índices para queries frecuentes
CREATE INDEX idx_fact_periodo ON iqvia.fact_mercado_valor(idPeriodo);
CREATE INDEX idx_fact_producto ON iqvia.fact_mercado_valor(idProducto);
CREATE INDEX idx_fact_clase ON iqvia.fact_mercado_valor(idClase);
CREATE INDEX idx_fact_geo ON iqvia.fact_mercado_valor(idGeografia);
CREATE INDEX idx_presentacion_clase ON iqvia.dim_presentacion(idClaseTerapeutica);
