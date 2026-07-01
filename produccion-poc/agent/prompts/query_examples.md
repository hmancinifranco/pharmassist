# Ejemplos de Queries SQL — PharmAssist

Patrones SQL para preguntas frecuentes del APM. Usar como referencia para generar queries correctas.

## Ejemplo 1: ¿Cuántos médicos tengo en mi cartera?

**Pregunta**: "¿Cuántos médicos tengo?" / "Tamaño de mi cartera"

```sql
SELECT COUNT(*) as total_medicos
FROM cartera_medica
WHERE apm_id = APM_ID
  AND inactivo = false
```

**Lógica**: Contar registros activos en cartera_medica para el APM logueado.

## Ejemplo 2: ¿Cuáles son los productos foco del ciclo actual?

**Pregunta**: "¿Qué productos foco tengo?" / "Productos priorizados este ciclo"

```sql
SELECT fp.nombre as producto,
       cp.abreviatura as categoria,
       cp.nombre_categoria
FROM detalle_promocion_producto dpp
JOIN familia_producto fp ON fp.id = dpp.id_familia_producto
JOIN categoria_promocion cp ON cp.id = dpp.id_categoria_promocion
WHERE dpp.id_ciclo = CICLO_ACTUAL
  AND dpp.id_categoria_promocion IN ('1', '2')
ORDER BY dpp.id_categoria_promocion, fp.nombre
```

**Lógica**: Obtener familias de producto marcadas como Hiperfoco ('1') o Foco ('2') para el ciclo vigente.

## Ejemplo 3: Top 10 médicos por EVO TRM positivo (nuestros productos)

**Pregunta**: "¿Qué médicos están creciendo en prescripciones de nuestros productos?"

```sql
SELECT d."primerNombre" || ' ' || d."primerApellido" as medico,
       umm."marcaNombre",
       umm."ShareMarcaTrim" - umm."ShareMarcaTrim_1" as evo_trm,
       umm."ShareMarcaTrim" as share_actual
FROM cartera_medica cm
JOIN doctor d ON d.id = cm.doctor_id
JOIN "UltimaMillaMedico" ummed ON ummed."idMedicoAPX" = d.id
JOIN "UltimaMillaMarca" umm ON umm."idMedicoCUP" = ummed."idMedicoCUP"
WHERE cm.apm_id = APM_ID
  AND cm.inactivo = false
  AND umm."idLaboratorio" = 'ELE'
  AND (umm."ShareMarcaTrim" - umm."ShareMarcaTrim_1") > 0
ORDER BY (umm."ShareMarcaTrim" - umm."ShareMarcaTrim_1") DESC
LIMIT 10
```

**Lógica**: Calcular EVO_TRM = ShareMarcaTrim - ShareMarcaTrim_1 para productos propios (ELE), filtrando solo los que crecieron, dentro de la cartera del APM.


## Ejemplo 4: ¿Cuál es el share de nuestros productos en mi cartera?

**Pregunta**: "Share de nuestros productos" / "¿Cómo estamos vs competencia?"

```sql
SELECT umm."marcaNombre",
       ROUND(AVG(umm."ShareMarcaMercado"), 4) as share_promedio,
       ROUND(AVG(umm."ShareMarcaTrim"), 4) as share_trim_promedio,
       COUNT(DISTINCT umm."idMedicoCUP") as medicos_prescriptores
FROM cartera_medica cm
JOIN "UltimaMillaMedico" ummed ON ummed."idMedicoAPX" = cm.doctor_id
JOIN "UltimaMillaMarca" umm ON umm."idMedicoCUP" = ummed."idMedicoCUP"
WHERE cm.apm_id = APM_ID
  AND cm.inactivo = false
  AND umm."idLaboratorio" = 'ELE'
GROUP BY umm."marcaNombre"
ORDER BY share_promedio DESC
```

**Lógica**: Para cada marca propia (ELE), calcular el share promedio entre los médicos de la cartera del APM. Muestra cuántos médicos prescriben cada marca.

