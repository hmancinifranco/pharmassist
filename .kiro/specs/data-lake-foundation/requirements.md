# Requirements — data-lake-foundation

## Overview

Crear la infraestructura fundacional del data lake de PharmAssist: bucket S3 con estructura de prefijos por dominio, Glue Data Catalog con databases y definiciones de tablas Iceberg, y un Athena Workgroup básico para validación. Todo provisionado como CDK stack independiente (`DataLakeStack`).

## Glossary

- **DataLakeStack**: Stack CDK que contiene toda la infraestructura del data lake (S3, Glue, Athena, IAM)
- **Lake_Bucket**: Bucket S3 `pharmassist-lake` que almacena los datos del data lake en formato Iceberg
- **Glue_Catalog**: AWS Glue Data Catalog — metastore central que describe tablas, schemas y particiones
- **Glue_Database**: Base de datos lógica dentro del Glue Catalog que agrupa tablas de un dominio
- **Iceberg_Table**: Tabla Apache Iceberg registrada en Glue Catalog con formato Parquet subyacente
- **Athena_Workgroup**: Grupo de trabajo de Amazon Athena con configuración de resultado y límites de costo
- **Dominio**: Cada una de las 4 fuentes de datos: CRM (crm), CloseUp (cup), IQVIA (iqvia), Maestros (maestros)
- **Partition_Key**: Columna usada para particionar datos físicamente en S3, habilitando partition pruning
- **CDK_Aspect**: Mecanismo de CDK para aplicar transformaciones transversales (ej: tags) a todos los recursos

## Requirements

### Requirement 1: Bucket S3 del Data Lake

**User Story:** Como ingeniero de datos que construye el pipeline de ingesta,
quiero un bucket S3 con estructura de prefijos por dominio y configuración de seguridad,
para almacenar los datos del data lake de forma organizada, encriptada y con control de costos.

#### Acceptance Criteria

1. THE DataLakeStack SHALL crear un bucket S3 con nombre lógico generado por CDK y prefijo `pharmassist-lake`
2. THE Lake_Bucket SHALL tener encriptación server-side habilitada con SSE-S3 como algoritmo mínimo (AES-256)
3. THE Lake_Bucket SHALL tener versionado habilitado para proteger contra borrados accidentales
4. THE Lake_Bucket SHALL bloquear todo acceso público configurando las 4 opciones de Block Public Access en true (BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets)
5. THE Lake_Bucket SHALL tener una lifecycle rule que mueva objetos con tag `lifecycle=archive` a la clase de almacenamiento Glacier Flexible Retrieval después de 365 días
6. THE Lake_Bucket SHALL tener una lifecycle rule que elimine versiones no-current después de 90 días
7. THE Lake_Bucket SHALL tener una lifecycle rule que aborte multipart uploads incompletos después de 7 días
8. THE Lake_Bucket SHALL tener definidos los prefijos `crm/`, `cup/`, `iqvia/`, `maestros/` como parte de la estructura del bucket, verificables en el template CloudFormation o mediante la existencia de objetos placeholder en cada prefijo
9. THE DataLakeStack SHALL aplicar tags a todos los recursos via CDK Aspects con las claves Project, Environment y Owner, donde los valores se reciben como parámetros del stack
10. IF el entorno configurado es desarrollo, THEN THE Lake_Bucket SHALL tener removal policy DESTROY y auto_delete_objects habilitado para permitir la eliminación completa del bucket durante `cdk destroy`

### Requirement 2: Glue Data Catalog — Databases por Dominio

**User Story:** Como motor de consulta (Athena, Glue ETL) que necesita descubrir tablas,
quiero databases registradas en Glue Data Catalog para cada dominio del data lake,
para tener un metastore centralizado que sirva como fuente de verdad del schema.

#### Acceptance Criteria

1. THE DataLakeStack SHALL crear una Glue Database llamada `pharmassist_crm` para el dominio CRM
2. THE DataLakeStack SHALL crear una Glue Database llamada `pharmassist_cup` para el dominio CloseUp
3. THE DataLakeStack SHALL crear una Glue Database llamada `pharmassist_iqvia` para el dominio IQVIA
4. THE DataLakeStack SHALL crear una Glue Database llamada `pharmassist_maestros` para el dominio Maestros
5. WHEN se crea una Glue Database, THE DataLakeStack SHALL configurar la location URI con el formato `s3://{lake_bucket}/{domain_prefix}/` donde domain_prefix es `crm` para pharmassist_crm, `cup` para pharmassist_cup, `iqvia` para pharmassist_iqvia, y `maestros` para pharmassist_maestros
6. THE Glue_Catalog SHALL registrar cada database con una descripción que contenga el nombre de la fuente de datos del dominio y su cadencia de actualización esperada (por ejemplo: "Fuente: CRM interno | Cadencia: diaria")
7. THE DataLakeStack SHALL configurar cada Glue Database con el catalog_id correspondiente a la cuenta AWS del stack, de modo que las databases queden registradas en el Glue Data Catalog por defecto de la región

