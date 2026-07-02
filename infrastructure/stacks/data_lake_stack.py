"""DataLakeStack — Infraestructura fundacional del data lake de PharmAssist.

Provisiona:
- S3 Bucket con estructura de prefijos por dominio (crm/, cup/, iqvia/, maestros/)
- Glue Data Catalog con 4 databases y 51 tablas Iceberg
- IAM Roles para Glue Crawler y ETL con least privilege
- Athena Workgroup para validación con control de costos
"""

import aws_cdk as cdk
from aws_cdk import Duration, RemovalPolicy, Tags
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_athena as athena
from aws_cdk import aws_s3 as s3
from constructs import Construct

from cdk_constructs.iceberg_table import register_iceberg_table
from table_definitions import CRM_TABLES, CUP_TABLES, IQVIA_TABLES, MAESTROS_TABLES


# Glue Database definitions per domain
DATABASES = {
    "crm": {
        "name": "pharmassist_crm",
        "description": "Fuente: CRM interno | Cadencia: diaria",
        "location_prefix": "crm",
    },
    "cup": {
        "name": "pharmassist_cup",
        "description": "Fuente: CloseUp International | Cadencia: mensual",
        "location_prefix": "cup",
    },
    "iqvia": {
        "name": "pharmassist_iqvia",
        "description": "Fuente: IQVIA | Cadencia: mensual",
        "location_prefix": "iqvia",
    },
    "maestros": {
        "name": "pharmassist_maestros",
        "description": "Fuente: Tablas de integración cross-source | Cadencia: bajo demanda",
        "location_prefix": "maestros",
    },
}


