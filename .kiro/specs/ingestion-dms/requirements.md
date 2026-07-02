# Requirements — ingestion-dms

## Overview

Configurar el pipeline de ingesta completo que replica datos desde el RDS PostgreSQL (desplegado en spec #1, VPC 10.100.0.0/16) hacia el data lake S3 (desplegado en spec #2), convierte los archivos Parquet resultantes a formato Apache Iceberg, y orquesta la ejecución periódica del pipeline. Incluye VPC Peering para conectividad de red, DMS Serverless para replicación, Glue ETL para conversión Parquet→Iceberg, y EventBridge para scheduling.

## Glossary

- **IngestionStack**: Stack CDK que contiene la infraestructura de ingesta (DMS, Glue ETL, VPC Peering, EventBridge)
- **DMS_Serverless**: AWS Database Migration Service en modo Serverless — replica datos de RDS a S3 sin gestión de instancias
- **DMS_Replication_Config**: Configuración de replicación serverless de DMS que define source, target y reglas de mapeo
- **Source_Endpoint**: Endpoint DMS que apunta al RDS PostgreSQL como origen de datos
- **Target_Endpoint**: Endpoint DMS que apunta al bucket S3 como destino de datos en formato Parquet
- **VPC_Peering**: Conexión de peering entre la VPC de DataSources (10.100.0.0/16) y la VPC donde opera DMS
- **Glue_ETL_Job**: Job de AWS Glue que lee archivos Parquet de la landing zone en S3 y escribe datos en formato Iceberg
- **Landing_Zone**: Prefijo `raw/` en el bucket S3 del lake donde DMS deposita los archivos Parquet antes de la conversión a Iceberg
- **Lake_Bucket**: Bucket S3 del data lake creado en spec #2 (`datalakestack-lakebucket9cd7bbd2-yhmuiqidlita`)
- **Iceberg_Table**: Tabla Apache Iceberg registrada en Glue Catalog (creada en spec #2) donde el ETL escribe los datos finales
- **EventBridge_Schedule**: Regla de Amazon EventBridge Scheduler que dispara la ejecución del pipeline en cadencia configurada
- **Step_Functions_Workflow**: Máquina de estados de AWS Step Functions que orquesta DMS → espera completitud → Glue ETL
- **Schema_Mapping**: Reglas de DMS que mapean schemas y tablas del RDS a prefijos en S3
- **Idempotencia**: Propiedad del pipeline donde re-ejecutar la carga no duplica datos en las tablas Iceberg destino
- **GlueEtlRole**: Rol IAM creado en spec #2 con permisos de lectura/escritura sobre el Lake_Bucket y Glue Catalog
- **RDS_Secret**: Secret en AWS Secrets Manager que contiene las credenciales del RDS PostgreSQL (creado en spec #1)

## Requirements

### Requirement 1: VPC Peering — Conectividad de Red

**User Story:** Como servicio DMS que necesita acceder al RDS PostgreSQL en una VPC aislada,
quiero una conexión VPC Peering con rutas configuradas en ambos lados,
para que DMS pueda alcanzar el RDS sin exponer la base de datos a internet.

#### Acceptance Criteria

1. THE IngestionStack SHALL crear una VPC Peering Connection entre la VPC de DataSources (CIDR 10.100.0.0/16) y la VPC default de la región us-east-1 donde opera DMS Serverless, con auto-aceptación habilitada dado que ambas VPCs pertenecen a la misma cuenta y región
2. WHEN se crea el VPC Peering, THE IngestionStack SHALL agregar rutas en las route tables de las subnets isolated de la VPC de DataSources con destino al CIDR de la VPC default y target el peering connection
3. WHEN se crea el VPC Peering, THE IngestionStack SHALL agregar rutas en todas las route tables de las subnets de la VPC default (públicas y privadas) con destino 10.100.0.0/16 y target el peering connection, para que DMS Serverless pueda alcanzar el RDS independientemente de la subnet donde se instancie
4. THE IngestionStack SHALL configurar el Security Group del RDS PostgreSQL para permitir tráfico entrante TCP en puerto 5432 desde el CIDR de la VPC default
5. IF la VPC Peering Connection no puede establecerse por conflicto de CIDR, THEN THE IngestionStack SHALL fallar el deploy con un mensaje de error indicando los rangos IP en conflicto entre ambas VPCs
6. WHEN se crea el VPC Peering, THE IngestionStack SHALL habilitar DNS resolution en la conexión de peering para que DMS pueda resolver el hostname del endpoint RDS a su dirección IP privada a través del peering

### Requirement 2: DMS Serverless — Source Endpoint (RDS PostgreSQL)

**User Story:** Como pipeline de replicación que necesita leer datos del RDS,
quiero un endpoint DMS configurado con las credenciales del RDS PostgreSQL,
para que DMS pueda conectarse a la base de datos y leer los 4 schemas.

#### Acceptance Criteria

1. THE IngestionStack SHALL crear un DMS Source Endpoint de tipo `postgresql` apuntando al RDS PostgreSQL de DataSources, configurado con `SecretsManagerSecretId` y `SecretsManagerAccessRoleArn` para integración nativa de credenciales via Secrets Manager
2. THE Source_Endpoint SHALL referenciar el Secret en AWS Secrets Manager creado por spec #1 (output `RdsSecretArn` del DataSourcesStack) usando el ARN recibido como parámetro del constructor del IngestionStack, sin hardcodear el valor
3. THE Source_Endpoint SHALL configurar el database name como `pharmassist` (la base de datos que contiene los 4 schemas: crm_interno, closeup, iqvia, maestros)
4. THE Source_Endpoint SHALL configurar SSL mode como `require` para encriptar el tráfico entre DMS y RDS
5. WHEN se crea el Source_Endpoint, THE IngestionStack SHALL otorgar al DmsServerlessRole (definido en Requirement 9) permisos `secretsmanager:GetSecretValue` y `secretsmanager:DescribeSecret` sobre el ARN del RDS_Secret
6. IF el Source_Endpoint no puede establecer conexión con el RDS durante un test de conexión manual (`dms:TestConnection`), THEN THE Source_Endpoint SHALL reportar el error de conectividad sin exponer credenciales en el mensaje de fallo

### Requirement 3: DMS Serverless — Target Endpoint (S3 Parquet)

**User Story:** Como pipeline de replicación que necesita escribir datos en el data lake,
quiero un endpoint DMS configurado para escribir archivos Parquet en S3,
para que los datos replicados lleguen al lake en formato columnar eficiente.

#### Acceptance Criteria

1. THE IngestionStack SHALL crear un DMS Target Endpoint de tipo `s3` con `bucketName` apuntando al Lake_Bucket y `serviceAccessRoleArn` apuntando al ARN del DmsServerlessRole definido en Requirement 9
2. THE Target_Endpoint SHALL configurar el formato de datos como Parquet con compresión SNAPPY
3. THE Target_Endpoint SHALL configurar el bucket folder como `raw/` para que todos los archivos de DMS se depositen en la Landing_Zone
4. THE Target_Endpoint SHALL configurar `dataFormat=parquet`, `parquetVersion=PARQUET_2_0`, y `encodingType=PLAIN_DICTIONARY`
5. THE Target_Endpoint SHALL configurar `addColumnName=true` para incluir nombres de columna en los archivos Parquet
6. THE Target_Endpoint SHALL configurar `timestampColumnName=fecha_carga` para agregar una columna con la fecha/hora de carga en cada registro, donde DMS escribe el timestamp en formato UTC
7. WHEN se crea el Target_Endpoint, THE IngestionStack SHALL otorgar al DmsServerlessRole permisos `s3:PutObject` y `s3:DeleteObject` sobre los objetos del Lake_Bucket bajo el prefijo `raw/*` (ARN `arn:aws:s3:::bucket/raw/*`), y permiso `s3:ListBucket` sobre el ARN del Lake_Bucket con Condition `s3:prefix` limitado a `raw/`

### Requirement 4: DMS Serverless — Replication Config

**User Story:** Como ingeniero de datos que necesita replicar los 4 schemas completos,
quiero una configuración de replicación DMS Serverless con table mappings para los 51 tablas,
para que todos los datos del RDS se repliquen al S3 organizados por schema y tabla.

#### Acceptance Criteria

1. THE IngestionStack SHALL crear una DMS Serverless Replication Config con replication type `full-load` (carga completa sin CDC) que referencie el Source_Endpoint y el Target_Endpoint creados en los Requirements 2 y 3 respectivamente
2. THE DMS_Replication_Config SHALL incluir table mappings con 4 selection rules de tipo `include`, una por cada schema (`crm_interno`, `closeup`, `iqvia`, `maestros`), cada una con table-name pattern `%` para seleccionar todas las tablas del schema
3. THE DMS_Replication_Config SHALL configurar transformation rules de tipo `rename-schema` que mapeen cada schema de origen a su prefijo de dominio en S3: `crm_interno` → `crm_interno`, `closeup` → `closeup`, `iqvia` → `iqvia`, `maestros` → `maestros`, de modo que los archivos se depositen en `raw/{schema_name}/{table_name}/` según la configuración del Target_Endpoint
4. THE DMS_Replication_Config SHALL configurar el compute config con min_capacity_units=1 y max_capacity_units=4 DCU para DMS Serverless
5. THE DMS_Replication_Config SHALL configurar el compute config con los subnet IDs de la VPC default de us-east-1, el security group que permite tráfico saliente al RDS via VPC Peering, y la availability zone correspondiente a las subnets seleccionadas
6. THE DMS_Replication_Config SHALL configurar el replication config con multi_az=false para entorno de desarrollo (reducir costos)
7. WHEN se ejecuta la replicación, THE DMS_Serverless SHALL replicar las 51 tablas de los 4 schemas produciendo archivos Parquet en la Landing_Zone del Lake_Bucket bajo la estructura `raw/{schema_name}/{table_name}/`
8. IF una tabla del RDS está vacía, THEN THE DMS_Serverless SHALL crear igualmente el prefijo `raw/{schema_name}/{table_name}/` en S3 sin generar archivos de datos Parquet

### Requirement 5: Glue ETL Job — Conversión Parquet a Iceberg

**User Story:** Como data lake que necesita datos en formato Iceberg para queries eficientes con Athena,
quiero un job de Glue ETL que lea los Parquet de la landing zone y escriba en las tablas Iceberg registradas,
para que los datos queden disponibles para consulta inmediata con partition pruning y time travel.

#### Acceptance Criteria

1. THE IngestionStack SHALL crear un Glue ETL Job con nombre `pharmassist-parquet-to-iceberg` que ejecute un script PySpark almacenado en `s3://{lake_bucket}/scripts/parquet_to_iceberg.py`
2. THE Glue_ETL_Job SHALL leer archivos Parquet desde `s3://{lake_bucket}/raw/{schema_name}/{table_name}/` para cada una de las 51 tablas definidas en los schemas `crm_interno`, `closeup`, `iqvia` y `maestros`
3. THE Glue_ETL_Job SHALL escribir los datos en las tablas Iceberg ya registradas en Glue Catalog utilizando modo overwrite (reemplazo completo de datos en cada tabla), de modo que cada ejecución sea idempotente y produzca el mismo resultado independientemente del estado previo
4. WHEN se procesan tablas del dominio CRM (schema `crm_interno`), THE Glue_ETL_Job SHALL mapear los datos al Glue Database `pharmassist_crm` y escribir en la location `s3://{lake_bucket}/crm/{table_name}/`
5. WHEN se procesan tablas del dominio CloseUp (schema `closeup`), THE Glue_ETL_Job SHALL mapear los datos al Glue Database `pharmassist_cup` y escribir en la location `s3://{lake_bucket}/cup/{table_name}/`
6. WHEN se procesan tablas del dominio IQVIA (schema `iqvia`), THE Glue_ETL_Job SHALL mapear los datos al Glue Database `pharmassist_iqvia` y escribir en la location `s3://{lake_bucket}/iqvia/{table_name}/`
7. WHEN se procesan tablas del dominio Maestros (schema `maestros`), THE Glue_ETL_Job SHALL mapear los datos al Glue Database `pharmassist_maestros` y escribir en la location `s3://{lake_bucket}/maestros/{table_name}/`
8. THE Glue_ETL_Job SHALL usar el GlueEtlRole creado en spec #2 como execution role
9. THE Glue_ETL_Job SHALL configurarse con worker type `G.1X`, number of workers=2, Glue version 4.0 (Spark 3.3 con soporte Iceberg nativo), y timeout de 60 minutos
10. THE Glue_ETL_Job SHALL configurar el job bookmark como DISABLED dado que la carga es full-load idempotente
11. IF no existen archivos Parquet en el path de origen de una tabla (`s3://{lake_bucket}/raw/{schema_name}/{table_name}/`), THEN THE Glue_ETL_Job SHALL omitir esa tabla, registrar un mensaje de log indicando la tabla omitida, y continuar procesando las tablas restantes sin fallar la ejecución del job
12. IF la escritura a una tabla Iceberg falla por incompatibilidad de schema entre los datos Parquet y la definición en Glue Catalog, THEN THE Glue_ETL_Job SHALL registrar un error indicando el nombre de la tabla y la causa del fallo, y continuar procesando las tablas restantes

### Requirement 6: Glue ETL — Idempotencia y Particionado

**User Story:** Como operador del pipeline que puede necesitar re-ejecutar cargas,
quiero que el ETL sea idempotente y respete la estrategia de particionado definida,
para que re-ejecuciones no dupliquen datos y las queries se beneficien de partition pruning.

#### Acceptance Criteria

1. THE Glue_ETL_Job SHALL implementar escritura idempotente usando el modo `overwrite` de Iceberg (reemplazar datos completos de la tabla en cada ejecución), aplicando `writeTo().overwritePartitions()` para tablas particionadas y `writeTo().using("iceberg").overwrite()` para tablas no particionadas
2. WHEN se escriben datos en tablas particionadas del dominio CRM (tabla `agenda`), THE Glue_ETL_Job SHALL particionar por la columna `fecha_visita` usando identity transform
3. WHEN se escriben datos en la tabla `prescripcion` del dominio CloseUp, THE Glue_ETL_Job SHALL particionar por las columnas `anio`, `mes`, `cdgreg_pmix` en ese orden
4. WHEN se escriben datos en la tabla `fact_mercado_valor` del dominio IQVIA, THE Glue_ETL_Job SHALL particionar por la columna `idperiodo`
5. WHEN se escriben datos en tablas sin partition keys definidas en Glue Catalog, THE Glue_ETL_Job SHALL usar overwrite completo a nivel tabla (no append)
6. THE Glue_ETL_Job SHALL generar snapshots Iceberg válidos que contengan al menos un manifest file y un manifest list en el path `s3://{lake_bucket}/{domain}/{table_name}/metadata/` para cada tabla procesada con datos
7. IF el job se ejecuta dos veces consecutivas con los mismos datos de entrada, THEN THE Glue_ETL_Job SHALL producir el mismo row count en cada tabla Iceberg, verificable con `SELECT COUNT(*) FROM {database}.{table}` retornando el mismo valor en ambas ejecuciones

### Requirement 7: Orquestación — Step Functions Workflow

**User Story:** Como operador del pipeline que necesita ejecutar DMS y luego Glue ETL en secuencia,
quiero un workflow de Step Functions que orqueste ambos pasos con manejo de errores,
para que el pipeline se ejecute de forma confiable sin intervención manual.

#### Acceptance Criteria

1. THE IngestionStack SHALL crear un Step Functions State Machine de tipo STANDARD llamada `pharmassist-ingestion-pipeline`
2. THE Step_Functions_Workflow SHALL ejecutar como primer paso una tarea que invoque la API `StartReplication` de DMS sobre la Replication Config del pipeline, referenciada por ARN recibido como parámetro del stack
3. THE Step_Functions_Workflow SHALL esperar a que la replicación DMS complete exitosamente antes de proceder al siguiente paso, usando un patrón de polling con intervalo de 60 segundos que consulte `DescribeReplications` y considere el status `stopped` con stop-reason `FULL_LOAD_ONLY_FINISHED` como éxito
4. WHEN la replicación DMS completa exitosamente, THE Step_Functions_Workflow SHALL ejecutar el Glue ETL Job `pharmassist-parquet-to-iceberg` mediante la acción `StartJobRun`
5. THE Step_Functions_Workflow SHALL esperar a que el Glue ETL Job complete exitosamente, usando un patrón de polling con intervalo de 30 segundos que consulte `GetJobRun` y considere el status `SUCCEEDED` como éxito
6. IF la replicación DMS reporta un status `failed` o `error`, THEN THE Step_Functions_Workflow SHALL capturar el error en el campo Cause del estado de ejecución y terminar con status FAILED sin ejecutar el Glue ETL
7. IF el Glue ETL Job reporta un status `FAILED`, `TIMEOUT` o `ERROR`, THEN THE Step_Functions_Workflow SHALL capturar el error en el campo Cause del estado de ejecución y terminar con status FAILED
8. THE Step_Functions_Workflow SHALL configurar un timeout total de 60 minutos (3600 segundos) para la ejecución completa del pipeline, tras el cual la ejecución termina con status `TIMED_OUT`
9. THE Step_Functions_Workflow SHALL tener un IAM Role con trust policy para `states.amazonaws.com` y permisos explícitos: `dms:StartReplication`, `dms:DescribeReplications` sobre la Replication Config; `glue:StartJobRun`, `glue:GetJobRun` sobre el Glue Job; sin acciones wildcard (`*`) en el campo Action
10. IF el timeout de 60 minutos se alcanza durante el polling de DMS o Glue, THEN THE Step_Functions_Workflow SHALL terminar la ejecución con status `TIMED_OUT` sin intentar pasos adicionales

### Requirement 8: Orquestación — EventBridge Schedule

**User Story:** Como operador del pipeline que necesita ejecución periódica automatizada,
quiero un schedule de EventBridge que dispare el workflow de Step Functions,
para que la ingesta se ejecute sin intervención manual en la cadencia configurada.

#### Acceptance Criteria

1. THE IngestionStack SHALL crear un EventBridge Scheduler Schedule llamado `pharmassist-ingestion-schedule`
2. THE EventBridge_Schedule SHALL configurarse con una expresión cron para ejecución diaria a las 02:00 UTC, con timezone configurado explícitamente como `UTC` en el parámetro ScheduleExpressionTimezone
3. THE EventBridge_Schedule SHALL tener como target la State Machine de Step Functions `pharmassist-ingestion-pipeline`, referenciada por ARN obtenido del recurso creado en Requirement 7 del mismo stack
4. IF el entorno configurado es desarrollo, THEN THE EventBridge_Schedule SHALL crearse en estado DISABLED para prevenir ejecuciones automáticas no deseadas durante el desarrollo
5. THE EventBridge_Schedule SHALL tener un IAM Role dedicado con trust policy para el servicio `scheduler.amazonaws.com` y permiso `states:StartExecution` limitado al ARN de la State Machine target
6. WHEN se activa el schedule y se dispara la ejecución, THE EventBridge_Schedule SHALL pasar un payload vacío `{}` como input a la State Machine
7. THE EventBridge_Schedule SHALL configurar una retry policy con un máximo de 2 reintentos y un maximum event age de 60 minutos, de modo que si la invocación de StartExecution falla transitoriamente, el scheduler reintente antes de descartar el evento

### Requirement 9: IAM — Roles y Permisos para DMS

**User Story:** Como servicio DMS que necesita acceder a RDS y S3,
quiero roles IAM con permisos mínimos necesarios,
para operar con el principio de least privilege sin exponer recursos innecesarios.

#### Acceptance Criteria

1. THE IngestionStack SHALL crear un IAM Role `DmsServerlessRole` con trust policy para el servicio `dms.amazonaws.com`
2. THE DmsServerlessRole SHALL tener una policy inline con dos statements: (a) permisos `s3:PutObject` y `s3:DeleteObject` sobre el resource ARN `arn:aws:s3:::{lake_bucket}/raw/*` para operaciones a nivel de objeto, y (b) permisos `s3:ListBucket` y `s3:GetBucketLocation` sobre el resource ARN `arn:aws:s3:::{lake_bucket}` con condition key `s3:prefix` limitado a `raw/`
3. THE DmsServerlessRole SHALL tener permisos `secretsmanager:GetSecretValue` sobre el ARN del RDS_Secret para obtener credenciales de conexión
4. IF el RDS_Secret está encriptado con una Customer Managed Key (CMK), THEN THE DmsServerlessRole SHALL tener permisos `kms:Decrypt` y `kms:DescribeKey` sobre el ARN de dicha KMS key
5. THE IngestionStack SHALL incluir un test de CDK assertions que verifique que ninguna policy inline del DmsServerlessRole contenga acciones con wildcard (`*`) en el campo Action, usando `Template.from_stack()` y `has_resource_properties()` para inspeccionar el template sintetizado
6. IF el service-linked role `dms-vpc-role` no existe previamente en la cuenta, THEN THE IngestionStack SHALL crear un IAM Role `dms-vpc-role` con trust policy para `dms.amazonaws.com` y adjuntar la managed policy `AmazonDMSVPCManagementRole`

### Requirement 10: CDK Stack — Estructura e Integración

**User Story:** Como desarrollador que necesita desplegar la infraestructura de ingesta,
quiero un stack CDK que se integre con los stacks existentes de DataSources y DataLake,
para poder desplegar la ingesta de forma independiente pero conectada a los recursos previos.

#### Acceptance Criteria

1. THE IngestionStack SHALL vivir en `infrastructure/stacks/ingestion_stack.py` como una clase que hereda de `aws_cdk.Stack`, independiente de otros stacks del proyecto
2. THE IngestionStack SHALL tener un entry point en `infrastructure/app_ingestion.py` que instancie el stack cargando la configuración desde `.env` del proyecto root via `dotenv`, leyendo las variables `AWS_ACCOUNT_ID`, `AWS_REGION`, `TAG_PROJECT`, `TAG_ENVIRONMENT`, `TAG_OWNER`, `RDS_SECRET_ARN`, `DATASOURCES_VPC_ID`, `LAKE_BUCKET_NAME`, `GLUE_DB_CRM`, `GLUE_DB_CUP`, `GLUE_DB_IQVIA`, `GLUE_DB_MAESTROS`, y pasándolas como parámetros al constructor del stack
3. WHEN se ejecuta `cdk synth --app '.venv/bin/python3 app_ingestion.py'` desde el directorio `infrastructure/`, THE IngestionStack SHALL sintetizar un template CloudFormation válido sin errores
4. THE IngestionStack SHALL recibir como parámetros de constructor: `rds_secret_arn` (string, ARN del Secret de RDS de DataSourcesStack), `vpc_id` (string, VPC ID de DataSourcesStack), `lake_bucket_name` (string, nombre del bucket S3 de DataLakeStack), y `glue_database_names` (dict con claves `crm`, `cup`, `iqvia`, `maestros` y valores string con los nombres de las 4 Glue Databases de DataLakeStack)
5. THE IngestionStack SHALL importar recursos cross-stack usando `Fn.import_value` o parámetros explícitos pasados al constructor (no hardcodear ARNs ni nombres de recursos); el stack no debe declarar dependencias CDK directas contra DataLakeStack ni DataSourcesStack
6. THE IngestionStack SHALL exportar exactamente 3 CloudFormation Outputs via `CfnOutput`: el ARN de la State Machine, el nombre del Glue ETL Job, y el ARN del EventBridge Schedule
7. THE IngestionStack SHALL recibir parámetros de constructor `tag_project` (default: "PharmAssist"), `tag_environment` (default: "dev"), y `tag_owner` (default: "team"), y aplicar estos tags a todos los recursos del stack usando `Tags.of(self).add()` incluyendo un tag adicional `ManagedBy=cdk`
8. THE IngestionStack SHALL desplegarse en la región `us-east-1`, configurada via el parámetro `AWS_REGION` en `.env` con valor por defecto `us-east-1` en el entry point
9. WHEN se ejecuta `cdk deploy --app '.venv/bin/python3 app_ingestion.py'`, THE IngestionStack SHALL desplegarse exitosamente siempre que DataLakeStack y DataSourcesStack hayan sido desplegados previamente (sus recursos existen en la cuenta); no se requiere que estén en la misma app CDK ni que se desplieguen en la misma sesión
10. IF alguno de los parámetros obligatorios del constructor (`rds_secret_arn`, `vpc_id`, `lake_bucket_name`, `glue_database_names`) es None o string vacío, THEN THE entry point SHALL fallar con un error indicando qué variable de entorno falta, antes de intentar sintetizar el stack

### Requirement 11: Glue ETL — Script PySpark

**User Story:** Como job de Glue que necesita un script ejecutable,
quiero un script PySpark almacenado en S3 que implemente la lógica de conversión,
para que el Glue ETL Job tenga el código necesario para transformar Parquet a Iceberg.

#### Acceptance Criteria

1. THE IngestionStack SHALL almacenar el script PySpark del ETL en `s3://{lake_bucket}/scripts/parquet_to_iceberg.py` como un CDK Asset desplegado durante `cdk deploy`
2. THE Glue_ETL_Job SHALL referenciar el script desde la ubicación `s3://{lake_bucket}/scripts/parquet_to_iceberg.py` como su script location
3. THE script PySpark SHALL configurar la SparkSession con el catálogo Glue como implementación Iceberg (spark.sql.catalog con tipo `glue`, warehouse apuntando a `s3://{lake_bucket}/`) para habilitar escritura nativa en tablas Iceberg registradas en Glue Catalog
4. THE script PySpark SHALL iterar sobre los 4 schemas leyendo Parquet desde `s3://{lake_bucket}/raw/{schema_name}/{table_name}/` y escribiendo en las tablas Iceberg del Glue Database correspondiente (crm_interno→pharmassist_crm, closeup→pharmassist_cup, iqvia→pharmassist_iqvia, maestros→pharmassist_maestros), descubriendo las tablas disponibles consultando el Glue Catalog de cada database
5. THE script PySpark SHALL usar la API de Spark con soporte Iceberg nativo (`spark.sql` con `INSERT OVERWRITE` o DataFrame API con `writeTo().overwritePartitions()`)
6. IF no existen archivos Parquet en la landing zone para una tabla (`s3://{lake_bucket}/raw/{schema_name}/{table_name}/` vacío o inexistente), THEN THE script PySpark SHALL registrar un log de advertencia con el nombre de la tabla omitida y continuar con la siguiente tabla sin fallar
7. THE script PySpark SHALL loguear el progreso de cada tabla procesada incluyendo: nombre completo (database.table), cantidad de registros escritos, y tiempo de procesamiento en segundos
8. IF una tabla individual falla durante el procesamiento, THEN THE script PySpark SHALL registrar el error con el nombre de la tabla y el mensaje de excepción, continuar con las tablas restantes, y al finalizar imprimir un resumen con la cantidad de tablas exitosas y la lista de tablas fallidas
9. IF al menos una tabla falla durante la ejecución, THEN THE script PySpark SHALL terminar con exit code distinto de cero (sys.exit(1)) para que Step Functions detecte el job como fallido y pueda ejecutar la rama de error del workflow

### Requirement 12: Validación Post-Ingesta

**User Story:** Como ingeniero de datos que necesita confirmar que la ingesta fue exitosa,
quiero poder validar que los datos llegaron correctamente a las tablas Iceberg,
para tener confianza de que el pipeline funciona end-to-end antes de pasar al siguiente spec.

#### Acceptance Criteria

1. WHEN el Glue_ETL_Job completa exitosamente, THE Iceberg_Table de cada dominio SHALL contener al menos 1 registro queryeable via Athena usando el workgroup `pharmassist-validation`, verificado mediante una query `SELECT COUNT(*) FROM {database}.{table}` que retorna un resultado mayor a cero sin errores de ejecución dentro de 60 segundos
2. WHEN se ejecuta `SELECT COUNT(*) FROM pharmassist_crm.doctor` en Athena con el workgroup `pharmassist-validation`, THE query SHALL retornar un número igual al count de registros en la tabla `crm_interno.doctor` del RDS fuente
3. WHEN se ejecuta `SELECT COUNT(*) FROM pharmassist_cup.prescripcion` en Athena con el workgroup `pharmassist-validation`, THE query SHALL retornar un número igual al count de registros en la tabla `closeup.prescripcion` del RDS fuente
4. WHEN se ejecuta `SELECT COUNT(*) FROM pharmassist_iqvia.fact_mercado_valor` en Athena con el workgroup `pharmassist-validation`, THE query SHALL retornar un número igual al count de registros en la tabla `iqvia.fact_mercado_valor` del RDS fuente
5. WHEN se ejecuta `SELECT COUNT(*) FROM pharmassist_maestros.maestro_medicos` en Athena con el workgroup `pharmassist-validation`, THE query SHALL retornar un número igual al count de registros en la tabla `maestros.maestro_medicos` del RDS fuente
6. WHEN Athena ejecuta una query sobre cualquier tabla Iceberg del data lake, THE query SHALL resolver el metadata del snapshot sin producir errores de tipo `ICEBERG_CANNOT_OPEN_SPLIT` ni `HIVE_CANNOT_OPEN_SPLIT`, confirmando que los snapshots Iceberg escritos por el Glue_ETL_Job son estructuralmente válidos
7. WHEN se ejecuta una query con cláusula WHERE sobre una columna de partición (ej: `SELECT COUNT(*) FROM pharmassist_cup.prescripcion WHERE anio = 2025 AND mes = 6`), THE Athena query SHALL escanear menos del 50% del total de bytes de la tabla, verificable comparando el campo `data_scanned_in_bytes` de la ejecución filtrada contra una ejecución sin filtro sobre la misma tabla
8. IF una query de validación en Athena falla con error de timeout o error de servicio, THEN THE ingeniero de datos SHALL poder re-ejecutar la misma query sin necesidad de re-correr el pipeline de ingesta, dado que los snapshots Iceberg persisten independientemente del estado de la query
