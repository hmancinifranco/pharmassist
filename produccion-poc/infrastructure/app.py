#!/usr/bin/env python3
"""
CDK Entry Point — ProduccionPocStack.

Loads AWS_ACCOUNT_ID and AWS_REGION from ../../.env (project root)
and instantiates the ProduccionPocStack with explicit environment.

Requirements: 5.6
"""

import os
from pathlib import Path

import aws_cdk as cdk
from dotenv import load_dotenv

from stacks import ProduccionPocStack

# Load .env from project root (two levels up from produccion-poc/infrastructure/)
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

app = cdk.App()

ProduccionPocStack(
    app,
    "ProduccionPocStack",
    env=cdk.Environment(
        account=os.environ["AWS_ACCOUNT_ID"],
        region=os.environ.get("AWS_REGION", "us-east-1"),
    ),
)

app.synth()
