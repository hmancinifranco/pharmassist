# ETL Column Mapping — Tablas Maestras

## Descripción

Este documento define el mapping completo de columnas entre las tablas maestras en **RDS PostgreSQL** (fuente) y **AWS Glue Data Catalog** (destino, formato Iceberg). El ETL (`parquet_to_iceberg.py`) aplica estas transformaciones durante la carga.

### Convenciones

| Tipo de correspondencia | Descripción |
|---|---|
| **directa** | Misma columna, mismo nombre, mismo tipo |
| **renombrada** | Cambio de nombre, mismo tipo |
| **renombrada + cast** | Cambio de nombre y conversión de tipo |
| **transformada** | Cambio de nombre + lógica de transformación de valores |
| **descartada** | Columna RDS que no se carga en Glue |
| **derivada (NULL)** | Columna Glue sin origen en RDS — se carga como NULL en carga inicial |
| **derivada (default)** | Columna Glue sin origen en RDS — se carga con valor por defecto |

---

## 1. `maestro_medicos`

**Schema RDS:** `maestros.maestro_medicos`  
**Tabla Glue:** `pharmassist_maestros.maestro_medicos`

### Columnas mapeadas (RDS → Glue)

| Columna RDS | Tipo RDS | Columna Glue | Tipo Glue | Correspondencia |
|---|---|---|---|---|
| `id` | SERIAL | `id` | int | directa |
| `cod_interno` | INTEGER | `doctor_id_crm` | int | renombrada |
| `cod_closeup` | VARCHAR(20) | `cdgmedico_cup` | int | renombrada + cast |
| `nombre_verificado` | VARCHAR(200) | `nombre` | string | renombrada |
| `fecha_mapeo` | DATE | `fecha_actualizacion` | timestamp | renombrada + cast |

### Columnas descartadas (presentes en RDS, no se cargan en Glue)

| Columna RDS | Tipo RDS | Motivo |
|---|---|---|
| `confianza` | VARCHAR(20) | No requerida en el modelo analítico |

### Columnas derivadas (presentes en Glue, sin origen en RDS)

| Columna Glue | Tipo Glue | Valor en carga inicial |
|---|---|---|
| `apellido` | string | NULL |
| `matricula_nacional` | string | NULL |
| `especialidad` | string | NULL |
| `zona` | string | NULL |
| `localidad` | string | NULL |
| `provincia` | string | NULL |
| `fuente_primaria` | string | NULL |
| `activo` | boolean | TRUE (default) |

> **Nota:** Las columnas derivadas se poblarán en un paso posterior de enriquecimiento (fuera de scope de la carga inicial ETL).

---

## 2. `maestro_integrador_producto`

**Schema RDS:** `maestros.maestro_integrador_producto`  
**Tabla Glue:** `pharmassist_maestros.maestro_integrador_producto`

### Columnas mapeadas (RDS → Glue)

| Columna RDS | Tipo RDS | Columna Glue | Tipo Glue | Correspondencia |
|---|---|---|---|---|
| `id` | SERIAL | `id` | int | directa |
| `cod_interno` | VARCHAR(30) | `producto_id_crm` | int | renombrada + cast |
| `cod_closeup` | VARCHAR(20) | `cdgmarca_cup` | int | renombrada + cast |
| `cod_iqvia` | VARCHAR(20) | `idpresentacion_iqvia` | int | renombrada + cast |
| `nombre_unificado` | VARCHAR(300) | `nombre_interno` | string | renombrada |
| `fecha_mapeo` | DATE | `fecha_actualizacion` | timestamp | renombrada + cast |

### Columnas descartadas (presentes en RDS, no se cargan en Glue)

| Columna RDS | Tipo RDS | Motivo |
|---|---|---|
| `principio_activo` | VARCHAR(200) | Disponible en fuentes externas (IQVIA) |
| `codigo_barras_ean11` | VARCHAR(20) | No requerido en el modelo analítico |

### Columnas derivadas (presentes en Glue, sin origen en RDS)

| Columna Glue | Tipo Glue | Valor en carga inicial |
|---|---|---|
| `nombre_iqvia` | string | NULL |
| `nombre_cup` | string | NULL |
| `familia` | string | NULL |
| `linea` | string | NULL |
| `activo` | boolean | TRUE (default) |

> **Nota:** Las columnas derivadas se poblarán en un paso posterior de enriquecimiento (fuera de scope de la carga inicial ETL).

---

## 3. `familia_interno_a_marca_cup`

**Schema RDS:** `maestros.familia_interno_a_marca_cup`  
**Tabla Glue:** `pharmassist_maestros.familia_interno_a_marca_cup`

### Columnas mapeadas (RDS → Glue)

| Columna RDS | Tipo RDS | Columna Glue | Tipo Glue | Correspondencia |
|---|---|---|---|---|
| `id` | SERIAL | `id` | int | directa |
| `cod_interno` | VARCHAR(30) | `familia_producto_id` | int | renombrada + cast |
| `codigo_marca` | VARCHAR(20) | `cdgmarca_cup` | int | renombrada + cast |
| `relacion` | VARCHAR(50) | `confianza_match` | decimal(3,2) | transformada |

### Columnas derivadas (presentes en Glue, sin origen en RDS)

| Columna Glue | Tipo Glue | Valor en carga inicial |
|---|---|---|
| `nombre_familia` | string | NULL |
| `nombre_marca_cup` | string | NULL |
| `fecha_mapeo` | date | NULL |
| `activo` | boolean | TRUE (default) |

> **Nota:** Las columnas derivadas se poblarán en un paso posterior de enriquecimiento (fuera de scope de la carga inicial ETL).

---

## Transformación: `relacion` → `confianza_match`

La columna `relacion` en RDS contiene valores categóricos de texto que representan el nivel de confianza del mapeo entre una familia de producto interna y una marca CloseUp/CUP. En Glue, se transforma a un valor numérico `decimal(3,2)` que facilita filtrado y ordenamiento.

### Tabla de conversión

| Valor RDS (`relacion`) | Valor Glue (`confianza_match`) | Significado |
|---|---|---|
| `'exacta'` | `1.00` | Match exacto — misma presentación |
| `'parcial'` | `0.70` | Match parcial — misma molécula, diferente presentación |
| `'generico'` | `0.40` | Match genérico — misma categoría terapéutica |

### Reglas de transformación

- La comparación del valor fuente es **case-insensitive** (se normaliza a minúsculas antes del mapeo).
- Si el valor de `relacion` no coincide con ninguno de los 3 valores documentados, se escribe `NULL` en `confianza_match` y se registra un warning en el log del job ETL.
- El tipo destino `decimal(3,2)` permite valores entre `0.00` y `9.99`, pero los valores válidos del negocio están acotados a `{0.40, 0.70, 1.00}`.

---

## Notas generales

1. **Columnas descartadas** no generan error — simplemente se omiten del DataFrame destino durante el ETL.
2. **Columnas derivadas** se agregan al DataFrame con valor NULL (o default TRUE para `activo`) antes de escribir en Iceberg.
3. Si una columna fuente definida en el mapping **no existe** en el DataFrame de entrada, el job ETL falla con `ValueError` indicando la tabla y columna faltante (ver Requerimiento 1.10).
4. La validación post-carga verifica que las columnas mapeadas contengan al menos un valor no nulo (ver Requerimiento 1.8).
5. Este documento es la fuente de verdad para la detección de drift de schema (ver Requerimiento 10.4).
