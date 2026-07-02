-- =============================================================================
-- Validación de Integridad Referencial: familia_interno_a_marca_cup
-- =============================================================================
-- Base de datos: pharmassist_maestros.familia_interno_a_marca_cup
-- Prerequisito: Pipeline de ingesta ejecutado al menos 1 vez
-- Ejecutar en: Athena (workgroup pharmassist-validation)
-- Valida: Requerimientos 4.1 a 4.8
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 4.1 Verificar que ambos campos (familia_producto_id y cdgmarca_cup)
-- son no nulos en cada registro
-- ---------------------------------------------------------------------------
SELECT
    'registros_con_familia_producto_id_nulo' AS validacion,
    COUNT(*) AS cantidad
FROM pharmassist_maestros.familia_interno_a_marca_cup
WHERE familia_producto_id IS NULL

UNION ALL

SELECT
    'registros_con_cdgmarca_cup_nulo' AS validacion,
    COUNT(*) AS cantidad
FROM pharmassist_maestros.familia_interno_a_marca_cup
WHERE cdgmarca_cup IS NULL;


-- ---------------------------------------------------------------------------
-- 4.2 Familias distintas con al menos un mapeo a marca CloseUp
-- ---------------------------------------------------------------------------
SELECT
    'familias_con_mapeo' AS validacion,
    COUNT(DISTINCT familia_producto_id) AS cantidad_familias
FROM pharmassist_maestros.familia_interno_a_marca_cup
WHERE familia_producto_id IS NOT NULL
  AND cdgmarca_cup IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 4.3 Familias huérfanas: familias activas en CRM sin ningún mapeo
-- en familia_interno_a_marca_cup
-- ---------------------------------------------------------------------------
SELECT
    'familias_crm_sin_mapeo' AS validacion,
    COUNT(*) AS cantidad_huerfanas
FROM pharmassist_crm.familia_producto fp
LEFT JOIN pharmassist_maestros.familia_interno_a_marca_cup fam
    ON fp.id = fam.familia_producto_id
WHERE fp.activo = true
  AND fam.familia_producto_id IS NULL;

-- Detalle de familias huérfanas
SELECT
    fp.id AS familia_producto_id,
    fp.nombre AS nombre_familia,
    fp.linea_id
FROM pharmassist_crm.familia_producto fp
LEFT JOIN pharmassist_maestros.familia_interno_a_marca_cup fam
    ON fp.id = fam.familia_producto_id
WHERE fp.activo = true
  AND fam.familia_producto_id IS NULL
ORDER BY fp.nombre;


-- ---------------------------------------------------------------------------
-- 4.4 Validar campo confianza_match contiene solo valores válidos
-- En Glue: confianza_match con valores 1.00, 0.70, 0.40
-- (Corresponde a relacion: exacta, parcial, generico en RDS)
-- ---------------------------------------------------------------------------
SELECT
    'valores_confianza_match_invalidos' AS validacion,
    confianza_match,
    COUNT(*) AS cantidad
FROM pharmassist_maestros.familia_interno_a_marca_cup
WHERE confianza_match NOT IN (1.00, 0.70, 0.40)
GROUP BY confianza_match
ORDER BY cantidad DESC;


-- ---------------------------------------------------------------------------
-- 4.5 Pares duplicados: mismo familia_producto_id + cdgmarca_cup
-- apareciendo más de una vez
-- ---------------------------------------------------------------------------
SELECT
    familia_producto_id,
    cdgmarca_cup,
    COUNT(*) AS ocurrencias
FROM pharmassist_maestros.familia_interno_a_marca_cup
GROUP BY familia_producto_id, cdgmarca_cup
HAVING COUNT(*) > 1
ORDER BY ocurrencias DESC;


-- ---------------------------------------------------------------------------
-- 4.6 Distribución de tipos de relación (confianza_match)
-- 1.00 = exacta, 0.70 = parcial, 0.40 = generico
-- ---------------------------------------------------------------------------
SELECT
    CASE
        WHEN confianza_match = 1.00 THEN 'exacta'
        WHEN confianza_match = 0.70 THEN 'parcial'
        WHEN confianza_match = 0.40 THEN 'generico'
        ELSE 'desconocido'
    END AS tipo_relacion,
    COUNT(*) AS cantidad,
    ROUND(CAST(COUNT(*) AS DOUBLE)
        / NULLIF(CAST((SELECT COUNT(*) FROM pharmassist_maestros.familia_interno_a_marca_cup) AS DOUBLE), 0)
        * 100, 2
    ) AS porcentaje
FROM pharmassist_maestros.familia_interno_a_marca_cup
GROUP BY
    CASE
        WHEN confianza_match = 1.00 THEN 'exacta'
        WHEN confianza_match = 0.70 THEN 'parcial'
        WHEN confianza_match = 0.40 THEN 'generico'
        ELSE 'desconocido'
    END
ORDER BY cantidad DESC;


-- ---------------------------------------------------------------------------
-- 4.7 Huérfanos: familia_producto_id sin correspondencia en
-- pharmassist_crm.familia_producto
-- ---------------------------------------------------------------------------
SELECT
    'huerfanos_familia_producto_id' AS validacion,
    COUNT(*) AS cantidad_huerfanos
FROM pharmassist_maestros.familia_interno_a_marca_cup fam
LEFT JOIN pharmassist_crm.familia_producto fp ON fam.familia_producto_id = fp.id
WHERE fam.familia_producto_id IS NOT NULL
  AND fp.id IS NULL;


-- ---------------------------------------------------------------------------
-- 4.8 Huérfanos: cdgmarca_cup sin correspondencia en pharmassist_cup.marca
-- ---------------------------------------------------------------------------
SELECT
    'huerfanos_cdgmarca_cup' AS validacion,
    COUNT(*) AS cantidad_huerfanos
FROM pharmassist_maestros.familia_interno_a_marca_cup fam
LEFT JOIN pharmassist_cup.marca m ON fam.cdgmarca_cup = m.cdgmarca
WHERE fam.cdgmarca_cup IS NOT NULL
  AND m.cdgmarca IS NULL;


-- ---------------------------------------------------------------------------
-- Resumen consolidado de violaciones de integridad
-- ---------------------------------------------------------------------------
SELECT 'registros_con_campos_nulos' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.familia_interno_a_marca_cup
WHERE familia_producto_id IS NULL OR cdgmarca_cup IS NULL

UNION ALL

SELECT 'pares_duplicados' AS tipo_violacion, COUNT(*) AS cantidad
FROM (
    SELECT familia_producto_id, cdgmarca_cup
    FROM pharmassist_maestros.familia_interno_a_marca_cup
    GROUP BY familia_producto_id, cdgmarca_cup
    HAVING COUNT(*) > 1
)

UNION ALL

SELECT 'valores_confianza_invalidos' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.familia_interno_a_marca_cup
WHERE confianza_match NOT IN (1.00, 0.70, 0.40)

UNION ALL

SELECT 'huerfanos_familia_producto_id' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.familia_interno_a_marca_cup fam
LEFT JOIN pharmassist_crm.familia_producto fp ON fam.familia_producto_id = fp.id
WHERE fam.familia_producto_id IS NOT NULL AND fp.id IS NULL

UNION ALL

SELECT 'huerfanos_cdgmarca_cup' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.familia_interno_a_marca_cup fam
LEFT JOIN pharmassist_cup.marca m ON fam.cdgmarca_cup = m.cdgmarca
WHERE fam.cdgmarca_cup IS NOT NULL AND m.cdgmarca IS NULL;
