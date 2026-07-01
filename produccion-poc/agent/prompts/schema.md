# Schema de Base de Datos — PharmAssist POC

Base de datos: `pharmassist_poc` (Aurora PostgreSQL Serverless v2)

## Tablas Catálogo (sin dependencias)

### especialidad
Catálogo de especialidades médicas.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(10) | PK |
| nombre | VARCHAR(100) | NOT NULL |

### loyalty_doctor
Niveles de lealtad de médicos.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(10) | PK |
| nombre | VARCHAR(50) | NOT NULL |

### institucion
Instituciones/hospitales donde se visitan médicos.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(20) | PK |
| nombre | VARCHAR(200) | NOT NULL |

### linea
Líneas comerciales del laboratorio.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(10) | PK |
| nombre | VARCHAR(100) | NOT NULL |
| abreviatura | VARCHAR(10) | |

### ciclo
Períodos promocionales con fechas de vigencia.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(10) | PK |
| inicio | DATE | NOT NULL |
| fin | DATE | NOT NULL |
| nombre | VARCHAR(50) | |

### categoria_promocion
Categorías de promoción de productos: '1'=HP (Hiperfoco), '2'=FC (Foco).
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(5) | PK. '1'=HP, '2'=FC |
| abreviatura | VARCHAR(5) | NOT NULL. 'HP' o 'FC' |
| nombre_categoria | VARCHAR(50) | |


## Tablas de Entidades Principales

### apm
Agentes de Propaganda Médica (visitadores).
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(20) | PK |
| "primerNombre" | VARCHAR(100) | |
| "primerApellido" | VARCHAR(100) | |
| email | VARCHAR(200) | |
| id_linea | VARCHAR(10) | FK → linea(id) |
| gerente_regional_id | VARCHAR(20) | |
| "codigoPromotor" | VARCHAR(20) | |
| inactivo | BOOLEAN | DEFAULT false |

### doctor
Médicos visitados por los APMs.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(20) | PK |
| "primerNombre" | VARCHAR(100) | |
| "primerApellido" | VARCHAR(100) | |
| "matriculaNacional" | VARCHAR(20) | |
| especialidad_id | VARCHAR(10) | FK → especialidad(id) |
| loyalty_id | VARCHAR(10) | FK → loyalty_doctor(id) |
| categoria_id | VARCHAR(10) | |
| inactivo | BOOLEAN | DEFAULT false |

### familia_producto
Familias de productos farmacéuticos (nivel de agregación para promoción).
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(20) | PK |
| nombre | VARCHAR(100) | NOT NULL |
| principio_activo | VARCHAR(200) | |
| accion_terapeutica | VARCHAR(200) | |

### producto
Productos individuales (presentaciones) del laboratorio.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(20) | PK |
| nombre | VARCHAR(100) | NOT NULL |
| id_linea | VARCHAR(10) | FK → linea(id) |

### grilla
Grillas de promoción por línea comercial.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(20) | PK |
| nombre_grilla | VARCHAR(100) | |
| id_linea | VARCHAR(10) | FK → linea(id) |


## Tablas de Relación y Operativas

### linea_apm
Relación entre APMs y líneas comerciales asignadas.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(20) | PK |
| id_apm | VARCHAR(20) | FK → apm(id) |
| id_linea | VARCHAR(10) | FK → linea(id) |

### datos_visita
Datos de frecuencia de visita por institución.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(20) | PK |
| frecuencia | VARCHAR(20) | Mensual/Trimestral/Semestral/Anual |
| institucion_id | VARCHAR(20) | FK → institucion(id) |

### cartera_medica
Relación entre APM y sus médicos asignados (portfolio activo).
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(20) | PK |
| apm_id | VARCHAR(20) | FK → apm(id) |
| doctor_id | VARCHAR(20) | FK → doctor(id) |
| datos_visita_id | VARCHAR(20) | FK → datos_visita(id) |
| inactivo | BOOLEAN | DEFAULT false. **Filtrar siempre WHERE inactivo = false** |

### agenda
Visitas realizadas o planificadas por el APM.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(30) | PK |
| inicio | TIMESTAMP | NOT NULL |
| fin | TIMESTAMP | |
| apm_id | VARCHAR(20) | FK → apm(id) |
| doctor_id | VARCHAR(20) | FK → doctor(id) |
| visita_exitosa | BOOLEAN | DEFAULT true |
| observaciones | TEXT | |
| visita_tipo | VARCHAR(20) | Presencial/Virtual/Telefónica |
| inactivo | BOOLEAN | DEFAULT false. **Filtrar siempre WHERE inactivo = false** |

### detalle_promocion_producto
Productos asignados a una grilla/ciclo con categoría de promoción.
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(30) | PK |
| id_familia_producto | VARCHAR(20) | FK → familia_producto(id) |
| id_grilla | VARCHAR(20) | FK → grilla(id) |
| id_categoria_promocion | VARCHAR(5) | FK → categoria_promocion(id). '1'=HP, '2'=FC |
| id_ciclo | VARCHAR(10) | FK → ciclo(id) |

### agenda_producto
Productos presentados en cada visita (relación agenda ↔ familia_producto).
| Columna | Tipo | Notas |
|---------|------|-------|
| id | VARCHAR(30) | PK |
| id_agenda | VARCHAR(30) | FK → agenda(id) |
| id_producto | VARCHAR(20) | FK → familia_producto(id) |


