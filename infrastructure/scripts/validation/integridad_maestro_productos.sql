-- =============================================================================
-- Validación de Integridad Referencial: maestro_integrador_producto
-- =============================================================================
-- Base de datos: pharmassist_maestros.maestro_integrador_producto
-- Prerequisito: Pipeline de ingesta ejecutado al menos 1 vez
-- Ejecutar en: Athena (workgroup pharmassist-validation)
-- Valida: Requerimientos 3.1 a 3.6
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 3.1 Constraint al_menos_un_codigo: al menos uno de producto_id_crm,
-- cdgmarca_cup o idpresentacion_iqvia debe ser no nulo
-- ---------------------------------------------------------------------------
SELECT
    'violacion_al_menos_un_codigo' AS validacion,
    COUNT(*) AS cantidad_violaciones
FROM pharmassist_maestros.maestro_integrador_producto
WHERE producto_id_crm IS NULL
  AND cdgmarca_cup IS NULL
  AND idpresentacion_iqvia IS NULL;


-- Detalle de registros que violan la constraint
SELECT
    id,
    nombre_interno,
    fecha_actualizacion
FROM pharmassist_maestros.maestro_integrador_producto
WHERE producto_id_crm IS NULL
  AND cdgmarca_cup IS NULL
  AND idpresentacion_iqvia IS NULL;


-- ---------------------------------------------------------------------------
-- 3.2 Distribución por cantidad de códigos mapeados
-- Productos con 3 códigos (cobertura completa), sin cdgmarca_cup, sin idpresentacion_iqvia
-- ---------------------------------------------------------------------------
SELECT
    'productos_con_3_codigos' AS categoria,
    COUNT(*) AS cantidad,
    ROUND(CAST(COUNT(*) AS DOUBLE)
        / NULLIF(CAST((SELECT COUNT(*) FROM pharmassist_maestros.maestro_integrador_producto) AS DOUBLE), 0)
        * 100, 2
    ) AS porcentaje
FROM pharmassist_maestros.maestro_integrador_producto
WHERE producto_id_crm IS NOT NULL
  AND cdgmarca_cup IS NOT NULL
  AND idpresentacion_iqvia IS NOT NULL

UNION ALL

SELECT
    'productos_sin_cdgmarca_cup' AS categoria,
    COUNT(*) AS cantidad,
    ROUND(CAST(COUNT(*) AS DOUBLE)
        / NULLIF(CAST((SELECT COUNT(*) FROM pharmassist_maestros.maestro_integrador_producto) AS DOUBLE), 0)
        * 100, 2
    ) AS porcentaje
FROM pharmassist_maestros.maestro_integrador_producto
WHERE cdgmarca_cup IS NULL

UNION ALL

SELECT
    'productos_sin_idpresentacion_iqvia' AS categoria,
    COUNT(*) AS cantidad,
    ROUND(CAST(COUNT(*) AS DOUBLE)
        / NULLIF(CAST((SELECT COUNT(*) FROM pharmassist_maestros.maestro_integrador_producto) AS DOUBLE), 0)
        * 100, 2
    ) AS porcentaje
FROM pharmassist_maestros.maestro_integrador_producto
WHERE idpresentacion_iqvia IS NULL;


-- ---------------------------------------------------------------------------
-- 3.3 Huérfanos: producto_id_crm sin correspondencia en
-- pharmassist_crm.familia_producto
-- ---------------------------------------------------------------------------
SELECT
    'huerfanos_producto_id_crm' AS validacion,
    COUNT(*) AS cantidad_huerfanos
FROM pharmassist_maestros.maestro_integrador_producto mip
LEFT JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
WHERE mip.producto_id_crm IS NOT NULL
  AND fp.id IS NULL;


-- ---------------------------------------------------------------------------
-- 3.4 Huérfanos: cdgmarca_cup sin correspondencia en pharmassist_cup.marca
-- ---------------------------------------------------------------------------
SELECT
    'huerfanos_cdgmarca_cup' AS validacion,
    COUNT(*) AS cantidad_huerfanos
FROM pharmassist_maestros.maestro_integrador_producto mip
LEFT JOIN pharmassist_cup.marca m ON mip.cdgmarca_cup = m.cdgmarca
WHERE mip.cdgmarca_cup IS NOT NULL
  AND m.cdgmarca IS NULL;


-- ---------------------------------------------------------------------------
-- 3.5 Huérfanos: idpresentacion_iqvia sin correspondencia en
-- pharmassist_iqvia.dim_presentacion
-- ---------------------------------------------------------------------------
SELECT
    'huerfanos_idpresentacion_iqvia' AS validacion,
    COUNT(*) AS cantidad_huerfanos
FROM pharmassist_maestros.maestro_integrador_producto mip
LEFT JOIN pharmassist_iqvia.dim_presentacion dp ON mip.idpresentacion_iqvia = dp.idpresentacion
WHERE mip.idpresentacion_iqvia IS NOT NULL
  AND dp.idpresentacion IS NULL;


-- ---------------------------------------------------------------------------
-- 3.6 Resumen consolidado de violaciones de integridad referencial
-- ---------------------------------------------------------------------------
SELECT 'violacion_al_menos_un_codigo' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.maestro_integrador_producto
WHERE producto_id_crm IS NULL
  AND cdgmarca_cup IS NULL
  AND idpresentacion_iqvia IS NULL

UNION ALL

SELECT 'huerfanos_producto_id_crm' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.maestro_integrador_producto mip
LEFT JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
WHERE mip.producto_id_crm IS NOT NULL AND fp.id IS NULL

UNION ALL

SELECT 'huerfanos_cdgmarca_cup' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.maestro_integrador_producto mip
LEFT JOIN pharmassist_cup.marca m ON mip.cdgmarca_cup = m.cdgmarca
WHERE mip.cdgmarca_cup IS NOT NULL AND m.cdgmarca IS NULL

UNION ALL

SELECT 'huerfanos_idpresentacion_iqvia' AS tipo_violacion, COUNT(*) AS cantidad
FROM pharmassist_maestros.maestro_integrador_producto mip
LEFT JOIN pharmassist_iqvia.dim_presentacion dp ON mip.idpresentacion_iqvia = dp.idpresentacion
WHERE mip.idpresentacion_iqvia IS NOT NULL AND dp.idpresentacion IS NULL;
