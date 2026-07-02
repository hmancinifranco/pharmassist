#!/usr/bin/env python3
"""CDK app entry point — IngestionStack only.

Deploys the ingestion pipeline: VPC Peering, DMS Serverless, Glue ETL,
Step Functions orchestration, and EventBridge schedule.

Usage:
    cdk deploy --app '.venv/bin/python3 app_ingestion.py' --profile $AWS_PROFILE
"""
import os
import aws_cdk as cdk
from dotenv import load_dotenv
from stacks.ingestion_stack import IngestionStack

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# --- Read environment variables ---
account = os.environ.get("AWS_ACCOUNT_ID")
region = os.environ.get("AWS_REGION", "us-east-1")
tag_project = os.environ.get("TAG_PROJECT", "PharmAssist")
tag_environment = os.environ.get("TAG_ENVIRONMENT", "dev")
tag_owner = os.environ.get("TAG_OWNER", "team")

rds_secret_arn = os.environ.get("RDS_SECRET_ARN")
datasources_vpc_id = os.environ.get("DATASOURCES_VPC_ID")
lake_bucket_name = os.environ.get("LAKE_BUCKET_NAME")
glue_db_crm = os.environ.get("GLUE_DB_CRM")
glue_db_cup = os.environ.get("GLUE_DB_CUP")
glue_db_iqvia = os.environ.get("GLUE_DB_IQVIA")
glue_db_maestros = os.environ.get("GLUE_DB_MAESTROS")

# --- Validate required parameters ---
_required_vars = {
    "RDS_SECRET_ARN": rds_secret_arn,
    "DATASOURCES_VPC_ID": datasources_vpc_id,
    "LAKE_BUCKET_NAME": lake_bucket_name,
    "GLUE_DB_CRM": glue_db_crm,
    "GLUE_DB_CUP": glue_db_cup,
    "GLUE_DB_IQVIA": glue_db_iqvia,
    "GLUE_DB_MAESTROS": glue_db_maestros,
}

for var_name, var_value in _required_vars.items():
    if not var_value:
        raise ValueError(f"Missing required env var: {var_name}")

# --- Instantiate the stack ---
app = cdk.App()

IngestionStack(
    app,
    "IngestionStack",
    env=cdk.Environment(
        account=account,
        region=region,
    ),
    rds_secret_arn=rds_secret_arn,
    datasources_vpc_id=datasources_vpc_id,
    lake_bucket_name=lake_bucket_name,
    glue_database_names={
        "crm": glue_db_crm,
        "cup": glue_db_cup,
        "iqvia": glue_db_iqvia,
        "maestros": glue_db_maestros,
    },
    tag_project=tag_project,
    tag_environment=tag_environment,
    tag_owner=tag_owner,
)

app.synth()
