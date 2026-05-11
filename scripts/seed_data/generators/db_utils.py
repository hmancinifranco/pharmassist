"""Database utilities for bulk inserts via SSM tunnel.

Uses psycopg2.extras.execute_values which is 10-50x faster than executemany
because it sends all values in a single query instead of one roundtrip per row.
This is critical when inserting through an SSM port-forwarding tunnel with ~10ms latency.
"""
from psycopg2.extras import execute_values


def bulk_insert(cur, sql_template, data, page_size=1000):
    """Bulk insert using execute_values.

    Args:
        cur: psycopg2 cursor
        sql_template: SQL with VALUES %s placeholder, e.g.:
            "INSERT INTO schema.table (col1, col2) VALUES %s"
        data: list of tuples
        page_size: rows per batch (default 1000)
    """
    if not data:
        return 0
    execute_values(cur, sql_template, data, page_size=page_size)
    return len(data)
