"""Runs the demo seed once in a throw-away SQLite database and reads back every row it wrote, table by table.

The caller must set ``DATABASE_URL`` (and the other environment settings) BEFORE this module runs: Keigan caches its settings and engine.
Unlike ``python -m keigan.seed_main``, a failing seed step stops the run: a generator must never publish half of the demo data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


async def _run_seed_steps() -> None:
    from keigan.config.database_config import create_database_schema, open_session
    from keigan.seed.foundation_seed import SeedContext, seed_demo_applications, seed_simulation_world
    from keigan.seed_main import discover_seed_step_modules

    await create_database_schema()
    seed_context = SeedContext()
    async with open_session() as session:
        await seed_demo_applications(session, seed_context)
    async with open_session() as session:
        await seed_simulation_world(session, seed_context)
    for seed_step_module in discover_seed_step_modules():
        async with open_session() as session:
            await seed_step_module.seed(session, seed_context)  # type: ignore[attr-defined]


async def _read_all_rows() -> dict[str, list[dict[str, Any]]]:
    from sqlalchemy import select

    from keigan.config.database_config import open_session
    from keigan.entities import all_entities  # noqa: F401  (registers every table)
    from keigan.entities.base_entity import EntityBase

    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    async with open_session() as session:
        for table in EntityBase.metadata.sorted_tables:
            result = await session.execute(select(table).order_by(*table.primary_key.columns))
            rows_by_table[table.name] = [dict(row._mapping) for row in result.all()]
    return rows_by_table


async def seed_and_read_rows(reference_time: datetime, random_seed: int) -> dict[str, list[dict[str, Any]]]:
    """Seed with a fixed clock and fixed randomness (see ``deterministic_seed_environment``), then return the rows of every table."""
    from keigan.config.database_config import get_database_engine
    from keigan.seed.deterministic_seed_environment import deterministic_seed_environment

    try:
        with deterministic_seed_environment(reference_time, random_seed):
            await _run_seed_steps()
        return await _read_all_rows()
    finally:
        await get_database_engine().dispose()  # releases the SQLite file so the temporary folder can be deleted on Windows
