# Documento de Requerimientos — Maestros Integration

## Introducción

Este spec valida las tablas maestras de integración (`maestro_medicos`, `maestro_integrador_producto`, `familia_interno_a_marca_cup`) que permiten joins cross-source entre las 3 fuentes de datos del sistema PharmAssist: CRM interno, CloseUp/CUP e IQVIA. Sin estos maestros, ninguna pregunta que cruce fuentes puede responderse.

El alcance incluye:
- Validación de coherencia de datos en las tablas maestras (integridad referencial)
- Reconciliación del schema entre RDS y Glue Catalog (discrepancia de nombres de columnas)
- Validación de queries cross-source usando maestros como pegamento
- Creación de Athena named queries para validación continua
- Verificación de que los maestros habilitan las 15 preguntas priorizadas del cliente

## Glosario

- **Maestro**: Tabla de integración que mapea identificadores entre fuentes de datos distintas
- **Sistema_Validacion**: Conjunto de Athena named queries y scripts que verifican la coherencia de los maestros
- **ETL_Maestros**: Proceso Glue ETL que transforma datos de RDS (Parquet) a formato Iceberg en el Data Lake
- **Athena_Workgroup**: Workgroup `pharmassist-validation` con límite de 100MB de scan para queries de validación
- **CRM_Interno**: Sistema de gestión de relaciones con médicos del laboratorio (fuente primaria de visitas y cartera)
- **CloseUp_CUP**: Fuente externa de datos de prescripciones médicas
- **IQVIA**: Fuente externa de datos de ventas farmacéuticas
- **Glue_Catalog**: AWS Glue Data Catalog con las tablas Iceberg registradas
- **Cross_Source_Query**: Query SQL en Athena que une datos de 2 o más fuentes via tablas maestras
- **Cobertura_Mapeo**: Porcentaje de registros en una fuente que tienen correspondencia en el maestro


## Requerimientos

### Requerimiento 1: Reconciliación de schema RDS ↔ Glue Catalog

**User Story:** Como ingeniero de datos, quiero que los nombres de columnas entre RDS y Glue Catalog estén alineados, para que el ETL produzca datos consultables sin ambigüedad.

#### Criterios de Aceptación

1. THE ETL_Maestros SHALL mapear la columna `cod_interno` de RDS a `doctor_id_crm` en Glue Catalog para la tabla `maestro_medicos`, preservando el tipo de dato original de la columna fuente
2. THE ETL_Maestros SHALL mapear la columna `cod_closeup` de RDS a `cdgmedico_cup` en Glue Catalog para la tabla `maestro_medicos`, preservando el tipo de dato original de la columna fuente
3. THE ETL_Maestros SHALL mapear la columna `cod_interno` de RDS a `producto_id_crm` en Glue Catalog para la tabla `maestro_integrador_producto`, preservando el tipo de dato original de la columna fuente
4. THE ETL_Maestros SHALL mapear la columna `cod_closeup` de RDS a `cdgmarca_cup` en Glue Catalog para la tabla `maestro_integrador_producto`, preservando el tipo de dato original de la columna fuente
5. THE ETL_Maestros SHALL mapear la columna `cod_iqvia` de RDS a `idpresentacion_iqvia` en Glue Catalog para la tabla `maestro_integrador_producto`, preservando el tipo de dato original de la columna fuente
6. THE ETL_Maestros SHALL mapear la columna `cod_interno` de RDS a `familia_producto_id` en Glue Catalog para la tabla `familia_interno_a_marca_cup`, preservando el tipo de dato original de la columna fuente
7. THE ETL_Maestros SHALL mapear la columna `codigo_marca` de RDS a `cdgmarca_cup` en Glue Catalog para la tabla `familia_interno_a_marca_cup`, preservando el tipo de dato original de la columna fuente
8. WHEN el ETL completa la carga exitosa de una tabla maestro, THE Sistema_Validacion SHALL verificar que cada columna mapeada (criterios 1-7) contiene datos no nulos en al menos un registro, dentro de los 60 segundos posteriores a la finalización del job
9. IF la validación post-carga detecta que una columna mapeada tiene valores nulos en todos los registros, THEN THE Sistema_Validacion SHALL registrar una alerta indicando el nombre de la tabla, el nombre de la columna afectada y la cantidad total de registros procesados
10. IF una columna fuente especificada en los criterios 1-7 no existe en la tabla RDS de origen, THEN THE ETL_Maestros SHALL fallar el job de carga para esa tabla y registrar un error indicando la tabla y la columna faltante


