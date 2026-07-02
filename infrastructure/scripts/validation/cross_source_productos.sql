-- =============================================================================
-- Validación Cross-Source: Productos (CRM + CloseUp + IQVIA via maestro_integrador_producto)
-- =============================================================================
-- Fuentes: pharmassist_crm.familia_producto, pharmassist_maestros.maestro_integrador_producto,
--          pharmassist_cup.prescripcion, pharmassist_iqvia.fact_mercado_valor
-- Prerequisito: Pipeline de ingesta ejecutado al menos 1 vez
-- Ejecutar en: Athena (workgroup pharmassist-validation)
-- Valida: Requerimientos 6.1 a 6.6
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 6.1 Join CRM + CloseUp solamente (productos con prescripciones)
-- Valida que el join via maestro_integrador_producto entre CRM y CloseUp
-- retorna al menos 1 fila con nombre de producto y suma de unidades prescritas
-- ---------------------------------------------------------------------------
SELECT
    fp.nombre AS producto_familia,
    mip.nombre_interno,
    SUM(p.unidades) AS prescripciones_cup
FROM pharmassist_maestros.maestro_integrador_producto mip
JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
JOIN pharmassist_cup.prescripcion p ON mip.cdgmarca_cup = p.cdgmarca
    AND p.anio >= YEAR(CURRENT_DATE) - 1
WHERE mip.producto_id_crm IS NOT NULL
  AND mip.cdgmarca_cup IS NOT NULL
GROUP BY fp.nombre, mip.nombre_interno
HAVING SUM(p.unidades) > 0
ORDER BY prescripciones_cup DESC;


-- ---------------------------------------------------------------------------
-- 6.2 Join CRM + IQVIA solamente (productos con ventas)
-- Valida que el join via maestro_integrador_producto entre CRM e IQVIA
-- retorna al menos 1 fila con nombre de producto y suma de unidades vendidas
-- ---------------------------------------------------------------------------
SELECT
    fp.nombre AS producto_familia,
    mip.nombre_interno,
    SUM(fmv.unidades) AS ventas_iqvia
FROM pharmassist_maestros.maestro_integrador_producto mip
JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
JOIN pharmassist_iqvia.fact_mercado_valor fmv ON mip.idpresentacion_iqvia = fmv.idpresentacion
WHERE mip.producto_id_crm IS NOT NULL
  AND mip.idpresentacion_iqvia IS NOT NULL
GROUP BY fp.nombre, mip.nombre_interno
HAVING SUM(fmv.unidades) > 0
ORDER BY ventas_iqvia DESC;


-- ---------------------------------------------------------------------------
-- 6.3 Triple join: CRM + CloseUp + IQVIA (productos con cobertura completa)
-- Valida que productos con los 3 códigos poblados retornan prescripciones
-- y/o ventas. Debe completar en menos de 90 segundos.
-- ---------------------------------------------------------------------------
SELECT
    fp.nombre AS producto_familia,
    mip.nombre_interno,
    SUM(p.unidades) AS prescripciones_cup,
    SUM(fmv.unidades) AS ventas_iqvia
FROM pharmassist_maestros.maestro_integrador_producto mip
JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
LEFT JOIN pharmassist_cup.prescripcion p ON mip.cdgmarca_cup = p.cdgmarca
    AND p.anio >= YEAR(CURRENT_DATE) - 1
LEFT JOIN pharmassist_iqvia.fact_mercado_valor fmv ON mip.idpresentacion_iqvia = fmv.idpresentacion
WHERE mip.producto_id_crm IS NOT NULL
  AND mip.cdgmarca_cup IS NOT NULL
  AND mip.idpresentacion_iqvia IS NOT NULL
GROUP BY fp.nombre, mip.nombre_interno
HAVING SUM(p.unidades) > 0 OR SUM(fmv.unidades) > 0
ORDER BY prescripciones_cup DESC;


-- ---------------------------------------------------------------------------
-- 6.4 LEFT JOIN mostrando NULL para productos sin código CloseUp
-- Productos donde cdgmarca_cup IS NULL no deben tener datos de prescripciones.
-- Resultado esperado: todas las columnas de prescripción en NULL.
-- ---------------------------------------------------------------------------
SELECT
    fp.nombre AS producto_familia,
    mip.nombre_interno,
    mip.cdgmarca_cup,
    p.cdgmarca AS prescripcion_cdgmarca,
    p.unidades AS prescripcion_unidades
