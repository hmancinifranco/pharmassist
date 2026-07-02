# Plan de Implementación: Maestros Integration

## Overview

Implementación del sistema de validación e integración de tablas maestras para PharmAssist. Incluye: column mapping ETL (extensión de `pyspark_helpers.py`), construct CDK para named queries de validación en Athena, scripts SQL de validación/prototipo, y documentación del mapping.

El lenguaje de implementación es **Python** (PySpark para ETL, CDK Python para infraestructura, pytest + hypothesis para tests).

## Tareas

- [x] 1. Implementar Column Mapping ETL
  - [x] 1.1 Agregar `COLUMN_MAPPING` y `apply_column_mapping()` a `pyspark_helpers.py`
    - Agregar el diccionario `COLUMN_MAPPING` con los 3 mappings de tablas maestras
    - Implementar `apply_column_mapping(df, schema_name, table_name)` que renombra columnas según el mapping
    - Implementar la transformación `relacion` → `confianza_match` (exacta=1.00, parcial=0.70, generico=0.40)
    - Columnas sin mapping en destino se descartan; columnas destino sin origen se agregan como NULL
    - Lanzar `ValueError` si una columna fuente del mapping no existe en el DataFrame
    - _Requerimientos: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.10_

  - [x] 1.2 Agregar función `detect_schema_drift()` a `pyspark_helpers.py`
    - Implementar detección de columnas presentes en el schema actual pero ausentes del mapping
    - Implementar detección de columnas presentes en el mapping pero ausentes del schema actual
    - Retornar un dict con `extra_columns` y `missing_columns`
    - _Requerimientos: 10.2, 10.3, 10.4_

  - [x] 1.3 Integrar column mapping en `parquet_to_iceberg.py`
    - Importar `apply_column_mapping` desde `pyspark_helpers`
    - Invocar el mapping para tablas del schema `maestros` antes de escribir en Iceberg
    - Mantener el flujo existente para tablas de otros schemas sin cambios
    - _Requerimientos: 1.1 a 1.7_


  - [ ]* 1.4 Escribir property tests para `apply_column_mapping()`
    - **Property 1: Column mapping preserva valores (round-trip)**
    - Generar DataFrames aleatorios con columnas válidas, aplicar mapping, verificar que valores se preservan
    - **Validates: Requerimientos 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7**
    - Ubicación: `infrastructure/tests/unit/test_pyspark_helpers.py`

  - [ ]* 1.5 Escribir property test para columna fuente faltante
    - **Property 2: Columna fuente faltante produce ValueError**
    - Generar DataFrames con subconjuntos de columnas requeridas removidas, verificar ValueError
    - **Validates: Requerimiento 1.10**
    - Ubicación: `infrastructure/tests/unit/test_pyspark_helpers.py`

  - [ ]* 1.6 Escribir property test para detección de drift
    - **Property 3: Detección de drift de schema es correcta**
    - Generar pares de conjuntos de columnas aleatorios, verificar que la detección identifica correctamente extras y faltantes
    - **Validates: Requerimientos 10.2, 10.3, 10.4**
    - Ubicación: `infrastructure/tests/unit/test_pyspark_helpers.py`

  - [ ]* 1.7 Escribir unit tests para transformación `relacion` → `confianza_match`
    - Test con valores conocidos: 'exacta'→1.00, 'parcial'→0.70, 'generico'→0.40
    - Test con valor inválido (debe manejar gracefully)
    - Test que columnas derivadas se agregan como NULL
    - _Requerimientos: 1.6, 1.7_
    - Ubicación: `infrastructure/tests/unit/test_pyspark_helpers.py`

- [x] 2. Checkpoint — Validar lógica ETL
  - Ejecutar `pytest infrastructure/tests/unit/test_pyspark_helpers.py` y verificar que todos los tests pasan
  - Verificar que `pyspark_helpers.py` importa correctamente desde `parquet_to_iceberg.py`
  - Ensure all tests pass, ask the user if questions arise.


