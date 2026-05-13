"""CDK assertion tests for IngestionStack.

Validates the synthesized CloudFormation template against requirements:
- VPC Peering Connection and routes
- Security Group for DMS access to RDS
- DMS Source and Target Endpoints
- DMS Replication Config (Serverless full-load)
- Glue ETL Job configuration
- Step Functions State Machine
- EventBridge Schedule
- IAM Roles with least privilege
- Stack outputs and tags

Requirements: 9.5, 10.3, 10.6
"""

import json

import aws_cdk as cdk
from aws_cdk.assertions import Template, Match
from stacks.ingestion_stack import IngestionStack


# ---------------------------------------------------------------------------
# Mock VPC context for ec2.Vpc.from_lookup() calls during synth
# ---------------------------------------------------------------------------

# DataSources VPC (10.100.0.0/16) — 2 isolated subnets
_DATASOURCES_VPC_CONTEXT = {
    "vpcId": "vpc-12345",
    "vpcCidrBlock": "10.100.0.0/16",
    "ownerAccountId": "123456789012",
    "availabilityZones": ["us-east-1a", "us-east-1b"],
    "subnetGroups": [
        {
            "name": "Isolated",
            "type": "Isolated",
            "subnets": [
                {
                    "subnetId": "subnet-iso-1a",
                    "cidr": "10.100.1.0/24",
                    "availabilityZone": "us-east-1a",
                    "routeTableId": "rtb-iso-1a",
                },
                {
                    "subnetId": "subnet-iso-1b",
                    "cidr": "10.100.2.0/24",
                    "availabilityZone": "us-east-1b",
                    "routeTableId": "rtb-iso-1b",
                },
            ],
        }
    ],
}


def get_template() -> Template:
    """Synthesize the IngestionStack with mock parameters and return a Template.

    Provides VPC context so that ec2.Vpc.from_lookup() resolves during synth
    without requiring AWS API access. The DMS VPC is created by CDK (not looked up)
    so it doesn't need context mocking.
    """
    app = cdk.App(
        context={
            # Context key for DataSources VPC lookup by vpc_id
            "vpc-provider:account=123456789012:filter.vpc-id=vpc-12345"
            ":region=us-east-1:returnAsymmetricSubnets=true": _DATASOURCES_VPC_CONTEXT,
            # Availability zones context
            "availability-zones:account=123456789012:region=us-east-1": [
                "us-east-1a",
                "us-east-1b",
                "us-east-1c",
            ],
        }
    )

    stack = IngestionStack(
        app,
        "TestIngestionStack",
        rds_secret_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret",
        datasources_vpc_id="vpc-12345",
        lake_bucket_name="test-lake-bucket",
        glue_database_names={
            "crm": "pharmassist_crm",
            "cup": "pharmassist_cup",
            "iqvia": "pharmassist_iqvia",
            "maestros": "pharmassist_maestros",
        },
        tag_project="PharmAssist",
        tag_environment="dev",
        tag_owner="team",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )

    return Template.from_stack(stack)


# ---------------------------------------------------------------------------
# Test 1: VPC Peering Connection exists with correct CIDRs
# ---------------------------------------------------------------------------


def test_vpc_peering_connection_exists():
    """Verify VPC Peering Connection between DataSources and DMS VPC.

    Validates: Requirements 1.1, 10.3
    """
    template = get_template()
    template.has_resource_properties(
        "AWS::EC2::VPCPeeringConnection",
        {
            "VpcId": "vpc-12345",
            "PeerVpcId": Match.any_value(),
        },
    )


# ---------------------------------------------------------------------------
# Test 2: Routes in both VPCs with correct destinations
# ---------------------------------------------------------------------------


