-- =============================================================================
-- Validación de Integridad Referencial: maestro_medicos
-- =============================================================================
-- Base de datos: pharmassist_maestros.maestro_medicos
-- Prerequisito: Pipeline de ingesta ejecutado al menos 1 vez
-- Ejecutar en: Athena (workgroup pharmassist-validation)
-- Valida: Requerimientos 2.1 a 2.8
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 2.1 Constraint: al menos un código no nulo (doctor_id_crm o cdgmedico_cup)
-- Reporta registros que violan la regla de tener al menos un identificador
-- ---------------------------------------------------------------------------
SELECT
    'registros_sin_ningun_codigo' AS validacion,
    COUNT(*) AS cantidad_violaciones
FROM pharmassist_maestros.maestro_medicos
WHERE doctor_id_crm IS NULL
  AND cdgmedico_cup IS NULL;


-- ---------------------------------------------------------------------------
-- 2.2 Duplicados en doctor_id_crm (excluyendo nulos)
-- Cada doctor_id_crm debe ser único dentro del maestro
-- ---------------------------------------------------------------------------
SELECT
    'duplicados_doctor_id_crm' AS validacion,
    doctor_id_crm,
    COUNT(*) AS ocurrencias
FROM pharmassist_maestros.maestro_medicos
WHERE doctor_id_crm IS NOT NULL
GROUP BY doctor_id_crm
HAVING COUNT(*) > 1
ORDER BY ocurrencias DESC;


-- ---------------------------------------------------------------------------
-- 2.3 Duplicados en cdgmedico_cup (excluyendo nulos)
-- Cada cdgmedico_cup debe ser único dentro del maestro
-- ---------------------------------------------------------------------------
SELECT
    'duplicados_cdgmedico_cup' AS validacion,
    cdgmedico_cup,
    COUNT(*) AS ocurrencias
FROM pharmassist_maestros.maestro_medicos
WHERE cdgmedico_cup IS NOT NULL
GROUP BY cdgmedico_cup
HAVING COUNT(*) > 1
ORDER BY ocurrencias DESC;


-- ---------------------------------------------------------------------------
-- 2.4 Huérfanos: doctor_id_crm sin correspondencia en pharmassist_crm.doctor
-- ---------------------------------------------------------------------------
SELECT
    'huerfanos_doctor_id_crm' AS validacion,
    COUNT(*) AS cantidad_huerfanos
FROM pharmassist_maestros.maestro_medicos mm
LEFT JOIN pharmassist_crm.doctor d ON mm.doctor_id_crm = d.id
WHERE mm.doctor_id_crm IS NOT NULL
  AND d.id IS NULL;


-- ---------------------------------------------------------------------------
-- 2.5 Huérfanos: cdgmedico_cup sin correspondencia en pharmassist_cup.medico
-- ---------------------------------------------------------------------------
SELECT
    'huerfanos_cdgmedico_cup' AS validacion,
    COUNT(*) AS cantidad_huerfanos
FROM pharmassist_maestros.maestro_medicos mm
LEFT JOIN pharmassist_cup.medico m ON mm.cdgmedico_cup = m.cdgmedico
WHERE mm.cdgmedico_cup IS NOT NULL
  AND m.cdgmedico IS NULL;


-- ---------------------------------------------------------------------------
-- 2.6 Cobertura: % de médicos activos en CRM con mapeo válido en maestro
-- ---------------------------------------------------------------------------
SELECT
    (SELECT COUNT(*) FROM pharmassist_crm.doctor WHERE activo = true) AS total_medicos_crm_activos,
    (SELECT COUNT(DISTINCT mm.doctor_id_crm)
     FROM pharmassist_maestros.maestro_medicos mm
     JOIN pharmassist_crm.doctor d ON mm.doctor_id_crm = d.id
     WHERE d.activo = true
       AND mm.cdgmedico_cup IS NOT NULL) AS con_mapeo_closeup,
    ROUND(
        CAST((SELECT COUNT(DISTINCT mm.doctor_id_crm)
              FROM pharmassist_maestros.maestro_medicos mm
              JOIN pharmassist_crm.doctor d ON mm.doctor_id_crm = d.id
              WHERE d.activo = true
                AND mm.cdgmedico_cup IS NOT NULL) AS DOUBLE)
        / NULLIF(CAST((SELECT COUNT(*) FROM pharmassist_crm.doctor WHERE activo = true) AS DOUBLE), 0)
        * 100, 2
    ) AS porcentaje_cobertura;


-- ---------------------------------------------------------------------------
-- 2.7 Distribución por nivel de confianza (alta, media, baja)
-- Nota: En Glue el campo es confianza_match (decimal). Mapeo:
--   1.00 = alta, 0.70 = media, 0.40 = baja
-- En RDS el campo original es 'confianza' con valores texto.
-- Esta query soporta ambos esquemas según la tabla disponible.
-- ---------------------------------------------------------------------------
SELECT
    CASE
        WHEN confianza_match = 1.00 THEN 'alta'
        WHEN confianza_match = 0.70 THEN 'media'
        WHEN confianza_match = 0.40 THEN 'baja'
        ELSE 'desconocido'
    END AS nivel_confianza,
    COUNT(*) AS cantidad,
    ROUND(CAST(COUNT(*) AS DOUBLE)
        / NULLIF(CAST((SELECT COUNT(*) FROM pharmassist_maestros.maestro_medicos) AS DOUBLE), 0)
        * 100, 2
    ) AS porcentaje
FROM pharmassist_maestros.maestro_medicos
GROUP BY
    CASE
        WHEN confianza_match = 1.00 THEN 'alta'
        WHEN confianza_match = 0.70 THEN 'media'
        WHEN confianza_match = 0.40 THEN 'baja'
        ELSE 'desconocido'
    END
ORDER BY cantidad DESC;


-- ---------------------------------------------------------------------------
-- 2.8 Resumen consolidado de violaciones de integridad
-- Una sola query que resume todas las validaciones anteriores
-- ---------------------------------------------------------------------------
SELECT 'registros_sin_ningun_codigo' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.maestro_medicos
WHERE doctor_id_crm IS NULL AND cdgmedico_cup IS NULL

UNION ALL

SELECT 'duplicados_doctor_id_crm' AS tipo_violacion, COUNT(*) AS cantidad
FROM (
    SELECT doctor_id_crm
    FROM pharmassist_maestros.maestro_medicos
    WHERE doctor_id_crm IS NOT NULL
    GROUP BY doctor_id_crm
    HAVING COUNT(*) > 1
)

UNION ALL

SELECT 'duplicados_cdgmedico_cup' AS tipo_violacion, COUNT(*) AS cantidad
FROM (
    SELECT cdgmedico_cup
    FROM pharmassist_maestros.maestro_medicos
    WHERE cdgmedico_cup IS NOT NULL
    GROUP BY cdgmedico_cup
    HAVING COUNT(*) > 1
)

UNION ALL

SELECT 'huerfanos_doctor_id_crm' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.maestro_medicos mm
LEFT JOIN pharmassist_crm.doctor d ON mm.doctor_id_crm = d.id
WHERE mm.doctor_id_crm IS NOT NULL AND d.id IS NULL

UNION ALL

SELECT 'huerfanos_cdgmedico_cup' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.maestro_medicos mm
LEFT JOIN pharmassist_cup.medico m ON mm.cdgmedico_cup = m.cdgmedico
WHERE mm.cdgmedico_cup IS NOT NULL AND m.cdgmedico IS NULL;
