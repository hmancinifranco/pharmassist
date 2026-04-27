"""Create a demo APM user in the Cognito User Pool.

Usage:
    source .env
    python scripts/create-demo-user.py

Requires env vars:
    USER_POOL_ID          — Cognito User Pool ID (from CDK output)
    DEMO_USER_EMAIL       — Email for the demo user
    DEMO_USER_PASSWORD    — Password for the demo user
    AWS_REGION            — AWS region (default: us-east-1)
    DEMO_USER_APM_ID      — APM name stored in custom:apm_id (default: "Demo APM")
"""

import os
import sys

import boto3
from botocore.exceptions import ClientError

USER_POOL_ID = os.environ.get("USER_POOL_ID", "").strip().strip('"').strip("'")
EMAIL = os.environ.get("DEMO_USER_EMAIL", "").strip().strip('"').strip("'")
PASSWORD = os.environ.get("DEMO_USER_PASSWORD", "").strip().strip('"').strip("'")
REGION = os.environ.get("AWS_REGION", "us-east-1").strip().strip('"').strip("'")
APM_ID = os.environ.get("DEMO_USER_APM_ID", "Demo APM").strip().strip('"').strip("'")


def main() -> None:
    if not USER_POOL_ID:
        print("ERROR: USER_POOL_ID env var is required (from CDK output).")
        sys.exit(1)
    if not EMAIL:
        print("ERROR: DEMO_USER_EMAIL env var is required.")
        sys.exit(1)
    if not PASSWORD:
        print("ERROR: DEMO_USER_PASSWORD env var is required.")
        sys.exit(1)

    client = boto3.client("cognito-idp", region_name=REGION)

    # 1. Create user (suppress welcome email)
    try:
        client.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=EMAIL,
            UserAttributes=[
                {"Name": "email", "Value": EMAIL},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:apm_id", "Value": APM_ID},
            ],
            MessageAction="SUPPRESS",
        )
        print(f"✅ User created: {EMAIL}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "UsernameExistsException":
            print(f"ℹ️  User already exists: {EMAIL}")
        else:
            raise

    # 2. Set permanent password (skip FORCE_CHANGE_PASSWORD state)
    client.admin_set_user_password(
        UserPoolId=USER_POOL_ID,
        Username=EMAIL,
        Password=PASSWORD,
        Permanent=True,
    )
    print("✅ Password set (permanent).")

    # 3. Ensure custom:apm_id is set
    client.admin_update_user_attributes(
        UserPoolId=USER_POOL_ID,
        Username=EMAIL,
        UserAttributes=[
            {"Name": "custom:apm_id", "Value": APM_ID},
        ],
    )
    print(f"✅ custom:apm_id = \"{APM_ID}\"")
    print(f"\nDemo user ready. Login with: {EMAIL} / <DEMO_USER_PASSWORD>")


if __name__ == "__main__":
    main()
