"""
ProduccionPocStack — CDK Stack for PharmAssist POC with Aurora PostgreSQL.

Provisions: VPC, Aurora Serverless v2, Secrets Manager, Security Groups.
Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7, 5.8
"""

import os
import shutil
import subprocess

import aws_cdk as cdk
from aws_cdk import (
    ILocalBundling,
    RemovalPolicy,
    Tags,
    aws_ec2 as ec2,
    aws_lambda as _lambda,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
from jsii import implements


@implements(ILocalBundling)
class LocalBundling:
    """Local bundling: pip install + copy source to output directory."""

    def __init__(self, source_path: str):
        self.source_path = source_path

    def try_bundle(self, output_dir: str, *, image, **kwargs) -> bool:
        """Install deps and copy source locally (no Docker needed)."""
        import sys

        pip_cmd = [sys.executable, "-m", "pip"]

        # Install requirements into output dir
        req_file = os.path.join(self.source_path, "requirements.txt")
        if os.path.exists(req_file):
            subprocess.check_call(
                pip_cmd
                + [
                    "install",
                    "--quiet",
                    "--disable-pip-version-check",
                    "-r",
                    req_file,
                    "-t",
                    output_dir,
                    "--platform",
                    "manylinux2014_x86_64",
                    "--only-binary=:all:",
                    "--python-version",
                    "3.12",
                ]
            )
        # Copy source files
        for item in os.listdir(self.source_path):
            s = os.path.join(self.source_path, item)
            d = os.path.join(output_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        return True


class ProduccionPocStack(cdk.Stack):
    """CDK Stack for PharmAssist POC: Aurora PostgreSQL Serverless v2 + VPC."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Tags via CDK (Req 5.8) ---
        tag_project = os.environ.get("TAG_PROJECT", "PharmAssist")
        tag_environment = os.environ.get("TAG_ENVIRONMENT", "dev")
        tag_owner = os.environ.get("TAG_OWNER", "pharmassist-team")

        Tags.of(self).add("Project", tag_project)
        Tags.of(self).add("Environment", tag_environment)
        Tags.of(self).add("Owner", tag_owner)

        # --- VPC (Req 5.1) ---
        # Private subnets in 2 AZs with NAT Gateway for egress
        self.vpc = ec2.Vpc(
            self,
            "PocVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                # Public subnet required for NAT Gateway placement
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
            ],
        )

        # --- Security Groups (Req 5.4) ---
        # SG for Lambda/Agent that needs access to Aurora
        self.lambda_sg = ec2.SecurityGroup(
            self,
            "LambdaSg",
            vpc=self.vpc,
            description="Security group for Lambda functions accessing Aurora",
            allow_all_outbound=True,
        )

        # SG for Aurora — ingress only from Lambda SG on port 5432
        self.aurora_sg = ec2.SecurityGroup(
            self,
            "AuroraSg",
            vpc=self.vpc,
            description="Security group for Aurora PostgreSQL cluster",
            allow_all_outbound=False,
        )
        self.aurora_sg.add_ingress_rule(
            peer=self.lambda_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow PostgreSQL access from Lambda SG",
        )

        # --- Secrets Manager (Req 5.3) ---
        # Auto-generated credentials for Aurora cluster
        self.db_secret = secretsmanager.Secret(
            self,
            "AuroraSecret",
            description="Auto-generated credentials for PharmAssist POC Aurora cluster",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "pharmassist_admin"}',
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=30,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # --- Aurora PostgreSQL Serverless v2 (Req 5.2) ---
        # Engine: PostgreSQL 15.8, Serverless v2 scaling 0.5-4 ACU
        self.aurora_cluster = rds.DatabaseCluster(
            self,
            "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_8,
            ),
            credentials=rds.Credentials.from_secret(self.db_secret),
            default_database_name="pharmassist_poc",
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            security_groups=[self.aurora_sg],
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=4,
            writer=rds.ClusterInstance.serverless_v2("Writer"),
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
            storage_encrypted=True,
        )

        # --- Seed Data Lambda (Req 5.5, 5.6) ---
        # Bundle dependencies from requirements.txt using local pip install
        seed_lambda_path = os.path.join(
            os.path.dirname(__file__), "..", "lambda", "seed"
        )
        self.seed_lambda = _lambda.Function(
            self,
            "SeedDataFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="seed_handler.handler",
            code=_lambda.Code.from_asset(
                seed_lambda_path,
                bundling=cdk.BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                    local=LocalBundling(seed_lambda_path),
                ),
            ),
            timeout=cdk.Duration.minutes(15),
            memory_size=3008,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            security_groups=[self.lambda_sg],
            environment={
                "DB_SECRET_ARN": self.db_secret.secret_arn,
                "DB_NAME": "pharmassist_poc",
            },
        )

        # Grant Lambda permission to read Aurora credentials
        self.db_secret.grant_read(self.seed_lambda)

        # --- CfnOutputs (Req 5.6) ---
        cdk.CfnOutput(
            self,
            "AuroraEndpoint",
            value=self.aurora_cluster.cluster_endpoint.hostname,
            description="Aurora PostgreSQL cluster endpoint",
            export_name=f"{self.stack_name}-AuroraEndpoint",
        )
        cdk.CfnOutput(
            self,
            "AuroraSecretArn",
            value=self.db_secret.secret_arn,
            description="ARN of the Aurora credentials secret",
            export_name=f"{self.stack_name}-AuroraSecretArn",
        )
        cdk.CfnOutput(
            self,
            "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID for the POC infrastructure",
            export_name=f"{self.stack_name}-VpcId",
        )
        cdk.CfnOutput(
            self,
            "SeedLambdaArn",
            value=self.seed_lambda.function_arn,
            description="ARN of the seed data Lambda function",
            export_name=f"{self.stack_name}-SeedLambdaArn",
        )
