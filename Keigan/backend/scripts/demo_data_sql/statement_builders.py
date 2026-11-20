"""The T-SQL for demo data: guarded inserts and key-based removal. Columns, keys and identity columns all come from the entity metadata.

Insert (per block of at most ``ROWS_PER_INSERT_BLOCK`` rows, each block is one ``GO`` batch): the rows go into a temporary staging table
that has the real table's column types, then ONE ``INSERT ... SELECT ... WHERE NOT EXISTS`` copies every row whose key is missing.
So each row is guarded on its own key and a partly finished earlier run is completed, never duplicated or failed.
A staging table (instead of a multi-row ``VALUES`` inside ``INSERT ... SELECT``) keeps the column types of the real table, so an all-NULL
column cannot be typed as ``int`` by SQL Server.

Identity columns (``sli_measurement``): the generated id is NOT inserted. Forcing explicit ids into a table that already holds rows could collide
with them, so the row is matched by its unique constraint (the natural key) and SQL Server assigns the id.

Removal: only seeded rows, by primary key. For an identity table the rows are matched by the FIRST column of its unique constraint (the parent
key, for example the SLI id) with the short list of distinct values, because one literal per row would be hundreds of thousands. That is only
correct when every row under those parent keys is demo data, which holds because the parent rows are demo rows removed by the same script.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Column, Table, UniqueConstraint

from demo_data_sql.demo_data_errors import DemoDataSqlError
from demo_data_sql.sql_literals import render_literal

ROWS_PER_INSERT_BLOCK = 500  # below the 1000 row limit of one VALUES list
KEYS_PER_DELETE = 500
STAGING_TABLE = "#demo_rows"


def _quote(identifier: str) -> str:
    return f"[{identifier}]"


def _qualified(schema_name: str, table: Table) -> str:
    return f"{_quote(schema_name)}.{_quote(table.name)}"


def _column_list(columns: Sequence[Column]) -> str:
    return ", ".join(_quote(column.name) for column in columns)


def _natural_key_columns(table: Table) -> list[Column]:
    """The unique constraint that identifies a row of an identity table without its generated id."""
    unique_constraints = sorted((constraint for constraint in table.constraints if isinstance(constraint, UniqueConstraint)), key=lambda constraint: str(constraint.name))
    if not unique_constraints:
        raise DemoDataSqlError(
            f"Table {table.name} has a generated id and no unique constraint, so a demo row cannot be recognised on a second run. "
            "Add a unique constraint on its natural key (with a migration) or exclude the table in demo_data_plan.py."
        )
    return list(unique_constraints[0].columns)


def _key_columns(table: Table) -> list[Column]:
    """What identifies a row for the NOT EXISTS guard."""
    return _natural_key_columns(table) if table.autoincrement_column is not None else list(table.primary_key.columns)


def _inserted_columns(table: Table) -> list[Column]:
    return [column for column in table.columns if column is not table.autoincrement_column]


def _values_row(row: Mapping[str, Any], columns: Sequence[Column]) -> str:
    return "(" + ", ".join(render_literal(row[column.name], column) for column in columns) + ")"


def _insert_block(table: Table, rows: Sequence[Mapping[str, Any]], schema_name: str) -> str:
    columns = _inserted_columns(table)
    column_list = _column_list(columns)
    target = _qualified(schema_name, table)
    guard = " AND ".join(f"[existing].{_quote(column.name)} = [source].{_quote(column.name)}" for column in _key_columns(table))
    values = ",\n".join(f"    {_values_row(row, columns)}" for row in rows)
    selected = ", ".join(f"[source].{_quote(column.name)}" for column in columns)
    return (
        f"DROP TABLE IF EXISTS {STAGING_TABLE};\n"
        f"SELECT TOP (0) {column_list} INTO {STAGING_TABLE} FROM {target};\n"
        f"INSERT INTO {STAGING_TABLE} ({column_list}) VALUES\n{values};\n"
        f"INSERT INTO {target} ({column_list})\n"
        f"SELECT {selected} FROM {STAGING_TABLE} AS [source]\n"
        f"WHERE NOT EXISTS (SELECT 1 FROM {target} AS [existing] WHERE {guard});\n"
        f"DROP TABLE {STAGING_TABLE};"
    )


def build_insert_blocks(table: Table, rows: Sequence[Mapping[str, Any]], schema_name: str, rows_per_block: int = ROWS_PER_INSERT_BLOCK) -> list[str]:
    """Guarded insert batches for one table; empty when the seed wrote no rows into it."""
    return [_insert_block(table, rows[start : start + rows_per_block], schema_name) for start in range(0, len(rows), rows_per_block)]


def _key_tuples(table: Table, rows: Sequence[Mapping[str, Any]]) -> tuple[list[Column], list[tuple[Any, ...]]]:
    """The columns a DELETE matches on and the distinct value combinations to match."""
    if table.autoincrement_column is not None:
        parent_key_column = _natural_key_columns(table)[0]
        distinct_values = sorted({row[parent_key_column.name] for row in rows}, key=lambda value: render_literal(value, parent_key_column))
        return [parent_key_column], [(value,) for value in distinct_values]
    key_columns = list(table.primary_key.columns)
    return key_columns, [tuple(row[column.name] for column in key_columns) for row in rows]


def _delete_statement(table: Table, schema_name: str, key_columns: Sequence[Column], keys: Sequence[tuple[Any, ...]]) -> str:
    target = _qualified(schema_name, table)
    if len(key_columns) == 1:
        column = key_columns[0]
        literals = ", ".join(render_literal(key[0], column) for key in keys)
        return f"DELETE FROM {target} WHERE {_quote(column.name)} IN ({literals});"
    alternatives = " OR ".join("(" + " AND ".join(f"{_quote(column.name)} = {render_literal(value, column)}" for column, value in zip(key_columns, key, strict=True)) + ")" for key in keys)
    return f"DELETE FROM {target} WHERE {alternatives};"


def build_removal_blocks(
    tables_in_insert_order: Sequence[Table], rows_by_table: Mapping[str, Sequence[Mapping[str, Any]]], schema_name: str, keys_per_delete: int = KEYS_PER_DELETE
) -> list[str]:
    """One transaction that deletes the seeded rows, children before parents; mentions only tables that have seeded rows."""
    blocks = ["SET XACT_ABORT ON;\nBEGIN TRANSACTION;"]
    for table in reversed(tables_in_insert_order):
        rows = rows_by_table.get(table.name, ())
        if not rows:
            continue
        key_columns, keys = _key_tuples(table, rows)
        blocks.extend(_delete_statement(table, schema_name, key_columns, keys[start : start + keys_per_delete]) for start in range(0, len(keys), keys_per_delete))
    blocks.append("COMMIT TRANSACTION;")
    return blocks