## Tablas Analíticas UltimaMilla (datos de prescripción CUP/IQVIA)

**IMPORTANTE**: Estas tablas usan nombres con mayúsculas mixtas — usar siempre comillas dobles en SQL.

### "UltimaMillaMedico"
Resumen de prescripción por médico (1 fila por doctor).
| Columna | Tipo | Notas |
|---------|------|-------|
| "idMedicoCUP" | VARCHAR(20) | PK. ID del médico en sistema CUP |
| "idMedicoAPX" | VARCHAR(20) | FK → doctor(id). Cruce con tabla doctor |
| "IETrim" | DECIMAL(10,4) | Índice de esfuerzo trimestral |
| "ShareTrim" | DECIMAL(10,4) | Share trimestral actual |
| "ShareTrim_1" | DECIMAL(10,4) | Share trimestre anterior |
| "ShareMes" | DECIMAL(10,4) | Share mensual |

### "UltimaMillaMarca"
Prescripciones por médico y marca (~1.5M filas). Tabla principal para análisis de share.
| Columna | Tipo | Notas |
|---------|------|-------|
| "idMedicoCUP" | VARCHAR(20) | PK (compuesto) |
| "idMarca" | VARCHAR(20) | PK (compuesto) |
| "idMercado" | VARCHAR(20) | Mercado/segmento terapéutico |
| "idLaboratorio" | VARCHAR(10) | 'ELE' = productos propios del laboratorio |
| "marcaNombre" | VARCHAR(100) | Nombre comercial de la marca |
| "ShareMarcaMercado" | DECIMAL(10,4) | Share de la marca en el mercado |
| "ShareMarcaMes" | DECIMAL(10,4) | Share mensual |
| "IEMarcaTrim" | DECIMAL(10,4) | Índice de esfuerzo de la marca trimestral |
| "ShareMarcaTrim" | DECIMAL(10,4) | Share trimestral actual |
| "ShareMarcaTrim_1" | DECIMAL(10,4) | Share trimestre anterior |

### "UltimaMillaObjetivoMarcaMercado"
Objetivos de marca por especialidad y mercado.
| Columna | Tipo | Notas |
|---------|------|-------|
| "idEspecialidad" | VARCHAR(10) | PK (compuesto). FK → especialidad(id) |
| "idMarca" | VARCHAR(20) | PK (compuesto) |
| "idMercado" | VARCHAR(20) | PK (compuesto) |
| "marcaNombre" | VARCHAR(100) | |


## Tabla Cross-Reference APX → CUP

### familia_APX_a_Marca_CUP
Mapeo entre familias de producto internas (APX) y marcas del sistema CUP.
| Columna | Tipo | Notas |
|---------|------|-------|
| id_familia_producto_apx | VARCHAR(20) | PK (compuesto). FK → familia_producto(id) |
| "codMarcaCUP" | VARCHAR(20) | PK (compuesto). Código de marca en sistema CUP |

**Path de cruce APX → CUP**: familia_producto.id → familia_APX_a_Marca_CUP.id_familia_producto_apx → "codMarcaCUP" → "UltimaMillaMarca"."idMarca"

## Relaciones Clave (para JOINs frecuentes)

1. **APM → Cartera → Doctor** (portfolio del APM):
   `apm.id → cartera_medica.apm_id → cartera_medica.doctor_id → doctor.id`

2. **APM → Agenda → Productos presentados**:
   `apm.id → agenda.apm_id → agenda.id → agenda_producto.id_agenda → agenda_producto.id_producto → familia_producto.id`

3. **Doctor → Prescripciones por marca**:
   `doctor.id → "UltimaMillaMedico"."idMedicoAPX" → "UltimaMillaMedico"."idMedicoCUP" → "UltimaMillaMarca"."idMedicoCUP"`

4. **Productos foco del ciclo actual**:
   `ciclo.id → detalle_promocion_producto.id_ciclo (WHERE id_categoria_promocion IN ('1','2')) → detalle_promocion_producto.id_familia_producto → familia_producto.id`

5. **Familia producto → Marca CUP (para cruzar prescripciones)**:
   `familia_producto.id → familia_APX_a_Marca_CUP.id_familia_producto_apx → "codMarcaCUP" → "UltimaMillaMarca"."idMarca"`

## Índices de Performance

- `idx_cartera_medica_apm` — cartera_medica(apm_id) WHERE inactivo = false
- `idx_cartera_medica_doctor` — cartera_medica(doctor_id) WHERE inactivo = false
- `idx_agenda_apm_inicio` — agenda(apm_id, inicio DESC) WHERE inactivo = false
- `idx_agenda_doctor` — agenda(doctor_id, inicio DESC)
- `idx_ultima_milla_marca_medico` — "UltimaMillaMarca"("idMedicoCUP", "idMarca")
- `idx_ultima_milla_marca_lab` — "UltimaMillaMarca"("idLaboratorio", "idMedicoCUP")
- `idx_detalle_promo_ciclo_cat` — detalle_promocion_producto(id_ciclo, id_categoria_promocion)
- `idx_linea_apm_apm` — linea_apm(id_apm)
- `idx_agenda_producto_agenda` — agenda_producto(id_agenda)
- `idx_ultima_milla_medico_apx` — "UltimaMillaMedico"("idMedicoAPX")