### Requerimiento 2: Integridad referencial del maestro de médicos

**User Story:** Como analista de datos, quiero validar que el maestro de médicos tiene mapeos coherentes entre CRM y CloseUp, para que los joins cross-source produzcan resultados correctos.

#### Criterios de Aceptación

1. THE Sistema_Validacion SHALL verificar que cada registro en `maestro_medicos` tiene al menos uno de los campos `doctor_id_crm` o `cdgmedico_cup` con valor no nulo, y SHALL reportar la cantidad de registros que violan esta regla
2. THE Sistema_Validacion SHALL verificar que no existen valores duplicados en `doctor_id_crm` dentro de `maestro_medicos` (excluyendo nulos), y SHALL reportar la cantidad de valores duplicados encontrados
3. THE Sistema_Validacion SHALL verificar que no existen valores duplicados en `cdgmedico_cup` dentro de `maestro_medicos` (excluyendo nulos), y SHALL reportar la cantidad de valores duplicados encontrados
4. WHEN un registro tiene `doctor_id_crm` no nulo, THE Sistema_Validacion SHALL verificar que ese ID existe en la tabla `doctor` del schema CRM interno, y SHALL reportar la cantidad de IDs huérfanos (sin correspondencia en la tabla origen)
5. WHEN un registro tiene `cdgmedico_cup` no nulo, THE Sistema_Validacion SHALL verificar que ese código existe en la tabla de médicos del schema CloseUp, y SHALL reportar la cantidad de códigos huérfanos (sin correspondencia en la tabla origen)
6. THE Sistema_Validacion SHALL calcular la Cobertura_Mapeo como el porcentaje de médicos activos en la tabla `doctor` del CRM que tienen una correspondencia válida (no nula) en `cdgmedico_cup` dentro de `maestro_medicos`, y SHALL reportar este valor como un porcentaje con 2 decimales
7. THE Sistema_Validacion SHALL reportar la cantidad de registros en `maestro_medicos` con nivel de confianza `alta`, `media` y `baja` respectivamente, donde el nivel de confianza corresponde al campo `confianza` de la tabla
8. IF alguna de las validaciones de los criterios 1 a 5 detecta al menos 1 registro con violación, THEN THE Sistema_Validacion SHALL marcar la validación de integridad referencial como fallida e incluir en el reporte el detalle de cada tipo de violación con la cantidad de registros afectados


### Requerimiento 3: Integridad referencial del maestro integrador de productos

**User Story:** Como analista de datos, quiero validar que el maestro integrador de productos mapea correctamente entre CRM, CloseUp e IQVIA, para que las queries de prescripciones y ventas crucen datos sin pérdida.

#### Criterios de Aceptación

1. THE Sistema_Validacion SHALL verificar que cada registro en `maestro_integrador_producto` cumple la constraint `al_menos_un_codigo` (al menos uno de `producto_id_crm`, `cdgmarca_cup` o `idpresentacion_iqvia` es no nulo) y reportar la cantidad de registros que violan esta constraint
2. THE Sistema_Validacion SHALL reportar la cantidad de productos que tienen los 3 códigos mapeados (cobertura completa), la cantidad sin `cdgmarca_cup` (sin datos de prescripciones) y la cantidad sin `idpresentacion_iqvia` (sin datos de ventas)
3. WHEN un producto tiene `producto_id_crm` no nulo, THE Sistema_Validacion SHALL verificar que ese código existe en la tabla `familia_producto` del schema CRM y reportar la cantidad de códigos huérfanos que no tienen correspondencia
4. WHEN un producto tiene `cdgmarca_cup` no nulo, THE Sistema_Validacion SHALL verificar que ese código existe en la tabla de marcas del schema CloseUp y reportar la cantidad de códigos huérfanos que no tienen correspondencia
5. WHEN un producto tiene `idpresentacion_iqvia` no nulo, THE Sistema_Validacion SHALL verificar que ese código existe en la tabla `dim_presentacion` del schema IQVIA y reportar la cantidad de códigos huérfanos que no tienen correspondencia
6. IF la cantidad de códigos huérfanos en cualquiera de las verificaciones referenciales (criterios 3, 4 o 5) es mayor a 0, THEN THE Sistema_Validacion SHALL reportar el resultado como validación fallida indicando la fuente afectada y la cantidad de registros sin correspondencia


