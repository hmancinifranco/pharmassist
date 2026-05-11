#!/usr/bin/env python3
"""CDK app entry point — DataSourcesStack only.

Use this when deploying only the DataSourcesStack without needing
to bundle the PharmAssistStack Lambda (which requires pip).

Usage:
    cdk deploy --app '.venv/bin/python3 app_datasources.py' --profile $AWS_PROFILE
"""
import os
import aws_cdk as cdk
from dotenv import load_dotenv
from stacks.data_sources_stack import DataSourcesStack

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = cdk.App()

DataSourcesStack(
    app,
    "DataSourcesStack",
    env=cdk.Environment(
        account=os.environ.get("AWS_ACCOUNT_ID"),
        region=os.environ.get("AWS_REGION", "us-east-1"),
    ),
    tag_project=os.environ.get("TAG_PROJECT", "PharmAssist"),
    tag_environment=os.environ.get("TAG_ENVIRONMENT", "dev"),
    tag_owner=os.environ.get("TAG_OWNER", "team"),
)

app.synth()
