"""Table definitions for the PharmAssist data lake.

Defines the dataclasses used to declare Iceberg table schemas and exports
domain-specific table lists used by DataLakeStack to register tables in Glue Catalog.
"""

from dataclasses import dataclass, field


@dataclass
class ColumnDef:
    """Column definition for a Glue/Iceberg table.

    Attributes:
        name: Column name (snake_case).
        type: Glue/Iceberg type string: "int", "bigint", "string",
              "boolean", "date", "timestamp", "decimal(p,s)".
        comment: Optional description of the column.
    """

    name: str
    type: str
    comment: str = ""


@dataclass
class TableDef:
    """Table definition for a Glue/Iceberg table.

    Attributes:
        name: Table name (snake_case, matches Glue table name).
        columns: Full list of columns including partition key columns.
        partition_keys: Column names used as partition keys (identity transform).
        description: Optional table description for Glue Catalog.
    """

    name: str
    columns: list[ColumnDef] = field(default_factory=list)
    partition_keys: list[str] = field(default_factory=list)
    description: str = ""


# Domain table lists — imported from sibling modules.
# These are populated once the domain files are created (tasks 1.2-1.5).
try:
    from table_definitions.crm_tables import CRM_TABLES
except ImportError:
    CRM_TABLES: list[TableDef] = []

try:
    from table_definitions.cup_tables import CUP_TABLES
except ImportError:
    CUP_TABLES: list[TableDef] = []

try:
    from table_definitions.iqvia_tables import IQVIA_TABLES
except ImportError:
    IQVIA_TABLES: list[TableDef] = []

try:
    from table_definitions.maestros_tables import MAESTROS_TABLES
except ImportError:
    MAESTROS_TABLES: list[TableDef] = []


# Aggregated dict of all tables by domain prefix.
# Used by DataLakeStack to iterate and register tables.
ALL_TABLES: dict[str, list[TableDef]] = {
    "crm": CRM_TABLES,
    "cup": CUP_TABLES,
    "iqvia": IQVIA_TABLES,
    "maestros": MAESTROS_TABLES,
}
