-- ============================================================
-- SCHEMA: crm_interno
-- Sistema CRM interno del laboratorio (normalizado, OLTP)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS crm_interno;

-- Zonas geográficas
CREATE TABLE crm_interno.zona (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) UNIQUE NOT NULL,
    nombre          VARCHAR(100) NOT NULL,
    region          VARCHAR(100),
    provincia       VARCHAR(100)
);

-- Especialidades médicas
CREATE TABLE crm_interno.especialidad (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) UNIQUE NOT NULL,
    nombre          VARCHAR(100) NOT NULL
);

-- Tags / Hobbies
CREATE TABLE crm_interno.tag (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    tipo            VARCHAR(50),
    activo          BOOLEAN DEFAULT true
);

-- APMs (visitadores médicos)
CREATE TABLE crm_interno.apm (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) UNIQUE NOT NULL,
    nombre          VARCHAR(100) NOT NULL,
    apellido        VARCHAR(100) NOT NULL,
    email           VARCHAR(200),
    telefono        VARCHAR(50),
    zona_id         INTEGER REFERENCES crm_interno.zona(id),
    gerente_id      INTEGER REFERENCES crm_interno.apm(id),
    activo          BOOLEAN DEFAULT true,
    fecha_ingreso   DATE
);

-- Médicos
CREATE TABLE crm_interno.doctor (
    id              SERIAL PRIMARY KEY,
    matricula_nacional VARCHAR(20) UNIQUE,
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
    intereses       TEXT,
    fecha_nacimiento DATE,
    cadencia        VARCHAR(20) NOT NULL DEFAULT 'Trimestral'
        CHECK (cadencia IN ('Mensual','Trimestral','Semestral','Anual','Digital')),
    activo          BOOLEAN DEFAULT true,
    latitud         DECIMAL(10,7),
    longitud        DECIMAL(10,7)
);

-- Tags de médicos
CREATE TABLE crm_interno.tag_doctor (
    tag_id          INTEGER NOT NULL REFERENCES crm_interno.tag(id),
    doctor_id       INTEGER NOT NULL REFERENCES crm_interno.doctor(id),
    PRIMARY KEY (tag_id, doctor_id)
);

-- Datos de visita (configuración)
CREATE TABLE crm_interno.datos_visita (
    id              SERIAL PRIMARY KEY,
    institucion_id  INTEGER,
    especialidad_id INTEGER REFERENCES crm_interno.especialidad(id),
    frecuencia      VARCHAR(20),
    turno_preferido VARCHAR(20)
);

-- Cartera médica: asignación APM ↔ Doctor
CREATE TABLE crm_interno.cartera_medica (
    id              SERIAL PRIMARY KEY,
    apm_id          INTEGER NOT NULL REFERENCES crm_interno.apm(id),
    doctor_id       INTEGER NOT NULL REFERENCES crm_interno.doctor(id),
    datos_visita_id INTEGER REFERENCES crm_interno.datos_visita(id),
    fecha_creacion  TIMESTAMP DEFAULT NOW(),
    fecha_modificacion TIMESTAMP,
    activa          BOOLEAN DEFAULT true,
    UNIQUE(apm_id, doctor_id)
);

-- Estado de cartera médica (historial de movimientos)
CREATE TABLE crm_interno.cartera_medica_estado (
    id              SERIAL PRIMARY KEY,
    apm_id          INTEGER NOT NULL REFERENCES crm_interno.apm(id),
    doctor_id       INTEGER NOT NULL REFERENCES crm_interno.doctor(id),
    estado          VARCHAR(50) NOT NULL,
    gerente_id      INTEGER REFERENCES crm_interno.apm(id),
    aprobador_id    INTEGER REFERENCES crm_interno.apm(id),
    fecha           TIMESTAMP NOT NULL DEFAULT NOW(),
    motivo          TEXT
);