FROM pharmassist_maestros.maestro_integrador_producto mip
JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
LEFT JOIN pharmassist_cup.prescripcion p ON mip.cdgmarca_cup = p.cdgmarca
    AND p.anio >= YEAR(CURRENT_DATE) - 1
WHERE mip.producto_id_crm IS NOT NULL
  AND mip.cdgmarca_cup IS NULL
LIMIT 20;


-- ---------------------------------------------------------------------------
-- 6.5 LEFT JOIN mostrando NULL para productos sin código IQVIA
-- Productos donde idpresentacion_iqvia IS NULL no deben tener datos de ventas.
-- Resultado esperado: todas las columnas de ventas en NULL.
-- ---------------------------------------------------------------------------
SELECT
    fp.nombre AS producto_familia,
    mip.nombre_interno,
    mip.idpresentacion_iqvia,
    fmv.idpresentacion AS ventas_idpresentacion,
    fmv.unidades AS ventas_unidades
FROM pharmassist_maestros.maestro_integrador_producto mip
JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
LEFT JOIN pharmassist_iqvia.fact_mercado_valor fmv ON mip.idpresentacion_iqvia = fmv.idpresentacion
WHERE mip.producto_id_crm IS NOT NULL
  AND mip.idpresentacion_iqvia IS NULL
LIMIT 20;


-- ---------------------------------------------------------------------------
-- 6.6 Validación de fallo: sin productos con cobertura completa
-- Si no existen productos con los 3 códigos que retornen datos, reportar error.
-- ---------------------------------------------------------------------------
SELECT
    (SELECT COUNT(*)
     FROM pharmassist_maestros.maestro_integrador_producto
     WHERE producto_id_crm IS NOT NULL
       AND cdgmarca_cup IS NOT NULL
       AND idpresentacion_iqvia IS NOT NULL) AS productos_cobertura_completa,
    (SELECT COUNT(*)
     FROM pharmassist_maestros.maestro_integrador_producto mip
     JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
     LEFT JOIN pharmassist_cup.prescripcion p ON mip.cdgmarca_cup = p.cdgmarca
         AND p.anio >= YEAR(CURRENT_DATE) - 1
     LEFT JOIN pharmassist_iqvia.fact_mercado_valor fmv ON mip.idpresentacion_iqvia = fmv.idpresentacion
     WHERE mip.producto_id_crm IS NOT NULL
       AND mip.cdgmarca_cup IS NOT NULL
       AND mip.idpresentacion_iqvia IS NOT NULL
     GROUP BY fp.nombre, mip.nombre_interno
     HAVING SUM(p.unidades) > 0 OR SUM(fmv.unidades) > 0) AS productos_con_datos,
    CASE
        WHEN (SELECT COUNT(*)
              FROM pharmassist_maestros.maestro_integrador_producto
              WHERE producto_id_crm IS NOT NULL
                AND cdgmarca_cup IS NOT NULL
                AND idpresentacion_iqvia IS NOT NULL) > 0
         AND (SELECT COUNT(*)
              FROM pharmassist_maestros.maestro_integrador_producto mip
              JOIN pharmassist_crm.familia_producto fp ON mip.producto_id_crm = fp.id
              LEFT JOIN pharmassist_cup.prescripcion p ON mip.cdgmarca_cup = p.cdgmarca
                  AND p.anio >= YEAR(CURRENT_DATE) - 1
              LEFT JOIN pharmassist_iqvia.fact_mercado_valor fmv ON mip.idpresentacion_iqvia = fmv.idpresentacion
              WHERE mip.producto_id_crm IS NOT NULL
                AND mip.cdgmarca_cup IS NOT NULL
                AND mip.idpresentacion_iqvia IS NOT NULL
              GROUP BY fp.nombre, mip.nombre_interno
              HAVING SUM(p.unidades) > 0 OR SUM(fmv.unidades) > 0) = 0
        THEN 'ERROR: productos con cobertura completa pero sin datos de prescripciones ni ventas'
        ELSE 'OK'
    END AS resultado_validacion;