class DataLakeStack(cdk.Stack):
    """CDK Stack que contiene toda la infraestructura del data lake."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        tag_project: str = "PharmAssist",
        tag_environment: str = "dev",
        tag_owner: str = "team",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Apply tags to all resources in the stack
        Tags.of(self).add("Project", tag_project)
        Tags.of(self).add("Environment", tag_environment)
        Tags.of(self).add("Owner", tag_owner)
        Tags.of(self).add("ManagedBy", "cdk")

        # Create resources in order
        self.lake_bucket = self._create_bucket()
        self.databases = self._create_databases()
        self._register_tables()
        self._create_iam_roles()
        self._create_athena_workgroup()
        self._create_outputs()

    def _create_bucket(self):
        """Create S3 bucket for the data lake."""
        lake_bucket = s3.Bucket(
            self,
            "LakeBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,  # SSE-S3 (AES-256)
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,  # dev environment
            auto_delete_objects=True,  # permite cdk destroy limpio
            lifecycle_rules=[
                # Rule 1: Archive objetos con tag lifecycle=archive después de 365 días
                s3.LifecycleRule(
                    id="archive-tagged-objects",
                    tag_filters={"lifecycle": "archive"},
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(365),
                        )
                    ],
                ),
                # Rule 2: Eliminar versiones no-current después de 90 días
                s3.LifecycleRule(
                    id="delete-noncurrent-versions",
                    noncurrent_version_expiration=Duration.days(90),
                ),
                # Rule 3: Abortar multipart uploads incompletos después de 7 días
                s3.LifecycleRule(
                    id="abort-incomplete-multipart",
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                ),
            ],
        )
        return lake_bucket

    def _create_databases(self):
        """Create 4 Glue databases (CRM, CloseUp, IQVIA, Maestros)."""
        databases = {}
        for key, db_config in DATABASES.items():
            databases[key] = glue.CfnDatabase(
                self,
                f"{key}-database",
                catalog_id=cdk.Aws.ACCOUNT_ID,
                database_input=glue.CfnDatabase.DatabaseInputProperty(
                    name=db_config["name"],
                    description=db_config["description"],
                    location_uri=f"s3://{self.lake_bucket.bucket_name}/{db_config['location_prefix']}/",
                ),
            )
        return databases

    def _register_tables(self):
        """Register all 51 Iceberg tables using the helper function."""
        # Map domain prefix to (table list, database name, database resource)
        domain_config = [
            ("crm", CRM_TABLES, "pharmassist_crm"),
            ("cup", CUP_TABLES, "pharmassist_cup"),
            ("iqvia", IQVIA_TABLES, "pharmassist_iqvia"),
            ("maestros", MAESTROS_TABLES, "pharmassist_maestros"),
        ]

        for domain_prefix, tables, db_name in domain_config:
            db_resource = self.databases[domain_prefix]
            for table_def in tables:
                table_resource = register_iceberg_table(
                    scope=self,
                    database_name=db_name,
                    bucket=self.lake_bucket,
                    domain_prefix=domain_prefix,
                    table_def=table_def,
                )
                # Ensure table is created AFTER its database
                table_resource.add_dependency(db_resource)

    def _create_iam_roles(self):
        """Create GlueCrawlerRole and GlueEtlRole."""
        # GlueCrawlerRole — read-only S3, write Glue Catalog
        self.crawler_role = iam.Role(
            self,
            "GlueCrawlerRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSGlueServiceRole"
                ),
            ],
        )

        # S3: solo lectura sobre el lake bucket
        self.crawler_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[
                    self.lake_bucket.bucket_arn,
                    f"{self.lake_bucket.bucket_arn}/*",
                ],
            )
        )

        # Glue Catalog: crear/actualizar tablas y particiones
        self.crawler_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    "glue:GetTable",
                    "glue:GetDatabase",
                    "glue:BatchCreatePartition",
                ],
                resources=["*"],  # Glue catalog resources use account-level ARNs
            )
        )

        # GlueEtlRole — read-write S3, read-write Glue Catalog
        self.etl_role = iam.Role(
            self,
            "GlueEtlRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSGlueServiceRole"
                ),
            ],
        )

        # S3: lectura y escritura sobre el lake bucket
        self.etl_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket",
                ],
                resources=[
                    self.lake_bucket.bucket_arn,
                    f"{self.lake_bucket.bucket_arn}/*",
                ],
            )
        )

        # Glue Catalog: operaciones de tabla y particiones
        self.etl_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "glue:GetTable",
                    "glue:GetDatabase",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    "glue:BatchCreatePartition",
                    "glue:GetPartitions",
                ],
                resources=["*"],
            )
        )

    def _create_athena_workgroup(self):
        """Create Athena workgroup for validation."""
        self.athena_workgroup = athena.CfnWorkGroup(
            self,
            "ValidationWorkgroup",
            name="pharmassist-validation",
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{self.lake_bucket.bucket_name}/athena-results/",
                ),
                bytes_scanned_cutoff_per_query=104_857_600,  # 100 MB
                enforce_work_group_configuration=True,
                engine_version=athena.CfnWorkGroup.EngineVersionProperty(
                    selected_engine_version="Athena engine version 3",
                ),
            ),
        )

    def _create_outputs(self):
        """Create CloudFormation outputs."""
        cdk.CfnOutput(self, "LakeBucketName",
            value=self.lake_bucket.bucket_name,
            description="Name of the data lake S3 bucket",
        )
        cdk.CfnOutput(self, "CrmDatabaseName",
            value="pharmassist_crm",
            description="Name of the CRM Glue database",
        )
        cdk.CfnOutput(self, "CupDatabaseName",
            value="pharmassist_cup",
            description="Name of the CloseUp Glue database",
        )
        cdk.CfnOutput(self, "IqviaDatabaseName",
            value="pharmassist_iqvia",
            description="Name of the IQVIA Glue database",
        )
        cdk.CfnOutput(self, "MaestrosDatabaseName",
            value="pharmassist_maestros",
            description="Name of the Maestros Glue database",
        )
        cdk.CfnOutput(self, "AthenaWorkgroupName",
            value="pharmassist-validation",
            description="Name of the Athena validation workgroup",
        )
