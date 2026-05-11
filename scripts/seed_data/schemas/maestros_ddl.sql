-- ============================================================
-- SCHEMA: maestros
-- Tablas de integración entre las 3 fuentes
-- Permiten joins cross-source en Athena
-- ============================================================

CREATE SCHEMA IF NOT EXISTS maestros;

-- Maestro de médicos: CRM interno ↔ CloseUp
-- Si tiene cod_interno → lo atiende el laboratorio
-- Si tiene cod_closeup pero no cod_interno → no lo visitamos
CREATE TABLE maestros.maestro_medicos (
    id              SERIAL PRIMARY KEY,
    cod_interno     INTEGER,
    cod_closeup     VARCHAR(20),
    nombre_verificado VARCHAR(200),
    fecha_mapeo     DATE,
    confianza       VARCHAR(20) DEFAULT 'alta'
        CHECK (confianza IN ('alta','media','baja'))
);

CREATE UNIQUE INDEX idx_maestro_med_interno ON maestros.maestro_medicos(cod_interno) WHERE cod_interno IS NOT NULL;
CREATE UNIQUE INDEX idx_maestro_med_closeup ON maestros.maestro_medicos(cod_closeup) WHERE cod_closeup IS NOT NULL;

-- Maestro integrador de productos: CRM ↔ CloseUp ↔ IQVIA
-- codProductoCUP → CDG_PROD de mercados_productos (CloseUp)
-- idProducto → idProducto de dim_presentacion (IQVIA)
-- CodProductoBarrasEAN11 → adCodigoHeredado de dim_presentacion (IQVIA)
-- Si no tiene código CUP → no tuvo prescripciones
-- Si no tiene código IQVIA → no tuvo ventas
CREATE TABLE maestros.maestro_integrador_producto (
    id              SERIAL PRIMARY KEY,
    cod_interno     VARCHAR(30),
    cod_closeup     VARCHAR(20),
    cod_iqvia       VARCHAR(20),
    codigo_barras_ean11 VARCHAR(20),
    nombre_unificado VARCHAR(300),
    principio_activo VARCHAR(200),
    fecha_mapeo     DATE,
    CONSTRAINT al_menos_un_codigo CHECK (
        cod_interno IS NOT NULL OR cod_closeup IS NOT NULL OR cod_iqvia IS NOT NULL
    )
);

CREATE INDEX idx_maestro_prod_interno ON maestros.maestro_integrador_producto(cod_interno);
CREATE INDEX idx_maestro_prod_closeup ON maestros.maestro_integrador_producto(cod_closeup);
CREATE INDEX idx_maestro_prod_iqvia ON maestros.maestro_integrador_producto(cod_iqvia);

-- Familia interna a marca CloseUp (relación N:M)
-- Un id_familia_producto puede tener 0 a N codMarcaCUP (incluyendo repetidos)
-- Usar DISTINCT antes de usar el listado de códigos
CREATE TABLE maestros.familia_interno_a_marca_cup (
    id              SERIAL PRIMARY KEY,
    cod_interno     VARCHAR(30) NOT NULL,
    codigo_marca    VARCHAR(20) NOT NULL,
    relacion        VARCHAR(50) DEFAULT 'exacta'
        CHECK (relacion IN ('exacta','parcial','generico'))
);

CREATE INDEX idx_familia_marca_interno ON maestros.familia_interno_a_marca_cup(cod_interno);
CREATE INDEX idx_familia_marca_cup ON maestros.familia_interno_a_marca_cup(codigo_marca);
