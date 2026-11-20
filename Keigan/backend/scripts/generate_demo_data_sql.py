"""Generates the Azure SQL (SQL Server) demo data scripts from Keigan's deterministic seed, for the DBA to run when the Azure database is ready.

Usage (from backend/):  .\\.venv\\Scripts\\python.exe scripts\\generate_demo_data_sql.py [output folder] [schema]
Default output: ../database/azure_sql/demo_data, default schema: keigan.

Writes the step files, 99_remove_demo_data.sql, run_all_demo_data.sql, MANIFEST.json and .gitignore. The step that is too large to commit
(04_sli_measurements.sql) is written too, but is listed in .gitignore; MANIFEST.json records its row count and SHA-256.
Tables tell the generator everything: columns, keys and order come from the entities, and tables are grouped by
backend/scripts/demo_data_sql/demo_data_plan.py. Demo data is never referenced from ../database/azure_sql/run_all.sql.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIRECTORY = BACKEND_DIRECTORY.parent / "database" / "azure_sql" / "demo_data"
DEFAULT_SCHEMA_NAME = "keigan"
REFERENCE_TIME = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)  # the demo world's "now"; fixed so regenerating never changes the files
RANDOM_SEED = 0


def _configure_environment_for_seed_run(temporary_directory: Path) -> None:
    """Set before any Keigan import (settings and the engine are cached on first use). The seed runs on a throw-away SQLite file in simulated mode."""
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{(temporary_directory / 'seed.db').as_posix()}",
            "DATA_DIRECTORY": str(temporary_directory / "data"),
            "ENVIRONMENT": "test",
            "AUTH_MODE": "local",
            "LLM_PROVIDER": "mock",
            "TELEMETRY_MODE": "simulated",
            "SERVICENOW_MODE": "simulated",
            "TEAMS_MODE": "simulated",
            "EMAIL_MODE": "simulated",
            "RUN_WORKERS_IN_PROCESS": "false",
            "LOG_LEVEL": "WARNING",
        }
    )
    os.environ.pop("DATABASE_SCHEMA", None)
    sys.path.insert(0, str(BACKEND_DIRECTORY))


def generate_demo_data_sql(output_directory: Path, schema_name: str) -> None:
    with tempfile.TemporaryDirectory(prefix="keigan-demo-seed-") as temporary_name:
        _configure_environment_for_seed_run(Path(temporary_name))
        from demo_data_sql.demo_data_plan import build_demo_data_plan
        from demo_data_sql.script_writer import GenerationSettings, render_demo_data_scripts, write_scripts
        from demo_data_sql.seeded_database import seed_and_read_rows
        from keigan.entities import all_entities  # noqa: F401  (registers every table)
        from keigan.entities.base_entity import EntityBase

        rows_by_table = asyncio.run(seed_and_read_rows(REFERENCE_TIME, RANDOM_SEED))
        plan = build_demo_data_plan(EntityBase.metadata, {name: len(rows) for name, rows in rows_by_table.items()})
        scripts = render_demo_data_scripts(plan, rows_by_table, GenerationSettings(schema_name, REFERENCE_TIME, RANDOM_SEED))
        write_scripts(output_directory, scripts)
        for file_name, text in scripts.items():
            print(f"wrote {file_name} ({len(text.encode('utf-8')):,} bytes)")


def main() -> None:
    output_directory = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIRECTORY
    schema_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SCHEMA_NAME
    generate_demo_data_sql(output_directory, schema_name)


if __name__ == "__main__":
    main()