### Requirement 3: Tablas Iceberg — Dominio CRM

**User Story:** Como pipeline DMS que va a replicar datos del CRM interno,
quiero definiciones de tablas Iceberg en Glue Catalog que reflejen el schema del RDS,
para que los datos replicados sean queryeables inmediatamente por Athena.

#### Acceptance Criteria

1. THE DataLakeStack SHALL crear definiciones de tabla Iceberg en `pharmassist_crm` para las 25 tablas del schema `crm_interno`: apm, doctor, zona, especialidad, cartera_medica, cartera_medica_estado, linea, linea_apm, familia_producto, catalogo_productos, ciclo, grilla, categoria, detalle_promocion_producto, agenda, agenda_producto, agenda_muestra, datos_visita, visita_planificada, tag, tag_doctor, ultima_milla_medico, ultima_milla_marca, ultima_milla_objetivo
2. WHEN se define la tabla `agenda`, THE Glue_Catalog SHALL configurarla con particionado por `fecha_visita`
3. THE Glue_Catalog SHALL registrar cada tabla CRM con table type `EXTERNAL_TABLE` y formato Iceberg (InputFormat/OutputFormat de Iceberg, SerDe de Iceberg)
4. THE Glue_Catalog SHALL configurar la propiedad `table_type=ICEBERG` en los parámetros de cada tabla
5. WHEN se define una tabla CRM, THE Glue_Catalog SHALL apuntar su location a `s3://{lake_bucket}/crm/{table_name}/`
6. WHEN se define una tabla CRM, THE Glue_Catalog SHALL incluir la definición de columnas con nombres y tipos de datos correspondientes al schema PostgreSQL de `crm_interno`, de modo que Athena pueda resolver las columnas sin depender de un crawler previo
7. WHEN se define una tabla CRM cuya definición en el schema `crm_interno` contiene más de 100,000 registros esperados (agenda, agenda_producto), THE Glue_Catalog SHALL registrar la tabla con al menos una partition key definida

### Requirement 4: Tablas Iceberg — Dominio CloseUp

**User Story:** Como pipeline DMS que va a replicar datos de CloseUp,
quiero definiciones de tablas Iceberg en Glue Catalog que reflejen el schema de prescripciones,
para que los datos de prescripciones sean queryeables con partition pruning eficiente.

#### Acceptance Criteria

1. THE DataLakeStack SHALL crear definiciones de tabla Iceberg en `pharmassist_cup` para las 10 tablas del schema `closeup`: medico, marca, mercado, mercado_producto, representante, prescripcion, medico_rep_novisitado, medico_representante, medico_visitado, mercado_modulo_linea
2. WHEN se define la tabla `prescripcion`, THE Glue_Catalog SHALL configurarla con particionado por `anio, mes, cdgreg_pmix` en ese orden de precedencia
3. THE Glue_Catalog SHALL registrar cada tabla CloseUp con table type `EXTERNAL_TABLE` y formato Iceberg (InputFormat/OutputFormat de Iceberg, SerDe de Iceberg) y location en `s3://{lake_bucket}/cup/{table_name}/`
4. THE Glue_Catalog SHALL configurar la propiedad `table_type=ICEBERG` en los parámetros de cada tabla CloseUp
5. WHEN se define una tabla CloseUp que no es `prescripcion`, THE Glue_Catalog SHALL registrarla sin partition keys

### Requirement 5: Tablas Iceberg — Dominio IQVIA

**User Story:** Como pipeline DMS que va a replicar datos de IQVIA,
quiero definiciones de tablas Iceberg en Glue Catalog que reflejen el star schema de ventas,
para que los datos de ventas de mercado sean queryeables con partition pruning por período.

#### Acceptance Criteria

1. THE DataLakeStack SHALL crear definiciones de tabla Iceberg en `pharmassist_iqvia` para las 13 tablas del schema `iqvia`: dim_periodo, dim_droga, dim_forma_farmaceutica, dim_laboratorio, dim_clase_terapeutica, dim_presentacion, dim_geografia, dim_clase, dim_combinacion_droga, rel_presentacion_droga, rel_presentacion_forma, rel_producto_laboratorio, fact_mercado_valor
2. WHEN se define la tabla `fact_mercado_valor`, THE Glue_Catalog SHALL configurarla con particionado por `idperiodo`
3. THE Glue_Catalog SHALL registrar cada tabla IQVIA con table type `EXTERNAL_TABLE`, formato Iceberg (InputFormat/OutputFormat de Iceberg, SerDe de Iceberg) y location en `s3://{lake_bucket}/iqvia/{table_name}/`
4. THE Glue_Catalog SHALL configurar la propiedad `table_type=ICEBERG` en los parámetros de cada tabla IQVIA

