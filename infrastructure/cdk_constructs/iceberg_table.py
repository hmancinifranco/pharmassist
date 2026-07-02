"""Helper function to register Iceberg tables in Glue Data Catalog.

Provides a reusable function that transforms a TableDef into a fully configured
CfnTable with Iceberg format, reducing boilerplate across 51 table registrations.
"""

import aws_cdk as cdk
from aws_cdk import aws_glue as glue, aws_s3 as s3

from table_definitions import TableDef


def register_iceberg_table(
    scope: cdk.Stack,
    database_name: str,
    bucket: s3.IBucket,
    domain_prefix: str,
    table_def: TableDef,
) -> glue.CfnTable:
    """Register an Iceberg table in Glue Data Catalog.

    Creates a CfnTable with full Iceberg configuration including:
    - Column definitions with types
    - Iceberg InputFormat/OutputFormat/SerDe
    - table_type=ICEBERG, format-version=2
    - metadata_location pointing to S3
    - Partition keys (if any) as identity transforms

    Args:
        scope: CDK stack scope for resource creation.
        database_name: Name of the Glue database to register the table in.
        bucket: S3 bucket where table data will be stored.
        domain_prefix: Domain prefix for S3 path (e.g., "crm", "cup").
        table_def: Table definition with columns, partition keys, and metadata.

    Returns:
        The created CfnTable resource.
    """
    table_name = table_def.name
    location = f"s3://{bucket.bucket_name}/{domain_prefix}/{table_name}/"
    metadata_location = f"s3://{bucket.bucket_name}/{domain_prefix}/{table_name}/metadata/"

    # Build column list (excluding partition key columns)
    partition_key_names = set(table_def.partition_keys)
    storage_columns = [
        glue.CfnTable.ColumnProperty(
            name=col.name,
            type=col.type,
            comment=col.comment if col.comment else None,
        )
        for col in table_def.columns
        if col.name not in partition_key_names
    ]

    # Build partition keys (None if no partition keys defined)
    partition_keys = None
    if table_def.partition_keys:
        col_type_map = {col.name: col.type for col in table_def.columns}
        partition_keys = [
            glue.CfnTable.ColumnProperty(
                name=pk,
                type=col_type_map[pk],
            )
            for pk in table_def.partition_keys
        ]

    return glue.CfnTable(
        scope,
        f"{domain_prefix}-{table_name}-table",
        catalog_id=cdk.Aws.ACCOUNT_ID,
        database_name=database_name,
        table_input=glue.CfnTable.TableInputProperty(
            name=table_name,
            description=table_def.description,
            table_type="EXTERNAL_TABLE",
            parameters={
                "table_type": "ICEBERG",
                "format-version": "2",
                "metadata_location": metadata_location,
            },
            storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                location=location,
                input_format="org.apache.iceberg.mr.hive.HiveIcebergInputFormat",
                output_format="org.apache.iceberg.mr.hive.HiveIcebergOutputFormat",
                serde_info=glue.CfnTable.SerdeInfoProperty(
                    serialization_library="org.apache.iceberg.mr.hive.HiveIcebergSerDe",
                ),
                columns=storage_columns,
            ),
            partition_keys=partition_keys,
        ),
    )