- [x] 3. Implementar Athena Named Queries (CDK)
  - [x] 3.1 Crear construct `MaestrosValidationQueries` en `infrastructure/cdk_constructs/maestros_validation.py`
    - Crear clase `MaestrosValidationQueries(Construct)` con parámetros `workgroup_name` y `glue_databases`
    - Implementar 6 `CfnNamedQuery` resources con prefijo `validacion_maestros_`
    - Queries: cobertura_medicos, cobertura_productos, huerfanos_medicos, huerfanos_productos, constraint_al_menos_un_codigo, duplicados_familia_marca
    - Cada query referencia el workgroup `pharmassist-validation`
    - SQL embebido en cada named query según el diseño
    - _Requerimientos: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.8_

  - [x] 3.2 Integrar construct en `ingestion_stack.py`
    - Importar `MaestrosValidationQueries` desde `cdk_constructs`
    - Instanciar el construct pasando el nombre del workgroup (cross-stack reference o parámetro)
    - Pasar los nombres de las Glue databases como parámetro
    - _Requerimientos: 8.1 a 8.8_

  - [x] 3.3 Verificar `cdk synth` con el nuevo construct
    - Ejecutar `cdk synth --app '.venv/bin/python3 app_ingestion.py'` y verificar que genera template válido
    - Verificar que los 6 `AWS::Athena::NamedQuery` resources aparecen en el template
    - _Requerimientos: 8.1 a 8.8_

  - [ ]* 3.4 Escribir CDK assertion tests para `MaestrosValidationQueries`
    - Verificar que se crean 6 named queries con nombres correctos (prefijo `validacion_maestros_`)
    - Verificar que cada query referencia el workgroup `pharmassist-validation`
    - Verificar que el SQL de cada query no está vacío y contiene SELECT
    - Ubicación: `infrastructure/tests/unit/test_maestros_validation.py`
    - _Requerimientos: 8.1 a 8.8_

- [x] 4. Checkpoint — Validar CDK synth
  - Ejecutar `cdk synth --app '.venv/bin/python3 app_ingestion.py'` exitosamente
  - Ejecutar `pytest infrastructure/tests/unit/test_maestros_validation.py` y verificar que pasan
  - Ensure all tests pass, ask the user if questions arise.


- [x] 5. Crear scripts SQL de validación
  - [x] 5.1 Crear directorio y scripts de integridad referencial
    - Crear `infrastructure/scripts/validation/integridad_maestro_medicos.sql`
    - Crear `infrastructure/scripts/validation/integridad_maestro_productos.sql`
    - Crear `infrastructure/scripts/validation/integridad_familia_marca.sql`
    - SQL según diseño: verificar huérfanos, duplicados, constraints
    - _Requerimientos: 2.1 a 2.8, 3.1 a 3.6, 4.1 a 4.8_

  - [x] 5.2 Crear scripts de validación cross-source
    - Crear `infrastructure/scripts/validation/cross_source_medicos.sql`
    - Crear `infrastructure/scripts/validation/cross_source_productos.sql`
    - Crear `infrastructure/scripts/validation/cross_source_familias.sql`
    - SQL según diseño: joins CRM+CloseUp, CRM+CloseUp+IQVIA, familias+prescripciones
    - _Requerimientos: 5.1 a 5.6, 6.1 a 6.6, 7.1 a 7.5_

  - [x] 5.3 Crear script de queries prototipo (preguntas priorizadas)
    - Crear `infrastructure/scripts/validation/preguntas_prototipo.sql`
    - Incluir las 5 queries prototipo del diseño (preguntas 1, 2, 3, 7, 8)
    - Cada query con comentario indicando la pregunta que responde
    - _Requerimientos: 9.1 a 9.8_


- [x] 6. Crear documentación del mapping de columnas
  - [x] 6.1 Crear `docs/etl-column-mapping-maestros.md`
    - Documentar mapping completo RDS ↔ Glue para las 3 tablas maestras
    - Incluir para cada columna: nombre RDS, tipo RDS, nombre Glue, tipo Glue, tipo de correspondencia
    - Documentar columnas derivadas (NULL en carga inicial) y columnas descartadas
    - Documentar la transformación `relacion` → `confianza_match`
    - _Requerimientos: 10.1, 10.2, 10.3_

- [x] 7. Checkpoint final — Validar todo el spec
  - Ejecutar `pytest infrastructure/tests/unit/` completo (pyspark_helpers + maestros_validation)
  - Ejecutar `cdk synth --app '.venv/bin/python3 app_ingestion.py'` exitosamente
  - Verificar que los 7 archivos SQL existen en `infrastructure/scripts/validation/`
  - Verificar que `docs/etl-column-mapping-maestros.md` existe y tiene las 3 tablas documentadas
  - Ensure all tests pass, ask the user if questions arise.

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requerimientos específicos para trazabilidad
- Los checkpoints aseguran validación incremental
- Los property tests validan propiedades universales de correctitud (hypothesis, 100 iteraciones)
- Los unit tests validan ejemplos específicos y edge cases
- Las queries SQL de validación requieren que el pipeline de ingesta haya corrido al menos 1 vez — no se pueden testear automáticamente sin datos
- El workgroup `pharmassist-validation` ya existe en DataLakeStack — se pasa como parámetro al construct
- El entry point CDK (`app_ingestion.py`) ya existe — no se necesita crear uno nuevo


## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "1.6", "1.7", "3.1"] },
    { "id": 2, "tasks": ["3.2", "5.1", "5.2", "5.3", "6.1"] },
    { "id": 3, "tasks": ["3.3", "3.4"] }
  ]
}
```