### Requerimiento 4: Integridad referencial de familia interna a marca CloseUp

**User Story:** Como analista de datos, quiero validar que el mapeo de familias internas a marcas CloseUp es coherente y respeta la relación N:M, para que las queries de productos foco crucen correctamente con prescripciones.

#### Criterios de Aceptación

1. THE Sistema_Validacion SHALL verificar que cada registro en `familia_interno_a_marca_cup` tiene `familia_producto_id` y `cdgmarca_cup` con valores no nulos
2. THE Sistema_Validacion SHALL reportar la cantidad de familias internas distintas (por `familia_producto_id`) que tienen al menos un mapeo a marca CloseUp
3. THE Sistema_Validacion SHALL reportar la cantidad de familias internas presentes en la tabla de familias de producto del CRM que no tienen ningún registro en `familia_interno_a_marca_cup` (huérfanas), comparando contra el universo completo de familias activas en `crm_interno.familia_producto`
4. THE Sistema_Validacion SHALL verificar que el campo `relacion` contiene únicamente valores válidos: `exacta`, `parcial` o `generico`
5. WHEN una familia tiene múltiples mapeos a la misma marca CloseUp (mismo par `familia_producto_id` + `cdgmarca_cup`), THE Sistema_Validacion SHALL reportar la cantidad de pares duplicados y listar los `familia_producto_id` afectados
6. THE Sistema_Validacion SHALL reportar la distribución de tipos de relación (cantidad de mapeos `exacta`, `parcial`, `generico`) y el porcentaje que cada tipo representa sobre el total de registros
7. THE Sistema_Validacion SHALL verificar que cada `familia_producto_id` en `familia_interno_a_marca_cup` existe como registro válido en la tabla de familias de producto del CRM, y reportar la cantidad de IDs sin correspondencia en la fuente
8. THE Sistema_Validacion SHALL verificar que cada `cdgmarca_cup` en `familia_interno_a_marca_cup` existe como registro válido en la tabla de marcas de CloseUp, y reportar la cantidad de códigos sin correspondencia en la fuente


### Requerimiento 5: Queries cross-source médicos (CRM + CloseUp via maestro_medicos)

**User Story:** Como analista de datos, quiero ejecutar queries que crucen datos de visitas del CRM con prescripciones de CloseUp usando el maestro de médicos, para validar que el join funciona correctamente.

#### Criterios de Aceptación

1. WHEN se ejecuta un Cross_Source_Query uniendo CRM con CloseUp via `maestro_medicos`, THE Athena_Workgroup SHALL retornar resultados en menos de 30 segundos
2. THE Sistema_Validacion SHALL ejecutar una query que liste médicos visitados por el APM en los últimos 12 meses junto con su volumen de prescripciones en CloseUp para el mismo período, retornando al menos 1 registro
3. THE Sistema_Validacion SHALL verificar que el join entre `maestro_medicos.doctor_id_crm` y la tabla de doctores del CRM produce cero registros huérfanos (filas en `maestro_medicos` sin correspondencia en la tabla de doctores del CRM)
4. THE Sistema_Validacion SHALL verificar que el join entre `maestro_medicos.cdgmedico_cup` y la tabla de prescripciones de CloseUp produce al menos un resultado para cada médico con mapeo de confianza `alta` en `maestro_medicos`
5. IF un Cross_Source_Query excede el límite de 100MB de scan del Athena_Workgroup, THEN THE Sistema_Validacion SHALL reportar el query como candidato a optimización con particionado o filtros adicionales
6. IF el Cross_Source_Query retorna cero resultados cuando existen registros en `maestro_medicos` con confianza `alta`, THEN THE Sistema_Validacion SHALL reportar el resultado como fallo de integridad indicando las tablas involucradas y la condición de join utilizada