-- Líneas de producto
CREATE TABLE crm_interno.linea (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) UNIQUE NOT NULL,
    nombre          VARCHAR(100) NOT NULL,
    abreviatura     VARCHAR(20),
    icono           VARCHAR(200)
);

-- Asignación de líneas a APMs
CREATE TABLE crm_interno.linea_apm (
    id              SERIAL PRIMARY KEY,
    apm_id          INTEGER NOT NULL REFERENCES crm_interno.apm(id),
    linea_id        INTEGER NOT NULL REFERENCES crm_interno.linea(id),
    UNIQUE(apm_id, linea_id)
);

-- Relación línea ↔ especialidad
CREATE TABLE crm_interno.linea_especializacion (
    id              SERIAL PRIMARY KEY,
    especialidad_id INTEGER NOT NULL REFERENCES crm_interno.especialidad(id),
    linea_id        INTEGER NOT NULL REFERENCES crm_interno.linea(id),
    UNIQUE(especialidad_id, linea_id)
);

-- Familias de producto (SKU del laboratorio)
CREATE TABLE crm_interno.familia_producto (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(30) UNIQUE NOT NULL,
    nombre          VARCHAR(200) NOT NULL,
    nombre_corto    VARCHAR(100),
    descripcion     TEXT,
    accion_terapeutica TEXT,
    principio_activo VARCHAR(200),
    linea_id        INTEGER REFERENCES crm_interno.linea(id),
    tipo            VARCHAR(10) CHECK (tipo IN ('OTC', 'RX')),
    presentacion    VARCHAR(100),
    url_imagen      VARCHAR(500),
    url_prospecto   VARCHAR(500),
    activo          BOOLEAN DEFAULT true
);

-- Catálogo de productos (puente a códigos externos)
CREATE TABLE crm_interno.catalogo_productos (
    id              SERIAL PRIMARY KEY,
    codigo_sap      VARCHAR(30),
    familia_producto_id INTEGER REFERENCES crm_interno.familia_producto(id),
    especialidad_id INTEGER REFERENCES crm_interno.especialidad(id),
    codigo_dispro   VARCHAR(30),
    codigo_ean      VARCHAR(20),
    activo          BOOLEAN DEFAULT true
);

-- Ciclos promocionales
CREATE TABLE crm_interno.ciclo (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL,
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE NOT NULL,
    activo          BOOLEAN DEFAULT false
);

-- Grillas de promoción
CREATE TABLE crm_interno.grilla (
    id              SERIAL PRIMARY KEY,
    abreviatura     VARCHAR(20),
    nombre          VARCHAR(100) NOT NULL,
    linea_id        INTEGER NOT NULL REFERENCES crm_interno.linea(id)
);

-- Categorías de promoción
CREATE TABLE crm_interno.categoria (
    id              SERIAL PRIMARY KEY,
    abreviatura     VARCHAR(20),
    nombre          VARCHAR(30) UNIQUE NOT NULL,
    orden           INTEGER
);

-- Detalle de promoción: producto × grilla × categoría × ciclo
CREATE TABLE crm_interno.detalle_promocion_producto (
    id                  SERIAL PRIMARY KEY,
    familia_producto_id INTEGER NOT NULL REFERENCES crm_interno.familia_producto(id),
    grilla_id           INTEGER NOT NULL REFERENCES crm_interno.grilla(id),
    categoria_id        INTEGER NOT NULL REFERENCES crm_interno.categoria(id),
    ciclo_id            INTEGER NOT NULL REFERENCES crm_interno.ciclo(id),
    estado_ciclo        VARCHAR(20),
    estado_grilla       VARCHAR(20)
);

