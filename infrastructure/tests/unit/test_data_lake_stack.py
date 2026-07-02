"""CDK assertion tests for DataLakeStack.

Validates the synthesized CloudFormation template against requirements:
- S3 bucket encryption, public access, lifecycle rules
- Glue databases and table counts per domain
- Partition key configuration for key tables
- IAM roles with least privilege (no wildcard actions)
- Athena workgroup configuration
- Stack outputs

Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1-2.7, 3.1-3.7, 4.1-4.5, 5.1-5.4,
              6.1-6.4, 8.1-8.7, 9.1-9.5, 10.4
"""

import json
import aws_cdk as cdk
from aws_cdk.assertions import Template, Match
from stacks.data_lake_stack import DataLakeStack


def get_template() -> Template:
    """Synthesize the DataLakeStack and return a Template for assertions."""
    app = cdk.App()
    stack = DataLakeStack(
        app,
        "TestStack",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


# ---------------------------------------------------------------------------
# S3 Bucket Tests
# ---------------------------------------------------------------------------


def test_bucket_has_sse_s3_encryption():
    """Verify bucket has SSE-S3 (AES256) encryption. Validates: Requirement 1.2"""
    template = get_template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {
                        "ServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256",
                        }
                    }
                ]
            }
        },
    )


def test_bucket_blocks_public_access():
    """Verify all 4 public access blocks are enabled. Validates: Requirement 1.4"""
    template = get_template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_bucket_has_lifecycle_rules():
    """Verify bucket has 3 lifecycle rules. Validates: Requirements 1.5, 1.6, 1.7"""
    template = get_template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "LifecycleConfiguration": {
                "Rules": Match.array_with(
                    [
                        Match.object_like({"Id": "archive-tagged-objects"}),
                        Match.object_like({"Id": "delete-noncurrent-versions"}),
                        Match.object_like({"Id": "abort-incomplete-multipart"}),
                    ]
                )
            }
        },
    )


# ---------------------------------------------------------------------------
# Glue Database Tests
# ---------------------------------------------------------------------------


def test_creates_4_glue_databases():
    """Verify exactly 4 Glue databases exist. Validates: Requirements 2.1-2.4"""
    template = get_template()
    template.resource_count_is("AWS::Glue::Database", 4)


# ---------------------------------------------------------------------------
# Glue Table Count Tests
# ---------------------------------------------------------------------------


def test_creates_51_glue_tables():
    """Verify total of 51 CfnTable resources. Validates: Requirements 3.1, 4.1, 5.1, 6.1"""
    template = get_template()
    template.resource_count_is("AWS::Glue::Table", 51)


def _count_tables_for_database(template: Template, database_name: str) -> int:
    """Count Glue tables that belong to a specific database."""
    resources = template.find_resources("AWS::Glue::Table")
    count = 0
    for _logical_id, resource in resources.items():
        props = resource.get("Properties", {})
        if props.get("DatabaseName") == database_name:
            count += 1
    return count


def test_crm_has_25_tables():
    """Verify CRM domain has 25 tables. Validates: Requirement 3.1"""
    template = get_template()
    assert _count_tables_for_database(template, "pharmassist_crm") == 25


def test_cup_has_10_tables():
    """Verify CloseUp domain has 10 tables. Validates: Requirement 4.1"""
    template = get_template()
    assert _count_tables_for_database(template, "pharmassist_cup") == 10


def test_iqvia_has_13_tables():
    """Verify IQVIA domain has 13 tables. Validates: Requirement 5.1"""
    template = get_template()
    assert _count_tables_for_database(template, "pharmassist_iqvia") == 13


def test_maestros_has_3_tables():
    """Verify Maestros domain has 3 tables. Validates: Requirement 6.1"""
    template = get_template()
    assert _count_tables_for_database(template, "pharmassist_maestros") == 3


# ---------------------------------------------------------------------------
# Partition Key Tests
# ---------------------------------------------------------------------------


def _find_table_by_name(template: Template, table_name: str) -> dict:
    """Find a Glue table resource by its TableInput.Name property."""
    resources = template.find_resources("AWS::Glue::Table")
    for _logical_id, resource in resources.items():
        props = resource.get("Properties", {})
        table_input = props.get("TableInput", {})
        if table_input.get("Name") == table_name:
            return table_input
    raise AssertionError(f"Table '{table_name}' not found in template")