### Requerimiento 6: Queries cross-source productos (CRM + CloseUp + IQVIA via maestro_integrador_producto)

**User Story:** Como analista de datos, quiero ejecutar queries que crucen datos de productos del CRM con prescripciones de CloseUp y ventas de IQVIA usando el maestro integrador, para validar que el join triple funciona correctamente.

#### Criterios de Aceptación

1. WHEN se ejecuta un Cross_Source_Query uniendo `crm_interno.familia_producto` con `closeup.prescripcion` via `maestro_integrador_producto.cod_interno` = `familia_producto.codigo` y `maestro_integrador_producto.cod_closeup` = `prescripcion.CDGPRO`, THE Athena_Workgroup SHALL retornar al menos 1 fila que incluya el nombre del producto (`familia_producto.nombre`) y la suma de unidades prescritas (`prescripcion.cantidad`) en un tiempo no mayor a 60 segundos
2. WHEN se ejecuta un Cross_Source_Query uniendo `crm_interno.familia_producto` con `iqvia.fact_mercado_valor` via `maestro_integrador_producto.cod_interno` = `familia_producto.codigo` y `maestro_integrador_producto.cod_iqvia` = `fact_mercado_valor.idProducto`, THE Athena_Workgroup SHALL retornar al menos 1 fila que incluya el nombre del producto (`familia_producto.nombre`) y la suma de unidades vendidas (`fact_mercado_valor.unidades`) en un tiempo no mayor a 60 segundos
3. WHEN se ejecuta un Cross_Source_Query uniendo las 3 fuentes (CRM + CloseUp + IQVIA) para un producto que tiene los 3 códigos poblados en `maestro_integrador_producto` (`cod_interno` IS NOT NULL AND `cod_closeup` IS NOT NULL AND `cod_iqvia` IS NOT NULL), THE Athena_Workgroup SHALL retornar al menos 1 fila que incluya nombre del producto, suma de prescripciones y suma de ventas en un tiempo no mayor a 90 segundos
4. WHEN se ejecuta un Cross_Source_Query con LEFT JOIN desde `maestro_integrador_producto` hacia `closeup.prescripcion` para productos donde `maestro_integrador_producto.cod_closeup` IS NULL, THE Athena_Workgroup SHALL retornar 0 filas con datos de prescripciones (columnas de CloseUp en NULL) para esos productos
5. WHEN se ejecuta un Cross_Source_Query con LEFT JOIN desde `maestro_integrador_producto` hacia `iqvia.fact_mercado_valor` para productos donde `maestro_integrador_producto.cod_iqvia` IS NULL, THE Athena_Workgroup SHALL retornar 0 filas con datos de ventas (columnas de IQVIA en NULL) para esos productos
6. IF el Cross_Source_Query de 3 fuentes no retorna filas, THEN THE Sistema_Validacion SHALL reportar un error indicando que no existen productos con cobertura completa de códigos en `maestro_integrador_producto`


### Requerimiento 7: Queries cross-source familias (CRM + CloseUp via familia_interno_a_marca_cup)

**User Story:** Como analista de datos, quiero ejecutar queries que crucen familias de productos internas con marcas de CloseUp, para validar que los productos foco del APM se pueden cruzar con datos de prescripciones.

#### Criterios de Aceptación