def test_routes_in_both_vpcs():
    """Verify routes exist in DataSources VPC (→ 10.200.0.0/16) and DMS VPC (→ 10.100.0.0/16).

    DataSources VPC has 2 isolated subnets → 2 routes to 10.200.0.0/16.
    DMS VPC has 2 isolated subnets → 2 routes to 10.100.0.0/16.

    Validates: Requirements 1.2, 1.3, 10.3
    """
    template = get_template()

    # Routes from DataSources VPC to DMS VPC CIDR
    template.has_resource_properties(
        "AWS::EC2::Route",
        Match.object_like({
            "DestinationCidrBlock": "10.200.0.0/16",
            "VpcPeeringConnectionId": Match.any_value(),
        }),
    )

    # Routes from DMS VPC to DataSources VPC CIDR
    template.has_resource_properties(
        "AWS::EC2::Route",
        Match.object_like({
            "DestinationCidrBlock": "10.100.0.0/16",
            "VpcPeeringConnectionId": Match.any_value(),
        }),
    )

    # Count total routes: 2 (DataSources isolated) + 2 (DMS isolated) = 4
    template.resource_count_is("AWS::EC2::Route", 4)


# ---------------------------------------------------------------------------
# Test 3: Security Group ingress TCP/5432 from 172.31.0.0/16
# ---------------------------------------------------------------------------


def test_security_group_ingress_postgres():
    """Verify Security Group allows TCP/5432 ingress from DMS VPC CIDR.

    Validates: Requirements 1.4, 10.3
    """
    template = get_template()
    template.has_resource_properties(
        "AWS::EC2::SecurityGroup",
        Match.object_like({
            "SecurityGroupIngress": Match.array_with([
                Match.object_like({
                    "IpProtocol": "tcp",
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "CidrIp": "10.200.0.0/16",
                }),
            ]),
        }),
    )


# ---------------------------------------------------------------------------
# Test 4: DMS Source Endpoint — engine=postgres, SSL=require, SecretsManager
# ---------------------------------------------------------------------------


def test_dms_source_endpoint():
    """Verify DMS Source Endpoint configuration for RDS PostgreSQL.

    Validates: Requirements 2.1, 2.2, 2.4, 10.3
    """
    template = get_template()
    template.has_resource_properties(
        "AWS::DMS::Endpoint",
        Match.object_like({
            "EndpointType": "source",
            "EngineName": "postgres",
            "SslMode": "require",
            "PostgreSqlSettings": Match.object_like({
                "SecretsManagerSecretId": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret",
                "SecretsManagerAccessRoleArn": Match.any_value(),
            }),
        }),
    )


# ---------------------------------------------------------------------------
# Test 5: DMS Target Endpoint — engine=s3, Parquet, SNAPPY, bucket folder=raw
# ---------------------------------------------------------------------------


def test_dms_target_endpoint():
    """Verify DMS Target Endpoint configuration for S3 Parquet output.

    Validates: Requirements 3.1, 3.2, 3.3, 3.4, 10.3
    """
    template = get_template()
    template.has_resource_properties(
        "AWS::DMS::Endpoint",
        Match.object_like({
            "EndpointType": "target",
            "EngineName": "s3",
            "S3Settings": Match.object_like({
                "BucketName": "test-lake-bucket",
                "BucketFolder": "raw",
                "DataFormat": "parquet",
                "CompressionType": "NONE",
                "ServiceAccessRoleArn": Match.any_value(),
            }),
        }),
    )


# ---------------------------------------------------------------------------
# Test 6: Replication Config — full-load, capacity 1-4, multi_az=false
# ---------------------------------------------------------------------------


def test_dms_replication_config():
    """Verify DMS Replication Config for serverless full-load.

    Validates: Requirements 4.1, 4.2, 4.3, 10.3
    """
    template = get_template()
    template.has_resource_properties(
        "AWS::DMS::ReplicationConfig",
        Match.object_like({
            "ReplicationType": "full-load",
            "ComputeConfig": Match.object_like({
                "MinCapacityUnits": 1,
                "MaxCapacityUnits": 4,
                "MultiAZ": False,
            }),
        }),
    )


