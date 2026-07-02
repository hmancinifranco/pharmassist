-- =============================================================================
-- Queries Prototipo — Preguntas Priorizadas del Cliente
-- =============================================================================
--
-- Propósito: Validar que las tablas maestras (maestro_medicos,
-- maestro_integrador_producto, familia_interno_a_marca_cup) habilitan
-- las preguntas de negocio priorizadas que requieren cross-source joins.
--
-- Prerequisitos:
--   - Pipeline de ingesta ejecutado al menos 1 vez
--   - Datos presentes en pharmassist_crm, pharmassist_cup y pharmassist_maestros
--
-- Databases (Glue Catalog):
--   - pharmassist_crm      → CRM tables (doctor, familia_producto, agenda)
--   - pharmassist_cup      → CloseUp tables (medico, marca, prescripcion)
--   - pharmassist_maestros → Master tables (maestro_medicos,
--                            maestro_integrador_producto,
--                            familia_interno_a_marca_cup)
--
-- Sintaxis: Athena SQL (Trino/Presto)
-- Validates: Requirements 9.1 a 9.8
-- =============================================================================


-- =============================================================================
-- PREGUNTA 1: "Recomendar médicos según prescripciones y productos foco"
-- =============================================================================
-- Maestros utilizados: maestro_medicos, familia_interno_a_marca_cup
-- Join path:
--   prescripcion.cdgmedico → medico.cdgmedico (CUP)
--   prescripcion.cdgmarca  → familia_interno_a_marca_cup.cdgmarca_cup
--   prescripcion.cdgmedico → maestro_medicos.cdgmedico_cup
-- Resultado: Médicos con alta prescripción en productos foco que NO están
--            en cartera CRM (candidatos a incorporar).
-- =============================================================================

SELECT
    p.cdgmedico,
    cup_med.nombre AS nombre_medico,
    cup_med.especialidad,
    SUM(p.unidades) AS total_prescripciones_foco
FROM pharmassist_cup.prescripcion p
JOIN pharmassist_cup.medico cup_med ON p.cdgmedico = cup_med.cdgmedico
JOIN pharmassist_maestros.familia_interno_a_marca_cup fam ON p.cdgmarca = fam.cdgmarca_cup
JOIN pharmassist_maestros.maestro_medicos mm ON p.cdgmedico = mm.cdgmedico_cup
WHERE p.anio >= YEAR(CURRENT_DATE) - 1
  AND mm.doctor_id_crm IS NULL  -- no está en cartera CRM
GROUP BY p.cdgmedico, cup_med.nombre, cup_med.especialidad
HAVING SUM(p.unidades) > 0
ORDER BY total_prescripciones_foco DESC
LIMIT 20
;


-- =============================================================================
-- PREGUNTA 2: "Médicos creciendo en foco que visito poco"
-- =============================================================================
-- Maestros utilizados: maestro_medicos, familia_interno_a_marca_cup
-- Join path:
--   doctor.id             → maestro_medicos.doctor_id_crm (CRM → maestro)
--   maestro_medicos.cdgmedico_cup → prescripcion.cdgmedico (maestro → CUP)
--   prescripcion.cdgmarca → familia_interno_a_marca_cup.cdgmarca_cup
--   doctor.id             → agenda.doctor_id (CRM visitas)
-- Resultado: Médicos en cartera con prescripciones crecientes en productos
--            foco pero baja frecuencia de visita (>90 días sin visitar).
-- =============================================================================

SELECT
    d.id AS doctor_id,
    d.nombre || ' ' || d.apellido AS nombre_medico,
    d.cadencia,
    SUM(p.unidades) AS prescripciones_foco_12m,
    MAX(a.fecha_inicio) AS ultima_visita
FROM pharmassist_crm.doctor d
JOIN pharmassist_maestros.maestro_medicos mm ON d.id = mm.doctor_id_crm
JOIN pharmassist_cup.prescripcion p ON mm.cdgmedico_cup = p.cdgmedico
JOIN pharmassist_maestros.familia_interno_a_marca_cup fam ON p.cdgmarca = fam.cdgmarca_cup
LEFT JOIN pharmassist_crm.agenda a ON d.id = a.doctor_id AND a.estado = 'Realizada'
WHERE p.anio >= YEAR(CURRENT_DATE) - 1
  AND d.activo = true
GROUP BY d.id, d.nombre, d.apellido, d.cadencia
HAVING MAX(a.fecha_inicio) < CURRENT_DATE - INTERVAL '90' DAY
   OR MAX(a.fecha_inicio) IS NULL
ORDER BY prescripciones_foco_12m DESC
LIMIT 20
;


