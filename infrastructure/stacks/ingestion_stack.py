"""IngestionStack — Pipeline de ingesta DMS + Glue ETL para PharmAssist.

Provisiona:
- VPC Peering entre DataSources VPC y VPC default (conectividad DMS → RDS)
- DMS Serverless (Source Endpoint RDS, Target Endpoint S3, Replication Config)
- Glue ETL Job (conversión Parquet → Iceberg)
- Step Functions State Machine (orquestación DMS → Glue)
- EventBridge Schedule (ejecución diaria 02:00 UTC)
- IAM Roles con least privilege para DMS, Step Functions y Scheduler
"""

import json
import os

import aws_cdk as cdk
from aws_cdk import (
    Tags,
    aws_dms as dms,
    aws_ec2 as ec2,
    aws_glue as glue,
    aws_iam as iam,
    aws_s3_assets as s3_assets,
    aws_scheduler as scheduler,
    aws_stepfunctions as sfn,
    custom_resources as cr,
)
from constructs import Construct

from cdk_constructs.maestros_validation import MaestrosValidationQueries


class IngestionStack(cdk.Stack):
    """CDK Stack que contiene la infraestructura de ingesta (DMS, Glue ETL, VPC Peering, EventBridge)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        # Cross-stack parameters (from .env)
        rds_secret_arn: str,
        datasources_vpc_id: str,
        lake_bucket_name: str,
        glue_database_names: dict,  # {"crm": "pharmassist_crm", "cup": "...", ...}
        # Tags
        tag_project: str = "PharmAssist",
        tag_environment: str = "dev",
        tag_owner: str = "team",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store parameters for use by resource methods
        self._rds_secret_arn = rds_secret_arn
        self._datasources_vpc_id = datasources_vpc_id
        self._lake_bucket_name = lake_bucket_name
        self._glue_database_names = glue_database_names
        self._tag_environment = tag_environment

        # Apply tags to all resources in the stack
        Tags.of(self).add("Project", tag_project)
        Tags.of(self).add("Environment", tag_environment)
        Tags.of(self).add("Owner", tag_owner)
        Tags.of(self).add("ManagedBy", "cdk")

        # --- VPC Peering (Task 3.1) ---
        self._create_vpc_peering()

        # --- IAM Roles (Task 4.1) ---
        self._create_iam_roles()

        # --- DMS Endpoints (Task 5.1+) ---
        self._create_dms_endpoints()

        # --- Glue ETL Job (Task 6.2) ---
        self._create_glue_job()

        # --- Step Functions State Machine (Task 7.1) ---
        self._create_state_machine()

        # --- EventBridge Schedule (Task 8.1 + 8.2) ---
        self._create_eventbridge_schedule()

        # --- Maestros Validation Named Queries (Task 3.2) ---
        self._maestros_validation = MaestrosValidationQueries(
            self,
            "MaestrosValidation",
            workgroup_name="pharmassist-validation",
            glue_databases=self._glue_database_names,
        )

    def _create_vpc_peering(self) -> None:
        """Create VPC Peering Connection between DataSources VPC and DMS VPC.

        Creates a dedicated VPC for DMS Serverless (10.200.0.0/16) and peers it
        with the DataSources VPC (10.100.0.0/16). This avoids depending on a
        default VPC which may not exist in the account.

        DNS resolution is enabled on both sides so DMS can resolve the RDS
        endpoint hostname to its private IP through the peering connection.
        """
        # Import DataSources VPC (10.100.0.0/16) — contains RDS PostgreSQL.
        # from_lookup is needed for route table iteration in task 3.2.
        self._datasources_vpc = ec2.Vpc.from_lookup(
            self,
            "DataSourcesVpc",
            vpc_id=self._datasources_vpc_id,
        )

        # Create a dedicated VPC for DMS Serverless (10.200.0.0/16).
        # This replaces the default VPC lookup which fails when no default VPC exists.
        # DMS Serverless only needs private isolated subnets (no internet access needed).
        self._dms_vpc = ec2.Vpc(
            self,
            "DmsVpc",
            ip_addresses=ec2.IpAddresses.cidr("10.200.0.0/16"),
            max_azs=2,
            nat_gateways=0,  # DMS doesn't need internet access
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="DmsPrivate",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # Create VPC Peering Connection with auto-accept (same account & region).
        # When both VPCs belong to the same account and region, CloudFormation
        # automatically accepts the peering request.
        self._vpc_peering = ec2.CfnVPCPeeringConnection(
            self,
            "DmsPeeringConnection",
            vpc_id=self._datasources_vpc.vpc_id,
            peer_vpc_id=self._dms_vpc.vpc_id,
            tags=[cdk.CfnTag(key="Name", value="pharmassist-dms-peering")],
        )

        # --- Routes in DataSources VPC (isolated subnets → DMS VPC CIDR) ---
        # DMS Serverless operates in the DMS VPC and needs return traffic
        # to reach back through the peering connection.
        for idx, subnet in enumerate(self._datasources_vpc.isolated_subnets):
            ec2.CfnRoute(
                self,
                f"DsToDefaultRoute{idx}",
                route_table_id=subnet.route_table.route_table_id,
                destination_cidr_block="10.200.0.0/16",
                vpc_peering_connection_id=self._vpc_peering.ref,
            )

        # --- Routes in DMS VPC (isolated subnets → DataSources VPC CIDR) ---
        # DMS Serverless needs a route to reach RDS in the DataSources VPC.
        for idx, subnet in enumerate(self._dms_vpc.isolated_subnets):
            ec2.CfnRoute(
                self,
                f"DefaultToDsRoute{idx}",
                route_table_id=subnet.route_table.route_table_id,
                destination_cidr_block="10.100.0.0/16",
                vpc_peering_connection_id=self._vpc_peering.ref,
            )

        # Enable DNS resolution on both sides of the peering connection.
        # CloudFormation does not natively support VPC Peering DNS options,
        # so we use AwsCustomResource to call ModifyVpcPeeringConnectionOptions.
        cr.AwsCustomResource(
            self,
            "PeeringDnsResolution",
            on_create=cr.AwsSdkCall(
                service="EC2",
                action="modifyVpcPeeringConnectionOptions",
                parameters={
                    "VpcPeeringConnectionId": self._vpc_peering.ref,
                    "AccepterPeeringConnectionOptions": {
                        "AllowDnsResolutionFromRemoteVpc": True,
                    },
                    "RequesterPeeringConnectionOptions": {
                        "AllowDnsResolutionFromRemoteVpc": True,
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    "PeeringDnsResolutionConfig"
                ),
            ),
            on_update=cr.AwsSdkCall(
                service="EC2",
                action="modifyVpcPeeringConnectionOptions",
                parameters={
                    "VpcPeeringConnectionId": self._vpc_peering.ref,
                    "AccepterPeeringConnectionOptions": {
                        "AllowDnsResolutionFromRemoteVpc": True,
                    },
                    "RequesterPeeringConnectionOptions": {
                        "AllowDnsResolutionFromRemoteVpc": True,
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    "PeeringDnsResolutionConfig"
                ),
            ),
            on_delete=cr.AwsSdkCall(
                service="EC2",
                action="modifyVpcPeeringConnectionOptions",
                parameters={
                    "VpcPeeringConnectionId": self._vpc_peering.ref,
                    "AccepterPeeringConnectionOptions": {
                        "AllowDnsResolutionFromRemoteVpc": False,
                    },
                    "RequesterPeeringConnectionOptions": {
                        "AllowDnsResolutionFromRemoteVpc": False,
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    "PeeringDnsResolutionConfig"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["ec2:ModifyVpcPeeringConnectionOptions"],
                    resources=["*"],
                ),
            ]),
        )

        # --- Security Group: Allow DMS to reach RDS on port 5432 (Task 3.3) ---
        # This SG lives in the DataSources VPC and allows ingress from the
        # DMS VPC CIDR (10.200.0.0/16) on TCP/5432. It must be attached
        # to the RDS instance (via DataSourcesStack update or manual association)
        # so that DMS Serverless ENIs in the DMS VPC can reach PostgreSQL.
        self._rds_dms_access_sg = ec2.SecurityGroup(
            self,
            "RdsDmsAccessSg",
            vpc=self._datasources_vpc,
            description="Allow DMS Serverless (DMS VPC) to reach RDS on port 5432",
            allow_all_outbound=False,  # No outbound needed for this SG
        )
        self._rds_dms_access_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4("10.200.0.0/16"),
            connection=ec2.Port.tcp(5432),
            description="DMS Serverless from DMS VPC to RDS PostgreSQL",
        )

        # Security Group for DMS Serverless ENIs in the DMS VPC.
        # DMS Serverless places ENIs in this VPC and needs outbound access
        # to reach RDS in the DataSources VPC (10.100.0.0/16) on port 5432.
        # This SG is referenced by the DMS Replication Config compute settings.
        self._dms_security_group = ec2.SecurityGroup(
            self,
            "DmsSecurityGroup",
            vpc=self._dms_vpc,
            description="Security group for DMS Serverless ENIs - allows outbound to RDS",
            allow_all_outbound=False,  # Restrict outbound to only what's needed
        )
        self._dms_security_group.add_egress_rule(
            peer=ec2.Peer.ipv4("10.100.0.0/16"),
            connection=ec2.Port.tcp(5432),
            description="DMS to RDS PostgreSQL via VPC Peering",
        )

    def _create_iam_roles(self) -> None:
        """Create IAM roles for DMS Serverless with least-privilege permissions.

        DmsServerlessRole:
        - Trust policy: dms.amazonaws.com
        - S3Access policy: PutObject/DeleteObject on raw/* objects,
          ListBucket/GetBucketLocation on bucket with prefix condition
        - SecretsAccess policy: GetSecretValue/DescribeSecret on RDS secret

        dms-vpc-role:
        - Service-linked role that DMS needs to manage ENIs in the VPC
        - Created only if it doesn't already exist in the account
        - Trust policy: dms.amazonaws.com
        - Managed policy: AmazonDMSVPCManagementRole
        """
        # Build resource ARNs for the policies
        bucket_arn = f"arn:aws:s3:::{self._lake_bucket_name}"
        bucket_objects_arn = f"arn:aws:s3:::{self._lake_bucket_name}/raw/*"

        # S3Access inline policy — two statements
        s3_access_policy = iam.PolicyDocument(
            statements=[
                # Statement 1: Object-level operations on raw/* prefix
                iam.PolicyStatement(
                    sid="DmsS3ObjectAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:PutObject",
                        "s3:DeleteObject",
                    ],
                    resources=[bucket_objects_arn],
                ),
                # Statement 2: Bucket-level operations with prefix condition
                iam.PolicyStatement(
                    sid="DmsS3BucketAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:ListBucket",
                        "s3:GetBucketLocation",
                    ],
                    resources=[bucket_arn],
                    conditions={
                        "StringLike": {
                            "s3:prefix": "raw/*",
                        },
                    },
                ),
            ]
        )

        # SecretsAccess inline policy — access to RDS credentials
        secrets_access_policy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    sid="DmsSecretsAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:DescribeSecret",
                    ],
                    resources=[self._rds_secret_arn],
                ),
            ]
        )

        # Create the DMS Serverless Role
        self._dms_role = iam.Role(
            self,
            "DmsServerlessRole",
            assumed_by=iam.ServicePrincipal("dms.us-east-1.amazonaws.com"),
            description="Role for DMS Serverless to access S3 lake bucket and RDS secret",
            inline_policies={
                "S3Access": s3_access_policy,
                "SecretsAccess": secrets_access_policy,
            },
        )

        # Import dms-vpc-role (service-linked role for DMS VPC management).
        # DMS requires this role to manage ENIs in the VPC.
        # The role already exists in the account (created by a previous deploy attempt).
        # We import it by name instead of creating it.
        self._dms_vpc_role = iam.Role.from_role_name(
            self,
            "DmsVpcRole",
            role_name="dms-vpc-role",
        )
        # Alias for dependency reference
        self._dms_vpc_role_attachment = self._dms_vpc_role

    def _create_dms_endpoints(self) -> None:
        """Create DMS Source and Target Endpoints.

        Source Endpoint:
        - Type: source, engine: postgres
        - Uses Secrets Manager integration for RDS credentials
        - Database: pharmassist_sources (the actual RDS database name from spec #1)
        - SSL mode: require (encrypted traffic between DMS and RDS)

        The endpoint uses SecretsManagerSecretId and SecretsManagerAccessRoleArn
        instead of explicit username/password, following AWS best practices for
        credential management with DMS.
        """
        # --- Source Endpoint (RDS PostgreSQL) — Task 5.1 ---
        self._source_endpoint = dms.CfnEndpoint(
            self,
            "DmsSourceEndpoint",
            endpoint_type="source",
            engine_name="postgres",
            database_name="pharmassist_sources",
            postgre_sql_settings=dms.CfnEndpoint.PostgreSqlSettingsProperty(
                secrets_manager_secret_id=self._rds_secret_arn,
                secrets_manager_access_role_arn=self._dms_role.role_arn,
            ),
            ssl_mode="require",
        )

        # --- Target Endpoint (S3 Parquet) — Task 5.2 ---
        # DMS writes Parquet files to the landing zone (raw/) in the lake bucket.
        # The service_access_role_arn is set at the S3Settings level as required
        # by the DMS S3 target endpoint configuration.
        self._target_endpoint = dms.CfnEndpoint(
            self,
            "DmsTargetEndpoint",
            endpoint_type="target",
            engine_name="s3",
            s3_settings=dms.CfnEndpoint.S3SettingsProperty(
                bucket_name=self._lake_bucket_name,
                bucket_folder="raw",
                service_access_role_arn=self._dms_role.role_arn,
                data_format="parquet",
                parquet_version="PARQUET_2_0",
                encoding_type="PLAIN_DICTIONARY",
                compression_type="NONE",
                add_column_name=True,
                timestamp_column_name="fecha_carga",
            ),
        )

        # --- DMS Replication Config (Serverless full-load) — Task 5.3 ---
        self._create_replication_config()

    def _create_replication_config(self) -> None:
        """Create DMS Serverless Replication Config with subnet group.

        Creates:
        - DMS Replication Subnet Group using isolated subnets from the DMS VPC
        - DMS Replication Config (Serverless) with full-load replication type

        The replication config uses:
        - Table mappings with 4 selection rules (one per schema)
        - Compute config: 1-4 DCU, single-AZ, in DMS VPC subnets
        - Security group allowing egress to RDS via VPC Peering
        """
        # --- DMS Replication Subnet Group ---
        # DMS Serverless needs a subnet group to know where to place ENIs.
        # We use the isolated subnets of the DMS VPC since DMS needs
        # outbound connectivity to reach RDS via VPC Peering.
        subnet_ids = [
            subnet.subnet_id for subnet in self._dms_vpc.isolated_subnets
        ]

        self._dms_subnet_group = dms.CfnReplicationSubnetGroup(
            self,
            "DmsReplicationSubnetGroup",
            replication_subnet_group_description=(
                "Subnet group for DMS Serverless in DMS VPC"
            ),
            subnet_ids=subnet_ids,
        )

        # Note: dms-vpc-role is imported (already exists), no dependency needed

        # --- Table Mappings ---
        # 4 selection rules: one per schema, selecting all tables (table-name="%")
        table_mappings = {
            "rules": [
                {
                    "rule-type": "selection",
                    "rule-id": "1",
                    "rule-name": "include-crm-interno",
                    "object-locator": {
                        "schema-name": "crm_interno",
                        "table-name": "%",
                    },
                    "rule-action": "include",
                },
                {
                    "rule-type": "selection",
                    "rule-id": "2",
                    "rule-name": "include-closeup",
                    "object-locator": {
                        "schema-name": "closeup",
                        "table-name": "%",
                    },
                    "rule-action": "include",
                },
                {
                    "rule-type": "selection",
                    "rule-id": "3",
                    "rule-name": "include-iqvia",
                    "object-locator": {
                        "schema-name": "iqvia",
                        "table-name": "%",
                    },
                    "rule-action": "include",
                },
                {
                    "rule-type": "selection",
                    "rule-id": "4",
                    "rule-name": "include-maestros",
                    "object-locator": {
                        "schema-name": "maestros",
                        "table-name": "%",
                    },
                    "rule-action": "include",
                },
            ]
        }

        # --- DMS Replication Config (Serverless) ---
        # Full-load replication: copies all data from source to target once.
        # No CDC (Change Data Capture) — the pipeline is re-run on schedule.
        self._replication_config = dms.CfnReplicationConfig(
            self,
            "DmsReplicationConfig",
            replication_config_identifier="pharmassist-full-load",
            replication_type="full-load",
            source_endpoint_arn=self._source_endpoint.ref,
            target_endpoint_arn=self._target_endpoint.ref,
            table_mappings=table_mappings,
            compute_config=dms.CfnReplicationConfig.ComputeConfigProperty(
                min_capacity_units=1,
                max_capacity_units=4,
                multi_az=False,
                replication_subnet_group_id=self._dms_subnet_group.ref,
                vpc_security_group_ids=[
                    self._dms_security_group.security_group_id
                ],
            ),
        )

    def _create_glue_job(self) -> None:
        """Create Glue ETL Job for Parquet → Iceberg conversion.

        Uploads the PySpark script as a CDK Asset to S3, imports the
        GlueEtlRole from spec #2 (DataLakeStack), and creates the Glue Job
        with the specified configuration.

        Configuration:
        - Worker type: G.1X (4 vCPU, 16 GB)
        - Number of workers: 2
        - Glue version: 4.0 (Spark 3.3 with native Iceberg support)
        - Timeout: 60 minutes
        - Job bookmark: DISABLED (full-load idempotent)
        - Max retries: 0 (Step Functions handles retries)
        - Default arguments: --lake_bucket, --datalake-formats=iceberg
        """
        # Upload PySpark script as CDK Asset to S3.
        # The asset is deployed to the CDK bootstrap bucket and referenced
        # by the Glue Job as its script location.
        script_asset = s3_assets.Asset(
            self,
            "GlueEtlScript",
            path=os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "scripts",
                "parquet_to_iceberg.py",
            ),
        )

        # Import GlueEtlRole from spec #2 (DataLakeStack) by name.
        # This role was created with permissions for S3 read/write on the
        # lake bucket and Glue Catalog access.
        glue_etl_role = iam.Role.from_role_name(
            self,
            "GlueEtlRole",
            role_name="GlueEtlRole",
        )

        # Create Glue ETL Job
        self._glue_job = glue.CfnJob(
            self,
            "GlueEtlJob",
            name="pharmassist-parquet-to-iceberg",
            role=glue_etl_role.role_arn,
            command=glue.CfnJob.JobCommandProperty(
                name="glueetl",
                python_version="3",
                script_location=script_asset.s3_object_url,
            ),
            glue_version="4.0",
            worker_type="G.1X",
            number_of_workers=2,
            timeout=60,
            max_retries=0,
            execution_property=glue.CfnJob.ExecutionPropertyProperty(
                max_concurrent_runs=1,
            ),
            default_arguments={
                "--lake_bucket": self._lake_bucket_name,
                "--datalake-formats": "iceberg",
                "--job-bookmark-option": "job-bookmark-disable",
                "--TempDir": f"s3://{self._lake_bucket_name}/tmp/glue/",
            },
        )

    def _create_state_machine(self) -> None:
        """Create Step Functions State Machine for pipeline orchestration.

        Orchestrates the ingestion pipeline: DMS replication → Glue ETL.
        Uses AWS SDK integrations to call DMS and Glue APIs directly.

        States:
        1. StartDmsReplication — starts DMS full-load replication
        2. WaitForDms — waits 60 seconds between status checks
        3. CheckDmsStatus — polls DMS replication status
        4. IsDmsComplete — choice: stopped→CheckDmsStopReason, failed→PipelineFailed
        5. CheckDmsStopReason — choice: FULL_LOAD_ONLY_FINISHED→StartGlueJob
        6. StartGlueJob — starts Glue ETL job run
        7. WaitForGlue — waits 30 seconds between status checks
        8. CheckGlueStatus — polls Glue job run status
        9. IsGlueComplete — choice: SUCCEEDED→PipelineSucceeded, FAILED/TIMEOUT/ERROR→PipelineFailed
        10. PipelineSucceeded — terminal success state
        11. PipelineFailed — terminal failure state

        The IAM role grants least-privilege access to DMS and Glue APIs.
        """
        # --- IAM Role for Step Functions ---
        self._sfn_role = iam.Role(
            self,
            "StepFunctionsRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            description="Role for Step Functions to orchestrate DMS and Glue",
            inline_policies={
                "DmsAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="SfnDmsAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "dms:StartReplication",
                                "dms:DescribeReplications",
                            ],
                            resources=[self._replication_config.attr_replication_config_arn],
                        ),
                    ]
                ),
                "GlueAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="SfnGlueAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "glue:StartJobRun",
                                "glue:GetJobRun",
                            ],
                            resources=[
                                f"arn:aws:glue:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:job/pharmassist-parquet-to-iceberg",
                            ],
                        ),
                    ]
                ),
            },
        )

        # --- ASL Definition ---
        replication_config_arn = self._replication_config.attr_replication_config_arn

        asl_definition = {
            "Comment": "PharmAssist Ingestion Pipeline: DMS → Glue ETL",
            "StartAt": "StartDmsReplication",
            "TimeoutSeconds": 3600,
            "States": {
                "StartDmsReplication": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::aws-sdk:databasemigration:startReplication",
                    "Parameters": {
                        "ReplicationConfigArn": replication_config_arn,
                        "StartReplicationType": "reload-target",
                    },
                    "ResultPath": "$.dmsStart",
                    "Next": "WaitForDms",
                    "Catch": [
                        {
                            "ErrorEquals": ["States.ALL"],
                            "Next": "PipelineFailed",
                        }
                    ],
                },
                "WaitForDms": {
                    "Type": "Wait",
                    "Seconds": 60,
                    "Next": "CheckDmsStatus",
                },
                "CheckDmsStatus": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::aws-sdk:databasemigration:describeReplications",
                    "Parameters": {
                        "Filters": [
                            {
                                "Name": "replication-config-arn",
                                "Values": [replication_config_arn],
                            }
                        ]
                    },
                    "ResultPath": "$.dmsStatus",
                    "Next": "IsDmsComplete",
                },
                "IsDmsComplete": {
                    "Type": "Choice",
                    "Choices": [
                        {
                            "Variable": "$.dmsStatus.Replications[0].Status",
                            "StringEquals": "stopped",
                            "Next": "CheckDmsStopReason",
                        },
                        {
                            "Variable": "$.dmsStatus.Replications[0].Status",
                            "StringEquals": "failed",
                            "Next": "PipelineFailed",
                        },
                    ],
                    "Default": "WaitForDms",
                },
                "CheckDmsStopReason": {
                    "Type": "Choice",
                    "Choices": [
                        {
                            "Variable": "$.dmsStatus.Replications[0].StopReason",
                            "StringEquals": "FULL_LOAD_ONLY_FINISHED",
                            "Next": "StartGlueJob",
                        }
                    ],
                    "Default": "PipelineFailed",
                },
                "StartGlueJob": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::aws-sdk:glue:startJobRun",
                    "Parameters": {
                        "JobName": "pharmassist-parquet-to-iceberg",
                        "Arguments": {
                            "--lake_bucket": self._lake_bucket_name,
                        },
                    },
                    "ResultPath": "$.glueStart",
                    "Next": "WaitForGlue",
                    "Catch": [
                        {
                            "ErrorEquals": ["States.ALL"],
                            "Next": "PipelineFailed",
                        }
                    ],
                },
                "WaitForGlue": {
                    "Type": "Wait",
                    "Seconds": 30,
                    "Next": "CheckGlueStatus",
                },
                "CheckGlueStatus": {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::aws-sdk:glue:getJobRun",
                    "Parameters": {
                        "JobName": "pharmassist-parquet-to-iceberg",
                        "RunId.$": "$.glueStart.JobRunId",
                    },
                    "ResultPath": "$.glueStatus",
                    "Next": "IsGlueComplete",
                },
                "IsGlueComplete": {
                    "Type": "Choice",
                    "Choices": [
                        {
                            "Variable": "$.glueStatus.JobRun.JobRunState",
                            "StringEquals": "SUCCEEDED",
                            "Next": "PipelineSucceeded",
                        },
                        {
                            "Or": [
                                {
                                    "Variable": "$.glueStatus.JobRun.JobRunState",
                                    "StringEquals": "FAILED",
                                },
                                {
                                    "Variable": "$.glueStatus.JobRun.JobRunState",
                                    "StringEquals": "TIMEOUT",
                                },
                                {
                                    "Variable": "$.glueStatus.JobRun.JobRunState",
                                    "StringEquals": "ERROR",
                                },
                            ],
                            "Next": "PipelineFailed",
                        },
                    ],
                    "Default": "WaitForGlue",
                },
                "PipelineSucceeded": {
                    "Type": "Succeed",
                },
                "PipelineFailed": {
                    "Type": "Fail",
                    "Error": "PipelineError",
                    "Cause": "DMS replication or Glue ETL job failed",
                },
            },
        }

        # --- State Machine ---
        self._state_machine = sfn.CfnStateMachine(
            self,
            "IngestionStateMachine",
            state_machine_name="pharmassist-ingestion-pipeline",
            state_machine_type="STANDARD",
            role_arn=self._sfn_role.role_arn,
            definition_string=json.dumps(asl_definition),
        )

    def _create_eventbridge_schedule(self) -> None:
        """Create EventBridge Scheduler Schedule and its IAM execution role.

        SchedulerRole (Task 8.2):
        - Trust policy: scheduler.amazonaws.com
        - Permission: states:StartExecution limited to the State Machine ARN

        Schedule (Task 8.1):
        - Name: pharmassist-ingestion-schedule
        - Expression: cron(0 2 * * ? *) — daily at 02:00 UTC
        - Timezone: UTC
        - Target: State Machine ARN with input {}
        - State: DISABLED (dev environment)
        - Retry policy: max 2 retries, 60 min max event age
        - Flexible time window: OFF
        """
        # --- SchedulerRole (Task 8.2) ---
        # IAM Role for EventBridge Scheduler to invoke Step Functions.
        # Trust policy allows scheduler.amazonaws.com to assume this role.
        # Permission is scoped to only StartExecution on the specific state machine.
        self._scheduler_role = iam.Role(
            self,
            "SchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            description="Role for EventBridge Scheduler to start Step Functions execution",
            inline_policies={
                "StartExecution": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="SchedulerStartExecution",
                            effect=iam.Effect.ALLOW,
                            actions=["states:StartExecution"],
                            resources=[self._state_machine.attr_arn],
                        ),
                    ]
                ),
            },
        )

        # --- EventBridge Scheduler Schedule (Task 8.1) ---
        # Determines the schedule state based on environment.
        # DISABLED in non-production environments to prevent unintended automatic executions.
        # Only ENABLED when environment is explicitly "prod" or "production".
        schedule_state = (
            "ENABLED"
            if self._tag_environment in ("prod", "production")
            else "DISABLED"
        )

        self._schedule = scheduler.CfnSchedule(
            self,
            "IngestionSchedule",
            name="pharmassist-ingestion-schedule",
            schedule_expression="cron(0 2 * * ? *)",
            schedule_expression_timezone="UTC",
            state=schedule_state,
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                mode="OFF",
            ),
            target=scheduler.CfnSchedule.TargetProperty(
                arn=self._state_machine.attr_arn,
                role_arn=self._scheduler_role.role_arn,
                input="{}",
                retry_policy=scheduler.CfnSchedule.RetryPolicyProperty(
                    maximum_retry_attempts=2,
                    maximum_event_age_in_seconds=3600,  # 60 minutes
                ),
            ),
        )

        # --- CloudFormation Outputs (Task 9.1) ---
        # Exactly 3 outputs as required by Requirement 10.6
        cdk.CfnOutput(
            self,
            "StateMachineArn",
            value=self._state_machine.attr_arn,
            description="ARN of the ingestion pipeline Step Functions State Machine",
        )

        cdk.CfnOutput(
            self,
            "GlueJobName",
            value="pharmassist-parquet-to-iceberg",
            description="Name of the Glue ETL Job for Parquet to Iceberg conversion",
        )

        cdk.CfnOutput(
            self,
            "ScheduleArn",
            value=self._schedule.attr_arn,
            description="ARN of the EventBridge Scheduler Schedule for daily ingestion",
        )