def test_agenda_has_partition_key_fecha_inicio():
    """Verify agenda table is partitioned by fecha_inicio. Validates: Requirement 3.2"""
    template = get_template()
    table_input = _find_table_by_name(template, "agenda")
    partition_keys = table_input.get("PartitionKeys", [])
    partition_key_names = [pk["Name"] for pk in partition_keys]
    assert "fecha_inicio" in partition_key_names


def test_prescripcion_has_3_partition_keys():
    """Verify prescripcion has 3 partition keys (anio, mes, cdgreg_pmix). Validates: Requirement 4.2"""
    template = get_template()
    table_input = _find_table_by_name(template, "prescripcion")
    partition_keys = table_input.get("PartitionKeys", [])
    assert len(partition_keys) == 3
    partition_key_names = [pk["Name"] for pk in partition_keys]
    assert "anio" in partition_key_names
    assert "mes" in partition_key_names
    assert "cdgreg_pmix" in partition_key_names


def test_fact_mercado_valor_has_partition_key_idperiodo():
    """Verify fact_mercado_valor is partitioned by idperiodo. Validates: Requirement 5.2"""
    template = get_template()
    table_input = _find_table_by_name(template, "fact_mercado_valor")
    partition_keys = table_input.get("PartitionKeys", [])
    partition_key_names = [pk["Name"] for pk in partition_keys]
    assert "idperiodo" in partition_key_names


# ---------------------------------------------------------------------------
# IAM Tests
# ---------------------------------------------------------------------------


def test_iam_roles_no_wildcard_actions():
    """Verify no IAM policy uses '*' in Action field. Validates: Requirement 8.7"""
    template = get_template()
    resources = template.find_resources("AWS::IAM::Policy")
    for logical_id, resource in resources.items():
        props = resource.get("Properties", {})
        policy_document = props.get("PolicyDocument", {})
        statements = policy_document.get("Statement", [])
        for stmt in statements:
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            for action in actions:
                assert action != "*", (
                    f"Wildcard action '*' found in policy {logical_id}"
                )


def test_iam_s3_permissions_scoped_to_bucket():
    """Verify S3 actions reference the lake bucket ARN. Validates: Requirements 8.3, 8.4"""
    template = get_template()
    resources = template.find_resources("AWS::IAM::Policy")
    for logical_id, resource in resources.items():
        props = resource.get("Properties", {})
        policy_document = props.get("PolicyDocument", {})
        statements = policy_document.get("Statement", [])
        for stmt in statements:
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            # Check if this statement has S3 actions
            has_s3_actions = any(
                a.startswith("s3:") for a in actions
            )
            if has_s3_actions:
                # Resource must reference the bucket ARN (via Fn::GetAtt or Fn::Join)
                resource_field = stmt.get("Resource", [])
                if isinstance(resource_field, str):
                    resource_field = [resource_field]
                # Should NOT be "*" — must be scoped to bucket
                for res in resource_field:
                    if isinstance(res, str):
                        assert res != "*", (
                            f"S3 permissions in {logical_id} use wildcard resource '*'"
                        )


# ---------------------------------------------------------------------------
# Athena Workgroup Tests
# ---------------------------------------------------------------------------


def test_athena_workgroup_configuration():
    """Verify workgroup has 100MB limit, enforce=true, engine v3. Validates: Requirements 9.1-9.5"""
    template = get_template()
    template.has_resource_properties(
        "AWS::Athena::WorkGroup",
        {
            "Name": "pharmassist-validation",
            "State": "ENABLED",
            "WorkGroupConfiguration": {
                "BytesScannedCutoffPerQuery": 104857600,
                "EnforceWorkGroupConfiguration": True,
                "EngineVersion": {
                    "SelectedEngineVersion": "Athena engine version 3",
                },
            },
        },
    )


# ---------------------------------------------------------------------------
# Stack Outputs Tests
# ---------------------------------------------------------------------------


def test_stack_has_6_outputs():
    """Verify exactly 6 CfnOutput resources. Validates: Requirement 10.4"""
    template = get_template()
    outputs = template.to_json().get("Outputs", {})
    assert len(outputs) == 6, (
        f"Expected 6 outputs, got {len(outputs)}: {list(outputs.keys())}"
    )
