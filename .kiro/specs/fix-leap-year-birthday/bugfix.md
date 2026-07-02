# Bugfix Requirements Document

## Introduction

La función `dias_hasta_cumpleanos` en `backend/utils/birthday_utils.py` (y su copia sincronizada en `agentcore/utils/birthday_utils.py`) crashea con `ValueError` cuando el médico nació un 29 de febrero y el año de referencia no es bisiesto. Esto causa una caída del endpoint `/api/dashboard/birthdays` en producción cuando algún médico del CRM tiene fecha de nacimiento el 29/feb.

El root cause es que `datetime.date.replace(year=X)` con month=2, day=29 lanza `ValueError: day is out of range for month` si el año X no es bisiesto.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN un médico nació el 29 de febrero AND el año de referencia no es bisiesto THEN the system lanza `ValueError: day is out of range for month` al ejecutar `fecha_nacimiento.replace(year=fecha_referencia.year)`

1.2 WHEN un médico nació el 29 de febrero AND el año de referencia + 1 no es bisiesto AND el cumpleaños ya pasó este año THEN the system lanza `ValueError` al ejecutar `fecha_nacimiento.replace(year=fecha_referencia.year + 1)`

1.3 WHEN el endpoint `/api/dashboard/birthdays` procesa la lista de médicos y alguno nació el 29/feb en un año de referencia no bisiesto THEN the system devuelve HTTP 500 en lugar de la lista de cumpleaños próximos

### Expected Behavior (Correct)

2.1 WHEN un médico nació el 29 de febrero AND el año de referencia no es bisiesto THEN the system SHALL usar el 28 de febrero como fecha de cumpleaños para ese año y calcular los días restantes correctamente

2.2 WHEN un médico nació el 29 de febrero AND el año de referencia + 1 no es bisiesto AND el cumpleaños ya pasó este año THEN the system SHALL usar el 28 de febrero del año siguiente como fecha de cumpleaños y calcular los días restantes correctamente

2.3 WHEN un médico nació el 29 de febrero AND el año de referencia es bisiesto THEN the system SHALL usar el 29 de febrero normalmente (sin fallback)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN un médico nació en cualquier fecha que NO sea 29 de febrero THEN the system SHALL CONTINUE TO calcular los días hasta el próximo cumpleaños correctamente

3.2 WHEN el cumpleaños del médico es hoy (días = 0) THEN the system SHALL CONTINUE TO retornar 0

3.3 WHEN el cumpleaños del médico es mañana (días = 1) THEN the system SHALL CONTINUE TO retornar 1

3.4 WHEN la fecha de referencia es en diciembre y el cumpleaños es en enero (wrap de año) THEN the system SHALL CONTINUE TO calcular correctamente los días cruzando el cambio de año

3.5 WHEN se invoca `filtrar_cumpleanos_proximos` con una lista de médicos sin fecha de nacimiento THEN the system SHALL CONTINUE TO omitir esos médicos sin error
