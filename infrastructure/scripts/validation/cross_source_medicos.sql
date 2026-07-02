-- =============================================================================
-- Validación Cross-Source: Médicos (CRM + CloseUp via maestro_medicos)
-- =============================================================================
-- Fuentes: pharmassist_crm.doctor, pharmassist_maestros.maestro_medicos,
--          pharmassist_crm.agenda, pharmassist_cup.prescripcion
-- Prerequisito: Pipeline de ingesta ejecutado al menos 1 vez
-- Ejecutar en: Athena (workgroup pharmassist-validation)
-- Valida: Requerimientos 5.1 a 5.6
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 5.1 / 5.2 Médicos visitados con prescripciones en CloseUp (últimos 12 meses)
-- Valida que el join CRM + CloseUp via maestro_medicos retorna resultados
-- y que la ejecución completa en menos de 30 segundos
-- ---------------------------------------------------------------------------
SELECT
    d.id AS doctor_id_crm,
    d.nombre || ' ' || d.apellido AS nombre_medico,
    mm.cdgmedico_cup,
    COUNT(DISTINCT a.id) AS visitas_12m,
    COALESCE(SUM(p.unidades), 0) AS prescripciones_12m
FROM pharmassist_crm.doctor d
JOIN pharmassist_maestros.maestro_medicos mm ON d.id = mm.doctor_id_crm
LEFT JOIN pharmassist_crm.agenda a ON d.id = a.doctor_id
    AND a.estado = 'Realizada'
    AND a.fecha_inicio >= CURRENT_DATE - INTERVAL '365' DAY
LEFT JOIN pharmassist_cup.prescripcion p ON mm.cdgmedico_cup = p.cdgmedico
    AND p.anio >= YEAR(CURRENT_DATE) - 1
WHERE d.activo = true
  AND mm.cdgmedico_cup IS NOT NULL
GROUP BY d.id, d.nombre, d.apellido, mm.cdgmedico_cup
ORDER BY prescripciones_12m DESC;


-- ---------------------------------------------------------------------------
-- 5.3 Verificar cero registros huérfanos en el join
-- Filas en maestro_medicos.doctor_id_crm sin correspondencia en doctor CRM
-- Resultado esperado: 0 filas (cero huérfanos)
-- ---------------------------------------------------------------------------
SELECT
    'huerfanos_doctor_id_crm' AS tipo_validacion,
    COUNT(*) AS cantidad_huerfanos
FROM pharmassist_maestros.maestro_medicos mm
LEFT JOIN pharmassist_crm.doctor d ON mm.doctor_id_crm = d.id
WHERE mm.doctor_id_crm IS NOT NULL
  AND d.id IS NULL;


-- ---------------------------------------------------------------------------
-- 5.4 Verificar que médicos con confianza 'alta' producen resultados
-- Cada médico con mapeo de alta confianza debe tener al menos una
-- prescripción en CloseUp. Si retorna filas, son médicos alta-confianza
-- sin actividad de prescripciones (posible problema de datos).
-- ---------------------------------------------------------------------------
SELECT
    mm.doctor_id_crm,
    mm.cdgmedico_cup,
    'alta_confianza_sin_prescripciones' AS tipo_validacion
FROM pharmassist_maestros.maestro_medicos mm
LEFT JOIN pharmassist_cup.prescripcion p ON mm.cdgmedico_cup = p.cdgmedico
    AND p.anio >= YEAR(CURRENT_DATE) - 1
WHERE mm.cdgmedico_cup IS NOT NULL
  AND mm.confianza = 'alta'
GROUP BY mm.doctor_id_crm, mm.cdgmedico_cup
HAVING COALESCE(SUM(p.unidades), 0) = 0;


-- ---------------------------------------------------------------------------
-- 5.5 Verificar scan del query principal no excede 100MB
-- Ejecutar el query principal con EXPLAIN para estimar bytes escaneados.
-- Si el resultado excede 100MB, el query es candidato a optimización
-- con particionado o filtros adicionales.
-- NOTA: Ejecutar manualmente con EXPLAIN para verificar el scan estimado.
-- ---------------------------------------------------------------------------
-- EXPLAIN
-- SELECT ... (usar el query de 5.1/5.2 con EXPLAIN para verificar scan)


-- ---------------------------------------------------------------------------
-- 5.6 Validación de fallo: cero resultados con registros alta confianza
-- Si existen registros con confianza 'alta' en maestro_medicos pero el
-- cross-source query retorna 0 filas, reportar como fallo de integridad.
-- Este query cuenta registros alta confianza y resultados del join.
-- ---------------------------------------------------------------------------
SELECT
    (SELECT COUNT(*)
     FROM pharmassist_maestros.maestro_medicos
     WHERE confianza = 'alta'
       AND cdgmedico_cup IS NOT NULL) AS registros_alta_confianza,
    (SELECT COUNT(*)
     FROM pharmassist_crm.doctor d
     JOIN pharmassist_maestros.maestro_medicos mm ON d.id = mm.doctor_id_crm
     LEFT JOIN pharmassist_cup.prescripcion p ON mm.cdgmedico_cup = p.cdgmedico
         AND p.anio >= YEAR(CURRENT_DATE) - 1
     WHERE d.activo = true
       AND mm.cdgmedico_cup IS NOT NULL
       AND mm.confianza = 'alta'
     GROUP BY d.id
     HAVING COALESCE(SUM(p.unidades), 0) > 0) AS medicos_con_prescripciones,
    CASE
        WHEN (SELECT COUNT(*)
              FROM pharmassist_maestros.maestro_medicos
              WHERE confianza = 'alta'
                AND cdgmedico_cup IS NOT NULL) > 0
         AND (SELECT COUNT(*)
              FROM pharmassist_crm.doctor d
              JOIN pharmassist_maestros.maestro_medicos mm ON d.id = mm.doctor_id_crm
              LEFT JOIN pharmassist_cup.prescripcion p ON mm.cdgmedico_cup = p.cdgmedico
                  AND p.anio >= YEAR(CURRENT_DATE) - 1
              WHERE d.activo = true
                AND mm.cdgmedico_cup IS NOT NULL
                AND mm.confianza = 'alta'
              GROUP BY d.id
              HAVING COALESCE(SUM(p.unidades), 0) > 0) = 0
        THEN 'FALLO: registros alta confianza sin resultados cross-source'
        ELSE 'OK'
    END AS resultado_validacion;
