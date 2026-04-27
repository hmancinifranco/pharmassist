#!/usr/bin/env python3
"""CDK app entry point for PharmAssist infrastructure."""
import os
import aws_cdk as cdk
from dotenv import load_dotenv
from stacks.pharmassist_stack import PharmAssistStack

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = cdk.App()

PharmAssistStack(
    app,
    "PharmAssistStack",
    env=cdk.Environment(
        account=os.environ.get("AWS_ACCOUNT_ID"),
        region=os.environ.get("AWS_REGION", "us-east-1"),
    ),
    tag_project=os.environ.get("TAG_PROJECT", "PharmAssist"),
    tag_environment=os.environ.get("TAG_ENVIRONMENT", "dev"),
    tag_owner=os.environ.get("TAG_OWNER", "team"),
)

app.synth()