## Ejemplo 5: Médicos prescriptores de productos foco que no estoy visitando

**Pregunta**: "¿Qué médicos prescriben mis productos foco pero no los visito?"

```sql
WITH productos_foco AS (
    SELECT fp.id as id_familia, fp.nombre,
           fam."codMarcaCUP"
    FROM detalle_promocion_producto dpp
    JOIN familia_producto fp ON fp.id = dpp.id_familia_producto
    JOIN familia_APX_a_Marca_CUP fam ON fam.id_familia_producto_apx = fp.id
    WHERE dpp.id_ciclo = CICLO_ACTUAL
      AND dpp.id_categoria_promocion IN ('1', '2')
),
mis_medicos_prescriptores AS (
    SELECT DISTINCT cm.doctor_id,
           d."primerNombre" || ' ' || d."primerApellido" as medico,
           umm."ShareMarcaTrim"
    FROM cartera_medica cm
    JOIN doctor d ON d.id = cm.doctor_id
    JOIN "UltimaMillaMedico" ummed ON ummed."idMedicoAPX" = cm.doctor_id
    JOIN "UltimaMillaMarca" umm ON umm."idMedicoCUP" = ummed."idMedicoCUP"
    JOIN productos_foco pf ON pf."codMarcaCUP" = umm."idMarca"
    WHERE cm.apm_id = APM_ID
      AND cm.inactivo = false
      AND umm."ShareMarcaTrim" > 0
),
visitados_ultimo_trimestre AS (
    SELECT DISTINCT doctor_id
    FROM agenda
    WHERE apm_id = APM_ID
      AND inactivo = false
      AND inicio >= CURRENT_DATE - INTERVAL '90 days'
)
SELECT mp.medico, mp."ShareMarcaTrim"
FROM mis_medicos_prescriptores mp
WHERE mp.doctor_id NOT IN (SELECT doctor_id FROM visitados_ultimo_trimestre)
ORDER BY mp."ShareMarcaTrim" DESC
LIMIT 20
```

**Lógica**: 
1. Identificar productos foco del ciclo y sus códigos CUP
2. Encontrar médicos de mi cartera que prescriben esos productos
3. Excluir los que ya visité en los últimos 90 días
4. Ordenar por share (los que más prescriben arriba)

## Ejemplo 6: Última visita a un médico específico

**Pregunta**: "¿Cuándo fue mi última visita al Dr. [nombre]?"

```sql
SELECT a.inicio as fecha_visita,
       a.visita_tipo,
       a.observaciones,
       a.visita_exitosa,
       STRING_AGG(fp.nombre, ', ') as productos_presentados
FROM agenda a
LEFT JOIN agenda_producto ap ON ap.id_agenda = a.id
LEFT JOIN familia_producto fp ON fp.id = ap.id_producto
JOIN doctor d ON d.id = a.doctor_id
WHERE a.apm_id = APM_ID
  AND a.inactivo = false
  AND (d."primerApellido" ILIKE '%NOMBRE%' OR d."primerNombre" ILIKE '%NOMBRE%')
GROUP BY a.id, a.inicio, a.visita_tipo, a.observaciones, a.visita_exitosa
ORDER BY a.inicio DESC
LIMIT 5
```

**Lógica**: Buscar las últimas visitas al médico por nombre (case-insensitive), incluyendo productos presentados en cada visita.

## Ejemplo 7: Resumen de visitas del último mes

**Pregunta**: "¿Cuántas visitas hice este mes?" / "Resumen de actividad"

```sql
SELECT visita_tipo,
       COUNT(*) as total,
       SUM(CASE WHEN visita_exitosa THEN 1 ELSE 0 END) as exitosas
FROM agenda
WHERE apm_id = APM_ID
  AND inactivo = false
  AND inicio >= DATE_TRUNC('month', CURRENT_DATE)
GROUP BY visita_tipo
ORDER BY total DESC
```

**Lógica**: Agrupar visitas del mes actual por tipo, contando exitosas vs totales.
