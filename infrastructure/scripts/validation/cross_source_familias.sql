-- =============================================================================
-- Validación Cross-Source: Familias (CRM + CloseUp via familia_interno_a_marca_cup)
-- =============================================================================
-- Fuentes: pharmassist_crm.familia_producto, pharmassist_maestros.familia_interno_a_marca_cup,
--          pharmassist_cup.prescripcion
-- Prerequisito: Pipeline de ingesta ejecutado al menos 1 vez
-- Ejecutar en: Athena (workgroup pharmassist-validation)
-- Valida: Requerimientos 7.1 a 7.5
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 7.1 / 7.2 Familias internas con prescripciones agregadas por marca CUP
-- Aplica DISTINCT sobre cdgmarca_cup antes del join con prescripciones,
-- evitando duplicados cuando múltiples familias mapean a la misma marca.
-- Lista cada familia con la suma de prescripciones de los últimos 12 meses.
-- ---------------------------------------------------------------------------
SELECT
    fp.nombre AS nombre_familia,
    fp.id AS familia_producto_id,
    COUNT(DISTINCT fam_dist.cdgmarca_cup) AS marcas_cup_mapeadas,
    COALESCE(SUM(p.unidades), 0) AS prescripciones_12m
FROM pharmassist_crm.familia_producto fp
JOIN (
    SELECT DISTINCT familia_producto_id, cdgmarca_cup
    FROM pharmassist_maestros.familia_interno_a_marca_cup
) fam_dist ON fp.id = fam_dist.familia_producto_id
LEFT JOIN pharmassist_cup.prescripcion p ON fam_dist.cdgmarca_cup = p.cdgmarca
    AND p.anio >= YEAR(CURRENT_DATE) - 1
WHERE fp.activo = true
GROUP BY fp.nombre, fp.id
ORDER BY prescripciones_12m DESC;


-- ---------------------------------------------------------------------------
-- 7.3 Comparar promedio de marcas CUP por familia según tipo de relación
-- Familias con relación 'exacta' deben tener menor cantidad promedio de
-- marcas CUP por familia (ratio cercano a 1:1) que familias con relación
-- 'parcial' o 'generico'.
-- ---------------------------------------------------------------------------
SELECT
    fam.confianza_match AS tipo_relacion,
    COUNT(DISTINCT fam.familia_producto_id) AS familias_distintas,
    COUNT(DISTINCT fam.cdgmarca_cup) AS marcas_distintas,
    ROUND(
        CAST(COUNT(DISTINCT fam.cdgmarca_cup) AS DOUBLE)
        / NULLIF(CAST(COUNT(DISTINCT fam.familia_producto_id) AS DOUBLE), 0),
        2
    ) AS promedio_marcas_por_familia
FROM pharmassist_maestros.familia_interno_a_marca_cup fam
GROUP BY fam.confianza_match
ORDER BY promedio_marcas_por_familia ASC;


-- ---------------------------------------------------------------------------
-- 7.4 Familias sin cobertura: presentes en CRM pero sin mapeo en
-- familia_interno_a_marca_cup
-- Lista familias activas del CRM que no tienen ningún registro de mapeo.
-- ---------------------------------------------------------------------------
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
-- 7.5 Familias con mapeo pero sin actividad de prescripciones
-- Familias que tienen registros en familia_interno_a_marca_cup pero ninguno
-- de sus cdgmarca_cup asociados aparece en prescripciones de los últimos
-- 12 meses. Indica mapeo existente pero sin datos de actividad reciente.
-- ---------------------------------------------------------------------------
SELECT
    fp.id AS familia_producto_id,
    fp.nombre AS nombre_familia,
    COUNT(DISTINCT fam_dist.cdgmarca_cup) AS marcas_mapeadas,
    'mapeo_sin_actividad_prescripciones' AS tipo_validacion
FROM pharmassist_crm.familia_producto fp
JOIN (
    SELECT DISTINCT familia_producto_id, cdgmarca_cup
    FROM pharmassist_maestros.familia_interno_a_marca_cup
) fam_dist ON fp.id = fam_dist.familia_producto_id
LEFT JOIN pharmassist_cup.prescripcion p ON fam_dist.cdgmarca_cup = p.cdgmarca
    AND p.anio >= YEAR(CURRENT_DATE) - 1
WHERE fp.activo = true
GROUP BY fp.id, fp.nombre
HAVING COALESCE(SUM(p.unidades), 0) = 0
ORDER BY marcas_mapeadas DESC;