### Requirement 6: Tablas Iceberg — Dominio Maestros

**User Story:** Como pipeline de integración que necesita cruzar las 3 fuentes,
quiero definiciones de tablas maestras en Glue Catalog,
para que las queries cross-source en Athena puedan hacer JOIN entre dominios.

#### Acceptance Criteria

1. THE DataLakeStack SHALL crear definiciones de tabla Iceberg en `pharmassist_maestros` para las 3 tablas del schema `maestros`: maestro_medicos, maestro_integrador_producto, familia_interno_a_marca_cup
2. THE Glue_Catalog SHALL registrar cada tabla Maestros con table type `EXTERNAL_TABLE`, formato Iceberg (InputFormat/OutputFormat de Iceberg, SerDe de Iceberg) y location en `s3://{lake_bucket}/maestros/{table_name}/`
3. THE Glue_Catalog SHALL configurar la propiedad `table_type=ICEBERG` en los parámetros de cada tabla Maestros
4. THE DataLakeStack SHALL definir las 3 tablas Maestros sin partition keys, dado que son tablas de referencia de bajo volumen que no requieren partition pruning

### Requirement 7: Configuración Iceberg — Schema Evolution y ACID

**User Story:** Como ingeniero de datos que mantiene el data lake a largo plazo,
quiero que las tablas Iceberg soporten evolución de schema y transacciones ACID,
para que cambios en las fuentes no rompan queries existentes y cargas fallidas no corrompan datos.

#### Acceptance Criteria

1. THE Glue_Catalog SHALL configurar todas las tablas Iceberg con el metadata location apuntando a `s3://{lake_bucket}/{domain}/{table_name}/metadata/`
2. THE Glue_Catalog SHALL configurar el formato de almacenamiento subyacente como Apache Parquet para todas las tablas Iceberg
3. THE Glue_Catalog SHALL configurar las siguientes propiedades en cada tabla Iceberg para compatibilidad con Athena engine v3: `table_type=ICEBERG`, `metadata_location` apuntando al path de metadata, y `format-version=2`
4. WHEN se registra una tabla particionada, THE Glue_Catalog SHALL definir las partition keys como columnas de tipo identity transform en la configuración de particionado Iceberg
5. WHEN se agrega una nueva columna en la fuente de datos, THE Glue_Catalog SHALL permitir la evolución de schema (add column) sin requerir recreación de la tabla ni afectar queries existentes que no referencien la nueva columna
6. IF una operación de escritura falla antes de completar el commit del snapshot Iceberg, THEN THE Glue_Catalog SHALL mantener el estado de la tabla apuntando al último snapshot válido, sin exponer datos parciales a las queries

### Requirement 8: IAM Roles para Glue y ETL

**User Story:** Como servicio de Glue ETL que va a escribir datos en el lake,
quiero roles IAM con permisos mínimos para acceder al bucket y al catalog,
para operar con el principio de least privilege.

#### Acceptance Criteria

1. THE DataLakeStack SHALL crear un IAM Role `GlueCrawlerRole` con permisos S3 de solo lectura (`s3:GetObject`, `s3:ListBucket`) sobre el Lake_Bucket y permisos de escritura en el Glue_Catalog (`glue:CreateTable`, `glue:UpdateTable`, `glue:GetTable`, `glue:GetDatabase`, `glue:BatchCreatePartition`)
2. THE DataLakeStack SHALL crear un IAM Role `GlueEtlRole` con permisos S3 de lectura y escritura (`s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket`) sobre el Lake_Bucket y permisos en el Glue_Catalog (`glue:GetTable`, `glue:GetDatabase`, `glue:CreateTable`, `glue:UpdateTable`, `glue:BatchCreatePartition`, `glue:GetPartitions`)
3. WHEN se define el GlueCrawlerRole, THE DataLakeStack SHALL limitar los permisos S3 al ARN del Lake_Bucket y sus objetos (`arn:aws:s3:::bucket` y `arn:aws:s3:::bucket/*`)
4. WHEN se define el GlueEtlRole, THE DataLakeStack SHALL limitar los permisos S3 al ARN del Lake_Bucket y sus objetos (`arn:aws:s3:::bucket` y `arn:aws:s3:::bucket/*`)
5. THE DataLakeStack SHALL configurar ambos roles con trust policy para el servicio `glue.amazonaws.com`
6. THE DataLakeStack SHALL adjuntar la managed policy `AWSGlueServiceRole` a ambos roles (GlueCrawlerRole y GlueEtlRole) para permisos base del servicio Glue (logs, métricas, job bookmarks)
7. THE DataLakeStack SHALL verificar que ninguna policy inline de los roles utilice acciones con wildcard (`*`) en el campo Action

