-- =============================================================================
-- PharmAssist POC — DDL Completo
-- Aurora PostgreSQL Serverless v2 — Base de datos: pharmassist_poc
-- =============================================================================
-- Crea todas las tablas del modelo de datos farmacéutico (21+ tablas),
-- índices de performance (10 índices), y usuario read-only para el CodeAgent.
--
-- Orden: tablas padre (sin dependencias) → tablas con FK de primer nivel
--        → tablas operativas → tablas analíticas UltimaMilla → cross-ref
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLAS PADRE (catálogos sin dependencias de FK)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS especialidad (
    id VARCHAR(10) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS loyalty_doctor (
    id VARCHAR(10) PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS institucion (
    id VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(200) NOT NULL
);

CREATE TABLE IF NOT EXISTS linea (
    id VARCHAR(10) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    abreviatura VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS ciclo (
    id VARCHAR(10) PRIMARY KEY,
    inicio DATE NOT NULL,
    fin DATE NOT NULL,
    nombre VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS categoria_promocion (
    id VARCHAR(5) PRIMARY KEY,        -- '1' = HP (Hiperfoco), '2' = FC (Foco)
    abreviatura VARCHAR(5) NOT NULL,  -- 'HP', 'FC'
    nombre_categoria VARCHAR(50)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLAS CON DEPENDENCIA DE PRIMER NIVEL
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS apm (
    id VARCHAR(20) PRIMARY KEY,
    "primerNombre" VARCHAR(100),
    "primerApellido" VARCHAR(100),
    email VARCHAR(200),
    id_linea VARCHAR(10) REFERENCES linea(id),
    gerente_regional_id VARCHAR(20),
    "codigoPromotor" VARCHAR(20),
    inactivo BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS doctor (
    id VARCHAR(20) PRIMARY KEY,
    "primerNombre" VARCHAR(100),
    "primerApellido" VARCHAR(100),
    "matriculaNacional" VARCHAR(20),
    especialidad_id VARCHAR(10) REFERENCES especialidad(id),
    loyalty_id VARCHAR(10) REFERENCES loyalty_doctor(id),
    categoria_id VARCHAR(10),
    inactivo BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS familia_producto (
    id VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    principio_activo VARCHAR(200),
    accion_terapeutica VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS producto (
    id VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    id_linea VARCHAR(10) REFERENCES linea(id)
);

CREATE TABLE IF NOT EXISTS grilla (
    id VARCHAR(20) PRIMARY KEY,
    nombre_grilla VARCHAR(100),
    id_linea VARCHAR(10) REFERENCES linea(id)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLAS DE RELACIÓN Y OPERATIVAS
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS linea_apm (
    id VARCHAR(20) PRIMARY KEY,
    id_apm VARCHAR(20) REFERENCES apm(id),
    id_linea VARCHAR(10) REFERENCES linea(id)
);

CREATE TABLE IF NOT EXISTS datos_visita (
    id VARCHAR(20) PRIMARY KEY,
    frecuencia VARCHAR(20),          -- Mensual, Trimestral, Semestral, Anual
    institucion_id VARCHAR(20) REFERENCES institucion(id)
);

CREATE TABLE IF NOT EXISTS cartera_medica (
    id VARCHAR(20) PRIMARY KEY,
    apm_id VARCHAR(20) REFERENCES apm(id),
    doctor_id VARCHAR(20) REFERENCES doctor(id),
    datos_visita_id VARCHAR(20) REFERENCES datos_visita(id),
    inactivo BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS agenda (
    id VARCHAR(30) PRIMARY KEY,
    inicio TIMESTAMP NOT NULL,
    fin TIMESTAMP,
    apm_id VARCHAR(20) REFERENCES apm(id),
    doctor_id VARCHAR(20) REFERENCES doctor(id),
    visita_exitosa BOOLEAN DEFAULT true,
    observaciones TEXT,
    visita_tipo VARCHAR(20),         -- Presencial / Virtual / Telefónica
    inactivo BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS detalle_promocion_producto (
    id VARCHAR(30) PRIMARY KEY,
    id_familia_producto VARCHAR(20) REFERENCES familia_producto(id),
    id_grilla VARCHAR(20) REFERENCES grilla(id),
    id_categoria_promocion VARCHAR(5) REFERENCES categoria_promocion(id),
    id_ciclo VARCHAR(10) REFERENCES ciclo(id)
);

CREATE TABLE IF NOT EXISTS agenda_producto (
    id VARCHAR(30) PRIMARY KEY,
    id_agenda VARCHAR(30) REFERENCES agenda(id),
    id_producto VARCHAR(20) REFERENCES familia_producto(id)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLAS ANALÍTICAS "UltimaMilla" (nombres mixtos con comillas — datos CUP/IQVIA)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS "UltimaMillaMedico" (
    "idMedicoCUP" VARCHAR(20) NOT NULL,
    "idMedicoAPX" VARCHAR(20) REFERENCES doctor(id),
    "IETrim" DECIMAL(10,4),
    "ShareTrim" DECIMAL(10,4),
    "ShareTrim_1" DECIMAL(10,4),
    "ShareMes" DECIMAL(10,4),
    PRIMARY KEY ("idMedicoCUP")
);

CREATE TABLE IF NOT EXISTS "UltimaMillaMarca" (
    "idMedicoCUP" VARCHAR(20) NOT NULL,
    "idMarca" VARCHAR(20) NOT NULL,
    "idMercado" VARCHAR(20),
    "idLaboratorio" VARCHAR(10),         -- 'ELE' para Elea (laboratorio propio)
    "marcaNombre" VARCHAR(100),
    "ShareMarcaMercado" DECIMAL(10,4),
    "ShareMarcaMes" DECIMAL(10,4),
    "IEMarcaTrim" DECIMAL(10,4),
    "ShareMarcaTrim" DECIMAL(10,4),
    "ShareMarcaTrim_1" DECIMAL(10,4),
    PRIMARY KEY ("idMedicoCUP", "idMarca")
);

CREATE TABLE IF NOT EXISTS "UltimaMillaObjetivoMarcaMercado" (
    "idEspecialidad" VARCHAR(10) REFERENCES especialidad(id),
    "idMarca" VARCHAR(20),
    "idMercado" VARCHAR(20),
    "marcaNombre" VARCHAR(100),
    PRIMARY KEY ("idEspecialidad", "idMarca", "idMercado")
);


-- ─────────────────────────────────────────────────────────────────────────────
-- TABLA CROSS-REFERENCE APX → CUP
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS familia_APX_a_Marca_CUP (
    id_familia_producto_apx VARCHAR(20) REFERENCES familia_producto(id),
    "codMarcaCUP" VARCHAR(20),
    PRIMARY KEY (id_familia_producto_apx, "codMarcaCUP")
);


-- =============================================================================
-- ÍNDICES DE PERFORMANCE (10 índices)
-- Se crean después de la carga masiva de datos para mayor eficiencia.
-- =============================================================================

-- Cartera médica: búsqueda por APM (solo registros activos)
CREATE INDEX IF NOT EXISTS idx_cartera_medica_apm
    ON cartera_medica(apm_id) WHERE inactivo = false;

-- Cartera médica: búsqueda por doctor (solo registros activos)
CREATE INDEX IF NOT EXISTS idx_cartera_medica_doctor
    ON cartera_medica(doctor_id) WHERE inactivo = false;

-- Agenda: búsqueda por APM + fecha descendente (solo activas)
CREATE INDEX IF NOT EXISTS idx_agenda_apm_inicio
    ON agenda(apm_id, inicio DESC) WHERE inactivo = false;

-- Agenda: búsqueda por doctor + fecha descendente
CREATE INDEX IF NOT EXISTS idx_agenda_doctor
    ON agenda(doctor_id, inicio DESC);

-- UltimaMillaMarca: búsqueda por médico + marca
CREATE INDEX IF NOT EXISTS idx_ultima_milla_marca_medico
    ON "UltimaMillaMarca"("idMedicoCUP", "idMarca");

-- UltimaMillaMarca: búsqueda por laboratorio + médico (filtro ELE)
CREATE INDEX IF NOT EXISTS idx_ultima_milla_marca_lab
    ON "UltimaMillaMarca"("idLaboratorio", "idMedicoCUP");

-- Detalle promoción: búsqueda por ciclo + categoría
CREATE INDEX IF NOT EXISTS idx_detalle_promo_ciclo_cat
    ON detalle_promocion_producto(id_ciclo, id_categoria_promocion);

-- Linea APM: búsqueda por APM
CREATE INDEX IF NOT EXISTS idx_linea_apm_apm
    ON linea_apm(id_apm);

-- Agenda producto: búsqueda por agenda
CREATE INDEX IF NOT EXISTS idx_agenda_producto_agenda
    ON agenda_producto(id_agenda);

-- UltimaMillaMedico: búsqueda por idMedicoAPX (cruce con doctor)
CREATE INDEX IF NOT EXISTS idx_ultima_milla_medico_apx
    ON "UltimaMillaMedico"("idMedicoAPX");


-- =============================================================================
-- USUARIO READ-ONLY PARA EL CODEAGENT
-- El CodeAgent se conecta con permisos mínimos (SELECT only).
-- La contraseña es un placeholder — se reemplaza en runtime via Secrets Manager.
-- =============================================================================

CREATE USER codeagent_readonly WITH PASSWORD 'readonly_password_placeholder';
GRANT CONNECT ON DATABASE pharmassist_poc TO codeagent_readonly;
GRANT USAGE ON SCHEMA public TO codeagent_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO codeagent_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO codeagent_readonly;
