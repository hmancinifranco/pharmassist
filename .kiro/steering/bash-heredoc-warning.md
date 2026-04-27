---
inclusion: always
---

# Restricciones de Bash en executeBash

## NUNCA usar heredoc
Sintaxis heredoc (`<<`, `<< EOF`, `<< 'EOF'`) causa errores de ejecución.

## NUNCA usar `python3 -c "..."` con código multilínea o f-strings
Mezclar comillas simples, dobles y f-strings dentro de `python3 -c` rompe el terminal con `dquote>`. Esto aplica a CUALQUIER comando inline con strings complejos.

## Alternativa obligatoria para ejecutar código Python de prueba
1. Crear un script temporal con `fsWrite` (ej: `/tmp/test_script.py`)
2. Ejecutar con `executeBash`: `python3 /tmp/test_script.py`
3. Eliminar el script temporal con `deleteFile` si ya no se necesita

## Alternativas generales
- Crear archivos con `fsWrite` y luego ejecutarlos
- Usar `strReplace`, `fsAppend` para modificar archivos
- Múltiples llamadas a `executeBash` en secuencia para comandos simples
