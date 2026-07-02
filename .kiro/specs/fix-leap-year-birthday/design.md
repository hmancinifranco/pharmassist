# Fix Leap Year Birthday — Bugfix Design

## Overview

La función `dias_hasta_cumpleanos` crashea con `ValueError` cuando `fecha_nacimiento` es 29 de febrero y el año destino del `replace()` no es bisiesto. El fix consiste en envolver las llamadas a `date.replace()` en un `try/except ValueError`, usando el 28 de febrero como fallback cuando el 29 no existe en el año destino.

El fix es mínimo y localizado: solo modifica la función `dias_hasta_cumpleanos` en dos archivos sincronizados.

## Glossary

- **Bug_Condition (C)**: `fecha_nacimiento.month == 2 AND fecha_nacimiento.day == 29 AND NOT is_leap_year(target_year)`
- **Property (P)**: La función retorna los días hasta el 28 de febrero del año destino sin lanzar excepción
- **Preservation**: Para cualquier fecha de nacimiento que NO sea 29/feb, el comportamiento es idéntico al código original
- **`dias_hasta_cumpleanos`**: Función en `backend/utils/birthday_utils.py` que calcula días hasta el próximo cumpleaños
- **`filtrar_cumpleanos_proximos`**: Función que usa `dias_hasta_cumpleanos` para filtrar médicos con cumpleaños próximos


## Bug Details

### Bug Condition

El bug se manifiesta cuando `dias_hasta_cumpleanos` recibe una fecha de nacimiento del 29 de febrero y el año de referencia (o el año siguiente) no es bisiesto. La llamada `fecha_nacimiento.replace(year=target_year)` lanza `ValueError` porque el día 29 no existe en febrero de un año no bisiesto.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type (fecha_nacimiento: date, fecha_referencia: date)
  OUTPUT: boolean
  
  RETURN fecha_nacimiento.month = 2
         AND fecha_nacimiento.day = 29
         AND (NOT is_leap_year(fecha_referencia.year)
              OR (cumple_ya_paso AND NOT is_leap_year(fecha_referencia.year + 1)))
END FUNCTION
```

### Examples

- `dias_hasta_cumpleanos(date(2000, 2, 29), date(2023, 1, 15))` → Crashea con `ValueError` (2023 no es bisiesto)
- `dias_hasta_cumpleanos(date(2000, 2, 29), date(2023, 3, 1))` → Crashea con `ValueError` (2024 es bisiesto, pero intenta 2023 primero — en realidad 2024 sí es bisiesto, así que el replace del año siguiente funciona; el crash ocurre en el replace del año actual)
- `dias_hasta_cumpleanos(date(2000, 2, 29), date(2025, 3, 1))` → Crashea con `ValueError` (cumpleaños ya pasó, intenta 2026 que no es bisiesto)
- `dias_hasta_cumpleanos(date(2000, 2, 29), date(2024, 1, 15))` → Funciona correctamente (2024 es bisiesto, retorna 45)