1. WHEN se ejecuta un Cross_Source_Query usando `familia_interno_a_marca_cup`, THE Sistema_Validacion SHALL aplicar DISTINCT sobre `codigo_marca` antes de usar el listado de códigos en el join con CloseUp, evitando duplicados cuando múltiples familias internas mapean a la misma marca CUP
2. THE Sistema_Validacion SHALL ejecutar una query que liste cada familia interna (`cod_interno`, nombre) con la suma de `cantidad` de prescripciones agregada desde `closeup.prescripcion` para los últimos 12 meses, usando `familia_interno_a_marca_cup` como tabla de cruce
3. THE Sistema_Validacion SHALL verificar que familias con relación `exacta` producen menor cantidad promedio de marcas CUP por familia (ratio 1:1 o cercano) que familias con relación `parcial` o `generico`, comparando el promedio de `codigo_marca` distintos por `cod_interno` en cada grupo de relación
4. IF una familia interna presente en `crm_interno.familia_producto` no tiene ningún registro en `familia_interno_a_marca_cup`, THEN THE Sistema_Validacion SHALL incluirla en un listado de familias sin cobertura que contenga `cod_interno`, nombre de la familia, y `linea_id` asociada
5. IF una familia interna tiene mapeos en `familia_interno_a_marca_cup` pero ninguno de sus `codigo_marca` asociados aparece en `closeup.prescripcion` en los últimos 12 meses, THEN THE Sistema_Validacion SHALL reportar esa familia como con mapeo sin actividad de prescripciones


### Requerimiento 8: Athena named queries de validación continua

**User Story:** Como ingeniero de datos, quiero tener named queries en Athena que pueda ejecutar periódicamente para detectar degradación en la calidad de los maestros, para mantener la confiabilidad de las queries cross-source.

#### Criterios de Aceptación

1. THE Sistema_Validacion SHALL crear una Athena named query en el workgroup `pharmassist-validation` que retorne el total de médicos en `crm_interno.doctor`, el total con mapeo en `maestros.maestro_medicos` (donde `cod_closeup` IS NOT NULL), y el porcentaje de cobertura resultante
2. THE Sistema_Validacion SHALL crear una Athena named query en el workgroup `pharmassist-validation` que retorne la distribución de registros en `maestros.maestro_integrador_producto` agrupados por cantidad de códigos presentes (3 códigos no nulos, exactamente 2, exactamente 1), incluyendo el conteo y porcentaje de cada grupo
3. THE Sistema_Validacion SHALL crear una Athena named query en el workgroup `pharmassist-validation` que detecte registros huérfanos en `maestros.maestro_medicos` (valores de `cod_interno` que no existen en `crm_interno.doctor.id` y valores de `cod_closeup` que no existen en `closeup.medico.CDGMED`)
4. THE Sistema_Validacion SHALL crear una Athena named query en el workgroup `pharmassist-validation` que detecte registros huérfanos en `maestros.maestro_integrador_producto` (valores de `cod_interno` que no existen en `crm_interno.familia_producto.codigo`, valores de `cod_closeup` que no existen en `closeup.marca.codigo_marca`, y valores de `cod_iqvia` que no existen en `iqvia.dim_presentacion.idProducto`)
5. THE Sistema_Validacion SHALL crear una Athena named query en el workgroup `pharmassist-validation` que retorne los registros de `maestros.maestro_integrador_producto` donde `cod_interno` IS NULL AND `cod_closeup` IS NULL AND `cod_iqvia` IS NULL, validando la constraint `al_menos_un_codigo`
6. THE Sistema_Validacion SHALL crear una Athena named query en el workgroup `pharmassist-validation` que retorne los pares (`cod_interno`, `codigo_marca`) que aparecen más de una vez en `maestros.familia_interno_a_marca_cup`, incluyendo el conteo de ocurrencias por par duplicado
7. WHEN se ejecutan las named queries de validación, THE Athena_Workgroup `pharmassist-validation` SHALL completar cada query escaneando un máximo de 100MB de datos
8. THE Sistema_Validacion SHALL nombrar cada named query con el prefijo `validacion_maestros_` seguido de un sufijo descriptivo (por ejemplo: `cobertura_medicos`, `cobertura_productos`, `huerfanos_medicos`, `huerfanos_productos`, `constraint_al_menos_un_codigo`, `duplicados_familia_marca`)


### Requerimiento 9: Habilitación de preguntas priorizadas del cliente

**User Story:** Como product owner, quiero verificar que los maestros habilitan las 7 preguntas de alta y media prioridad que requieren cross-source joins, para confirmar que el data lake puede responder las necesidades del negocio.

#### Criterios de Aceptación

