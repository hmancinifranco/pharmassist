# Reglas de Negocio — PharmAssist

## Variables de Sesión Disponibles

- `APM_ID` — ID del APM logueado. Usar SIEMPRE para filtrar datos del APM.
- `CICLO_ACTUAL` — ID del ciclo promocional vigente.

## Regla 1: Scope del APM

**SIEMPRE** filtrar por `APM_ID` para mostrar solo datos del APM logueado:
- `cartera_medica.apm_id = APM_ID`
- `agenda.apm_id = APM_ID`
- `linea_apm.id_apm = APM_ID`

El APM solo ve SUS médicos, SUS visitas, SUS productos.

## Regla 2: Cartera Activa

La cartera médica del APM son solo los registros **activos**:
```sql
WHERE cartera_medica.inactivo = false
```
Nunca incluir médicos inactivos en resultados salvo que el usuario lo pida explícitamente.

## Regla 3: Agenda Activa

Las visitas válidas son solo las **activas**:
```sql
WHERE agenda.inactivo = false
```
Registros inactivos son visitas canceladas o eliminadas.

## Regla 4: EVO TRM (Evolución Trimestral)

La evolución de prescripción de una marca para un médico se calcula:
```
EVO_TRM = "ShareMarcaTrim" - "ShareMarcaTrim_1"
```
- Valor positivo → la marca creció en prescripciones
- Valor negativo → la marca perdió prescripciones
- Se calcula desde la tabla `"UltimaMillaMarca"`

## Regla 5: Productos Foco e Hiperfoco

Los productos **priorizados** en el ciclo actual se identifican en `detalle_promocion_producto`:
- `id_categoria_promocion = '1'` → **Hiperfoco (HP)** — máxima prioridad
- `id_categoria_promocion = '2'` → **Foco (FC)** — alta prioridad

Query para obtener productos foco del ciclo actual:
```sql
SELECT fp.id, fp.nombre, cp.abreviatura as categoria
FROM detalle_promocion_producto dpp
JOIN familia_producto fp ON fp.id = dpp.id_familia_producto
JOIN categoria_promocion cp ON cp.id = dpp.id_categoria_promocion
WHERE dpp.id_ciclo = CICLO_ACTUAL
  AND dpp.id_categoria_promocion IN ('1', '2')
```

## Regla 6: Laboratorio Propio (ELE)

El laboratorio propio se identifica con `idLaboratorio = 'ELE'` en `"UltimaMillaMarca"`.
- Cuando el usuario dice "mis productos" o "nuestros productos" → filtrar `"idLaboratorio" = 'ELE'`
- Cuando dice "competencia" → filtrar `"idLaboratorio" != 'ELE'`

## Regla 7: Cruce APX → CUP

Para conectar los **productos internos** (sistema APX) con los **datos de prescripción** (sistema CUP/IQVIA):

```
familia_producto.id
  → familia_APX_a_Marca_CUP.id_familia_producto_apx
  → familia_APX_a_Marca_CUP."codMarcaCUP"
  → "UltimaMillaMarca"."idMarca"
```

Este cruce es necesario para responder preguntas como:
- "¿Cuánto prescriben mis médicos de [producto foco]?"
- "¿Cuáles son los top prescriptores de [producto nuestro]?"

## Regla 8: Ciclo Vigente

El ciclo actual se obtiene de la variable `CICLO_ACTUAL` (pre-cargada en el REPL).
Para queries que necesiten el ciclo, usar directamente esta variable.

Si necesitás validar fechas del ciclo:
```sql
SELECT id, inicio, fin FROM ciclo WHERE id = CICLO_ACTUAL
```

## Regla 9: Cruce Doctor → Prescripciones

Para obtener prescripciones de un médico de la cartera del APM:
```
doctor.id
  → "UltimaMillaMedico"."idMedicoAPX"
  → "UltimaMillaMedico"."idMedicoCUP"
  → "UltimaMillaMarca"."idMedicoCUP"
```

## Regla 10: Share y Métricas

- `"ShareMarcaMercado"` — Share de la marca en el mercado total (0.0 a 1.0)
- `"ShareMarcaTrim"` — Share trimestral actual
- `"ShareMarcaTrim_1"` — Share trimestre anterior (para calcular EVO)
- `"IEMarcaTrim"` — Índice de esfuerzo trimestral de la marca
- Los shares son proporciones (entre 0 y 1), NO porcentajes

## Regla 11: Tipos de Visita

En `agenda.visita_tipo`:
- `'Presencial'` — visita cara a cara
- `'Virtual'` — videollamada
- `'Telefónica'` — llamada telefónica

## Regla 12: Frecuencia de Visita

En `datos_visita.frecuencia` (vía `cartera_medica.datos_visita_id`):
- `'Mensual'` — visitar 1 vez por mes
- `'Trimestral'` — visitar 1 vez cada 3 meses
- `'Semestral'` — visitar 1 vez cada 6 meses
- `'Anual'` — visitar 1 vez por año