### Requirement 9: Athena Workgroup para Validación

**User Story:** Como ingeniero de datos que necesita validar que las tablas Iceberg están correctamente definidas,
quiero un Athena Workgroup configurado con resultado en S3 y límite de escaneo,
para poder ejecutar queries de validación con control de costos.

#### Acceptance Criteria

1. THE DataLakeStack SHALL crear un Athena Workgroup llamado `pharmassist-validation` en estado ENABLED
2. THE Athena_Workgroup SHALL configurar el output location en `s3://{lake_bucket}/athena-results/`
3. THE Athena_Workgroup SHALL configurar un byte-scan limit de 100 MB (104,857,600 bytes) por query para control de costos
4. THE Athena_Workgroup SHALL habilitar la configuración `enforce workgroup configuration` para que los usuarios no puedan sobreescribir las configuraciones del workgroup (output location, byte-scan limit, ni engine version)
5. THE Athena_Workgroup SHALL configurar el engine version como Athena engine version 3 (compatible con Iceberg)

### Requirement 10: CDK Stack — Entry Point y Estructura

**User Story:** Como desarrollador que necesita desplegar la infraestructura del data lake de forma independiente,
quiero un stack CDK separado con su propio entry point,
para poder hacer deploy sin afectar otros stacks del proyecto.

#### Acceptance Criteria

1. THE DataLakeStack SHALL vivir en `infrastructure/stacks/data_lake_stack.py` como stack CDK independiente
2. THE DataLakeStack SHALL tener un entry point separado en `infrastructure/app_datalake.py`
3. WHEN se ejecuta `cdk synth -a "python app_datalake.py"`, THE DataLakeStack SHALL sintetizar un template CloudFormation válido sin errores
4. THE DataLakeStack SHALL exportar como CloudFormation Outputs: el nombre del bucket, los nombres de las 4 Glue Databases, y el nombre del Athena Workgroup
5. THE DataLakeStack SHALL recibir la configuración de entorno (account, region) via propiedades del stack, no via variables de entorno
6. THE DataLakeStack SHALL aplicar tags via CDK Aspects: Project=PharmAssist, Environment=dev, Owner (configurable)
7. THE DataLakeStack SHALL desplegarse en la región `us-east-1`

### Requirement 10: CDK Stack — Entry Point y Estructura

**User Story:** Como desarrollador que necesita desplegar la infraestructura del data lake de forma independiente,
quiero un stack CDK separado con su propio entry point,
para poder hacer deploy sin afectar otros stacks del proyecto.

#### Acceptance Criteria

1. THE DataLakeStack SHALL vivir en `infrastructure/stacks/data_lake_stack.py` como una clase que hereda de `aws_cdk.Stack`, independiente de otros stacks del proyecto
2. THE DataLakeStack SHALL tener un entry point separado en `infrastructure/app_datalake.py` que instancie únicamente el DataLakeStack, cargue la configuración desde `.env` del proyecto root via `dotenv`, y llame a `app.synth()`
3. WHEN se ejecuta `cdk deploy --app '.venv/bin/python3 app_datalake.py'` desde el directorio `infrastructure/`, THE DataLakeStack SHALL sintetizar y desplegar un template CloudFormation válido sin errores ni dependencias de otros stacks
4. THE DataLakeStack SHALL exportar exactamente 6 CloudFormation Outputs via `CfnOutput`: el nombre del bucket S3, los nombres de las 4 Glue Databases (pharmassist_crm, pharmassist_cup, pharmassist_iqvia, pharmassist_maestros), y el nombre del Athena Workgroup
5. THE DataLakeStack SHALL recibir la configuración de entorno (account, region) via `cdk.Environment` pasado como parámetro `env` al constructor del stack, donde el entry point lee `AWS_ACCOUNT_ID` y `AWS_REGION` desde `.env` y los pasa al stack — el stack no lee variables de entorno directamente
6. THE DataLakeStack SHALL recibir parámetros de constructor `tag_project` (default: "PharmAssist"), `tag_environment` (default: "dev"), y `tag_owner` (default: "team"), y aplicar estos tags a todos los recursos del stack usando `Tags.of(self).add()` incluyendo un tag adicional `ManagedBy=cdk`
7. THE DataLakeStack SHALL desplegarse en la región `us-east-1`, configurada via el parámetro `AWS_REGION` en `.env` con valor por defecto `us-east-1` en el entry point