1. WHEN se ejecuta la query prototipo para la pregunta 1 ("Recomendar médicos según prescripciones y productos foco") usando `maestro_medicos` + `familia_interno_a_marca_cup`, THE Sistema_Validacion SHALL retornar al menos 1 fila con claves de join no nulas entre las tablas cruzadas en un tiempo máximo de 60 segundos
2. WHEN se ejecuta la query prototipo para la pregunta 2 ("Médicos creciendo en foco que visito poco") usando `maestro_medicos` + `familia_interno_a_marca_cup`, THE Sistema_Validacion SHALL retornar al menos 1 fila con claves de join no nulas entre las tablas cruzadas en un tiempo máximo de 60 segundos
3. WHEN se ejecuta la query prototipo para la pregunta 3 ("Médicos a visitar para crecer con producto X") usando `maestro_medicos` + `maestro_integrador_producto`, THE Sistema_Validacion SHALL retornar al menos 1 fila con claves de join no nulas entre las tablas cruzadas en un tiempo máximo de 60 segundos
4. WHEN se ejecuta la query prototipo para la pregunta 7 ("Medicamentos que NO promociono y más prescribe Dr. X") usando `maestro_medicos` + `maestro_integrador_producto`, THE Sistema_Validacion SHALL retornar al menos 1 fila con claves de join no nulas entre las tablas cruzadas en un tiempo máximo de 60 segundos
5. WHEN se ejecuta la query prototipo para la pregunta 8 ("Medicamentos que SÍ promociono y más prescribe Dr. X") usando `maestro_medicos` + `maestro_integrador_producto`, THE Sistema_Validacion SHALL retornar al menos 1 fila con claves de join no nulas entre las tablas cruzadas en un tiempo máximo de 60 segundos
6. IF una query prototipo retorna 0 filas o falla por ausencia de mapeo en una tabla maestra, THEN THE Sistema_Validacion SHALL reportar el nombre de la tabla maestra involucrada, la columna de join sin correspondencia y la cantidad de claves huérfanas detectadas
7. THE Sistema_Validacion SHALL generar un artefacto de documentación por cada pregunta priorizada que incluya: las tablas maestras utilizadas, las columnas de join entre cada par de tablas y el orden de ejecución de los joins (de tabla origen a tabla destino)
8. IF una query prototipo excede los 60 segundos de ejecución sin retornar resultados, THEN THE Sistema_Validacion SHALL reportar la query como fallida indicando el tiempo transcurrido y la etapa del join donde se produjo el timeout


### Requerimiento 10: Documentación del mapping de columnas ETL

**User Story:** Como ingeniero de datos, quiero tener documentado el mapping exacto entre columnas RDS y columnas Glue para cada tabla maestra, para que futuros cambios en el schema no rompan el pipeline silenciosamente.

#### Criterios de Aceptación

1. THE Sistema_Validacion SHALL generar un documento de mapping para cada una de las 3 tablas maestras (maestro_medicos, maestro_integrador_producto, familia_interno_a_marca_cup) que liste cada columna RDS con su correspondiente columna Glue, incluyendo para cada entrada: nombre de columna en RDS, tipo de dato en RDS, nombre de columna en Glue, tipo de dato en Glue, y tipo de correspondencia (directa, renombrada, o transformada)
2. THE Sistema_Validacion SHALL identificar columnas presentes en Glue que no existen con el mismo nombre ni como resultado de una transformación documentada en el mapping de la tabla correspondiente en RDS, clasificándolas como columnas derivadas o enriquecidas
3. THE Sistema_Validacion SHALL identificar columnas presentes en RDS que no aparecen en el mapping como origen de ninguna columna Glue, clasificándolas como columnas descartadas en el ETL
4. WHEN el schema actual de RDS o de Glue contiene columnas que no están registradas en el documento de mapping vigente, THE Sistema_Validacion SHALL reportar cada columna no registrada como error de configuración, indicando la tabla afectada, el nombre de la columna, y el lado donde fue detectada (RDS o Glue)
5. WHEN se actualiza el mapping para reflejar un cambio de schema intencional, THE Sistema_Validacion SHALL registrar la fecha de actualización y dejar de reportar como error las columnas que fueron incorporadas al mapping
