"""Build a database at an older Alembic revision, fill it with rows the old code could have written, and render a revision's SQL Server script.

Migration tests use these so each one reads: old schema + old data -> upgrade -> assert.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
SQL_SERVER_URL = "mssql+aioodbc://@server.database.windows.net:1433/keigan?driver=ODBC+Driver+18+for+SQL+Server"
FILLER_BY_COLUMN_TYPE = {"INTEGER": 0, "BIGINT": 0, "BOOLEAN": 0, "FLOAT": 0.0}
TIMESTAMP_FILLER = "2026-01-01 00:00:00.000000"


def run_alembic(*arguments: str, database_file: Path | None = None, sql_server: bool = False) -> str:
    """Run ``alembic <arguments>`` from backend/ against a SQLite file, or against SQL Server's dialect offline (``--sql`` only)."""
    child_environment = {key: value for key, value in os.environ.items() if key not in ("DATABASE_URL", "DATABASE_SCHEMA")}
    if sql_server:
        child_environment.update(DATABASE_URL=SQL_SERVER_URL, DATABASE_SCHEMA="keigan")
    else:
        assert database_file is not None
        child_environment["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_file.as_posix()}"
    completed = subprocess.run([sys.executable, "-m", "alembic", *arguments], cwd=BACKEND_DIRECTORY, env=child_environment, capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def sql_server_script(from_revision: str, to_revision: str) -> str:
    """The T-SQL Alembic renders for ``from_revision:to_revision`` (never executed by the tests: there is no SQL Server here)."""
    return run_alembic("upgrade", f"{from_revision}:{to_revision}", "--sql", sql_server=True)


def database_at(directory: Path, revision: str) -> Path:
    database_file = directory / "old.db"
    run_alembic("upgrade", revision, database_file=database_file)
    return database_file


def insert_row(connection: sqlite3.Connection, table: str, **values: Any) -> None:
    """Insert one row, filling every NOT NULL column without a default so a test names only the columns it cares about."""
    row = dict(values)
    for _, name, column_type, not_null, default, primary_key in connection.execute(f"PRAGMA table_info({table})"):
        if name in row or default is not None or not not_null:
            continue
        if primary_key and column_type in ("INTEGER", "BIGINT"):
            continue
        row[name] = TIMESTAMP_FILLER if "DATETIME" in column_type.upper() else FILLER_BY_COLUMN_TYPE.get(column_type.upper(), "{}" if column_type.upper() == "JSON" else "x")
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(row.values()))


def column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