-- =============================================================================
-- PREGUNTA 3: "Médicos a visitar para crecer con producto X"
-- =============================================================================
-- Maestros utilizados: maestro_medicos, maestro_integrador_producto
-- Join path:
--   doctor.id             → maestro_medicos.doctor_id_crm (CRM → maestro)
--   maestro_medicos.cdgmedico_cup → prescripcion.cdgmedico (maestro → CUP)
--   prescripcion.cdgmarca → maestro_integrador_producto.cdgmarca_cup
-- Resultado: Médicos que prescriben productos de competencia (no nuestros)
--            ordenados por volumen — candidatos a visitar para ganar share.
-- =============================================================================

SELECT
    d.id AS doctor_id,
    d.nombre || ' ' || d.apellido AS nombre_medico,
    d.especialidad_id,
    SUM(p.unidades) AS prescripciones_competencia
FROM pharmassist_crm.doctor d
JOIN pharmassist_maestros.maestro_medicos mm ON d.id = mm.doctor_id_crm
JOIN pharmassist_cup.prescripcion p ON mm.cdgmedico_cup = p.cdgmedico
JOIN pharmassist_maestros.maestro_integrador_producto mip ON p.cdgmarca = mip.cdgmarca_cup
WHERE p.anio >= YEAR(CURRENT_DATE) - 1
  AND mip.producto_id_crm IS NULL  -- producto de competencia (no nuestro)
  AND d.activo = true
GROUP BY d.id, d.nombre, d.apellido, d.especialidad_id
ORDER BY prescripciones_competencia DESC
LIMIT 20
;


-- =============================================================================
-- PREGUNTA 7: "Medicamentos que NO promociono y más prescribe Dr. X"
-- =============================================================================
-- Maestros utilizados: maestro_medicos, maestro_integrador_producto
-- Join path:
--   prescripcion.cdgmedico → maestro_medicos.cdgmedico_cup (CUP → maestro)
--   maestro_medicos.doctor_id_crm = :doctor_id (filtro por médico)
--   prescripcion.cdgmarca  → marca.cdgmarca (CUP nombre de marca)
--   prescripcion.cdgmarca  → maestro_integrador_producto.cdgmarca_cup (LEFT JOIN)
-- Resultado: Para un médico dado, productos que prescribe pero que NO están
--            en nuestra cartera (oportunidad de competencia).
-- Parámetro: :doctor_id (ID del médico en CRM)
-- =============================================================================

SELECT
    p.cdgmarca,
    marca.nombre AS nombre_marca,
    SUM(p.unidades) AS total_prescripciones
FROM pharmassist_cup.prescripcion p
JOIN pharmassist_cup.marca marca ON p.cdgmarca = marca.cdgmarca
JOIN pharmassist_maestros.maestro_medicos mm ON p.cdgmedico = mm.cdgmedico_cup
LEFT JOIN pharmassist_maestros.maestro_integrador_producto mip ON p.cdgmarca = mip.cdgmarca_cup
WHERE mm.doctor_id_crm = :doctor_id  -- parámetro: ID del médico en CRM
  AND p.anio >= YEAR(CURRENT_DATE) - 1
  AND mip.producto_id_crm IS NULL  -- no es nuestro producto
GROUP BY p.cdgmarca, marca.nombre
ORDER BY total_prescripciones DESC
LIMIT 10
;


-- =============================================================================
-- PREGUNTA 8: "Medicamentos que SÍ promociono y más prescribe Dr. X"
-- =============================================================================
-- Maestros utilizados: maestro_medicos, maestro_integrador_producto
-- Join path:
--   prescripcion.cdgmedico → maestro_medicos.cdgmedico_cup (CUP → maestro)
--   maestro_medicos.doctor_id_crm = :doctor_id (filtro por médico)
--   prescripcion.cdgmarca  → maestro_integrador_producto.cdgmarca_cup
--   maestro_integrador_producto.producto_id_crm → familia_producto.id (CRM)
-- Resultado: Para un médico dado, nuestros productos que más prescribe
--            (validación de efectividad de visita médica).
-- Parámetro: :doctor_id (ID del médico en CRM)
-- =============================================================================

SELECT
    mip.nombre_interno,
    fp.nombre AS nombre_familia,
    SUM(p.unidades) AS total_prescripciones
FROM pharmassist_cup.prescripcion p
JOIN pharmassist_maestros.maestro_medicos mm ON p.cdgmedico = mm.cdgmedico_cup
JOIN pharmassist_maestros.maestro_integrador_producto mip ON p.cdgmarca = mip.cdgmarca_cup
JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
WHERE mm.doctor_id_crm = :doctor_id  -- parámetro: ID del médico en CRM
  AND p.anio >= YEAR(CURRENT_DATE) - 1
  AND mip.producto_id_crm IS NOT NULL  -- es nuestro producto
GROUP BY mip.nombre_interno, fp.nombre
ORDER BY total_prescripciones DESC
LIMIT 10
;