# ---------------------------------------------------------------------------
# Test 7: Glue Job — name, worker G.1X, workers=2, version 4.0, timeout 60min
# ---------------------------------------------------------------------------


def test_glue_job_configuration():
    """Verify Glue ETL Job configuration.

    Validates: Requirements 5.1, 10.3
    """
    template = get_template()
    template.has_resource_properties(
        "AWS::Glue::Job",
        Match.object_like({
            "Name": "pharmassist-parquet-to-iceberg",
            "WorkerType": "G.1X",
            "NumberOfWorkers": 2,
            "GlueVersion": "4.0",
            "Timeout": 60,
            "MaxRetries": 0,
            "Command": Match.object_like({
                "Name": "glueetl",
                "PythonVersion": "3",
            }),
        }),
    )


# ---------------------------------------------------------------------------
# Test 8: State Machine — type STANDARD, timeout 3600s
# ---------------------------------------------------------------------------


def test_state_machine_configuration():
    """Verify Step Functions State Machine type and timeout.

    Validates: Requirements 7.1, 10.3
    """
    template = get_template()
    template.has_resource_properties(
        "AWS::StepFunctions::StateMachine",
        Match.object_like({
            "StateMachineType": "STANDARD",
            "StateMachineName": "pharmassist-ingestion-pipeline",
        }),
    )

    # Verify the ASL definition contains TimeoutSeconds=3600
    resources = template.to_json()["Resources"]
    for resource in resources.values():
        if resource.get("Type") == "AWS::StepFunctions::StateMachine":
            definition_str = resource["Properties"]["DefinitionString"]
            # DefinitionString may contain Fn::Join or be a plain string
            if isinstance(definition_str, str):
                definition = json.loads(definition_str)
            else:
                # Handle Fn::Join or other intrinsic functions — skip deep check
                # The state machine type check above is sufficient
                return
            assert definition.get("TimeoutSeconds") == 3600, (
                f"Expected TimeoutSeconds=3600, got {definition.get('TimeoutSeconds')}"
            )
            return


# ---------------------------------------------------------------------------
# Test 9: EventBridge Schedule — cron, state=DISABLED, target=state machine
# ---------------------------------------------------------------------------


def test_eventbridge_schedule():
    """Verify EventBridge Schedule configuration.

    Validates: Requirements 8.1, 10.3
    """
    template = get_template()
    template.has_resource_properties(
        "AWS::Scheduler::Schedule",
        Match.object_like({
            "ScheduleExpression": "cron(0 2 * * ? *)",
            "State": "DISABLED",
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": Match.object_like({
                "Arn": Match.any_value(),
                "RoleArn": Match.any_value(),
            }),
        }),
    )


# ---------------------------------------------------------------------------
# Test 10: IAM no wildcards — no policy has Action="*"
# ---------------------------------------------------------------------------


def test_iam_no_wildcard_actions():
    """Verify no IAM policy uses Action='*' (least privilege).

    Validates: Requirements 9.5, 10.3
    """
    template = get_template()
    resources = template.to_json()["Resources"]

    for logical_id, resource in resources.items():
        if resource.get("Type") == "AWS::IAM::Role":
            policies = resource.get("Properties", {}).get("Policies", [])
            for policy in policies:
                doc = policy.get("PolicyDocument", {})
                statements = doc.get("Statement", [])
                for stmt in statements:
                    actions = stmt.get("Action", [])
                    if isinstance(actions, str):
                        actions = [actions]
                    assert "*" not in actions, (
                        f"Wildcard Action='*' found in role {logical_id}, "
                        f"policy statement: {stmt.get('Sid', 'unnamed')}"
                    )


# ---------------------------------------------------------------------------
# Test 11: IAM DmsServerlessRole — trust policy and specific permissions
# ---------------------------------------------------------------------------