-- Agenda de visitas (historial)
CREATE TABLE crm_interno.agenda (
    id              SERIAL PRIMARY KEY,
    apm_id          INTEGER NOT NULL REFERENCES crm_interno.apm(id),
    doctor_id       INTEGER NOT NULL REFERENCES crm_interno.doctor(id),
    fecha_inicio    TIMESTAMP NOT NULL,
    fecha_fin       TIMESTAMP,
    descripcion     TEXT,
    turno           VARCHAR(20),
    tipo_visita     VARCHAR(20) NOT NULL
        CHECK (tipo_visita IN ('Presencial','Virtual','Telefonica')),
    zona_id         INTEGER REFERENCES crm_interno.zona(id),
    inactivo        BOOLEAN DEFAULT false,
    visita_exitosa  BOOLEAN DEFAULT true
);

-- Productos presentados en cada visita
CREATE TABLE crm_interno.agenda_producto (
    id              SERIAL PRIMARY KEY,
    agenda_id       INTEGER NOT NULL REFERENCES crm_interno.agenda(id),
    familia_producto_id INTEGER NOT NULL REFERENCES crm_interno.familia_producto(id),
    orden           INTEGER
);

-- Muestras entregadas en visitas
CREATE TABLE crm_interno.agenda_muestra (
    id              SERIAL PRIMARY KEY,
    agenda_id       INTEGER NOT NULL REFERENCES crm_interno.agenda(id),
    familia_producto_id INTEGER NOT NULL REFERENCES crm_interno.familia_producto(id),
    cantidad        INTEGER NOT NULL DEFAULT 1,
    lote            VARCHAR(50),
    codigo_producto VARCHAR(50)
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

-- UltimaMilla: resumen de prescripciones por médico
CREATE TABLE crm_interno.ultima_milla_medico (
    id              SERIAL PRIMARY KEY,
    id_medico_cup   VARCHAR(20) NOT NULL,
    id_medico_crm   INTEGER REFERENCES crm_interno.doctor(id),
    evo_trimestral  DECIMAL(8,2),
    share_lab_ytd   DECIMAL(8,4),
    share_lab_mensual DECIMAL(8,4),
    share_lab_mat   DECIMAL(8,4),
    categoria_medico VARCHAR(10)
);

-- UltimaMilla: prescripciones por médico × marca × mercado
CREATE TABLE crm_interno.ultima_milla_marca (
    id              SERIAL PRIMARY KEY,
    id_medico_cup   VARCHAR(20) NOT NULL,
    id_marca        VARCHAR(20) NOT NULL,
    id_mercado      VARCHAR(20) NOT NULL,
    share_marca_mercado DECIMAL(8,4),
    share_marca_total   DECIMAL(8,4),
    categoria_medico VARCHAR(10)
);

-- UltimaMilla: relación mercado → marca → especialidad (productos objetivo)
CREATE TABLE crm_interno.ultima_milla_objetivo (
    id              SERIAL PRIMARY KEY,
    id_mercado      VARCHAR(20) NOT NULL,
    nombre_marca    VARCHAR(200) NOT NULL,
    id_especialidad INTEGER REFERENCES crm_interno.especialidad(id)
);

-- Índices para queries frecuentes
CREATE INDEX idx_cartera_apm ON crm_interno.cartera_medica(apm_id);
CREATE INDEX idx_cartera_doctor ON crm_interno.cartera_medica(doctor_id);
CREATE INDEX idx_agenda_apm_fecha ON crm_interno.agenda(apm_id, fecha_inicio);
CREATE INDEX idx_agenda_doctor ON crm_interno.agenda(doctor_id);
CREATE INDEX idx_agenda_producto_agenda ON crm_interno.agenda_producto(agenda_id);
CREATE INDEX idx_detalle_promo_grilla ON crm_interno.detalle_promocion_producto(grilla_id);
CREATE INDEX idx_detalle_promo_ciclo ON crm_interno.detalle_promocion_producto(ciclo_id);
CREATE INDEX idx_ultima_milla_medico_cup ON crm_interno.ultima_milla_medico(id_medico_cup);
CREATE INDEX idx_ultima_milla_marca_medico ON crm_interno.ultima_milla_marca(id_medico_cup);