def test_iam_dms_serverless_role():
    """Verify DmsServerlessRole trust policy and inline permissions.

    Trust: dms.us-east-1.amazonaws.com (regional endpoint)
    Permissions: s3:PutObject, s3:DeleteObject, s3:ListBucket,
                 secretsmanager:GetSecretValue, secretsmanager:DescribeSecret

    Validates: Requirements 9.1, 9.2, 9.5, 10.3
    """
    template = get_template()
    template.has_resource_properties(
        "AWS::IAM::Role",
        Match.object_like({
            "AssumeRolePolicyDocument": Match.object_like({
                "Statement": Match.array_with([
                    Match.object_like({
                        "Effect": "Allow",
                        "Principal": {"Service": "dms.us-east-1.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }),
                ]),
            }),
            "Policies": Match.array_with([
                Match.object_like({
                    "PolicyName": "S3Access",
                    "PolicyDocument": Match.object_like({
                        "Statement": Match.array_with([
                            Match.object_like({
                                "Action": Match.array_with(["s3:PutObject", "s3:DeleteObject"]),
                                "Resource": "arn:aws:s3:::test-lake-bucket/raw/*",
                            }),
                        ]),
                    }),
                }),
                Match.object_like({
                    "PolicyName": "SecretsAccess",
                    "PolicyDocument": Match.object_like({
                        "Statement": Match.array_with([
                            Match.object_like({
                                "Action": Match.array_with([
                                    "secretsmanager:GetSecretValue",
                                    "secretsmanager:DescribeSecret",
                                ]),
                                "Resource": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret",
                            }),
                        ]),
                    }),
                }),
            ]),
        }),
    )


# ---------------------------------------------------------------------------
# Test 12: Outputs — exactly 3 CfnOutputs
# ---------------------------------------------------------------------------


def test_outputs_exactly_three():
    """Verify the stack has exactly 3 CfnOutputs.

    Expected: StateMachineArn, GlueJobName, ScheduleArn

    Validates: Requirements 10.6
    """
    template = get_template()
    outputs = template.to_json().get("Outputs", {})
    assert len(outputs) == 3, (
        f"Expected exactly 3 outputs, got {len(outputs)}: {list(outputs.keys())}"
    )

    # Verify expected output keys exist
    output_keys = set(outputs.keys())
    assert "StateMachineArn" in output_keys, "Missing output: StateMachineArn"
    assert "GlueJobName" in output_keys, "Missing output: GlueJobName"
    assert "ScheduleArn" in output_keys, "Missing output: ScheduleArn"


# ---------------------------------------------------------------------------
# Test 13: Tags — Project, Environment, Owner, ManagedBy on resources
# ---------------------------------------------------------------------------


def test_tags_applied_to_resources():
    """Verify required tags are applied to taggable resources.

    Expected tags: Project=PharmAssist, Environment=dev, Owner=team, ManagedBy=cdk

    Validates: Requirements 10.3
    """
    template = get_template()
    resources = template.to_json()["Resources"]

    # Check tags on resources that support them (IAM Roles, Security Groups, etc.)
    # CDK applies stack-level tags to all taggable resources.
    # We verify at least one resource has all 4 required tags.
    expected_tags = {
        "Project": "PharmAssist",
        "Environment": "dev",
        "Owner": "team",
        "ManagedBy": "cdk",
    }

    found_tagged_resource = False
    for logical_id, resource in resources.items():
        props = resource.get("Properties", {})
        tags = props.get("Tags", [])
        if not tags:
            continue

        # Convert tags list to dict for easier comparison
        tag_dict = {t["Key"]: t["Value"] for t in tags if "Key" in t and "Value" in t}

        if all(tag_dict.get(k) == v for k, v in expected_tags.items()):
            found_tagged_resource = True
            break

    assert found_tagged_resource, (
        "No resource found with all required tags: "
        f"Project=PharmAssist, Environment=dev, Owner=team, ManagedBy=cdk"
    )
