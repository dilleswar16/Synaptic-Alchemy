"""Demo data: ``python -m keigan.seed_main`` (idempotent; safe to run repeatedly).

Seed steps are discovered automatically: every module ``keigan/seed/<name>_seed.py`` (except ``foundation_seed``)
that defines ``SEED_ORDER: int`` and ``async def seed(session, seed_context)`` runs in ascending ``SEED_ORDER``.
Suggested order: knowledge 10 · alerts and SLOs 20 · investigations 30 · intelligence and notifications 40.
Limit steps with ``SEED_STEPS=knowledge_seed,investigation_seed`` (environment variable). A failing step is logged and skipped.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import pkgutil

import keigan.seed
from keigan.config.database_config import create_database_schema, open_session
from keigan.config.logging_config import configure_logging
from keigan.config.settings import get_settings
from keigan.seed.foundation_seed import SeedContext, seed_demo_applications, seed_simulation_world

logger = logging.getLogger(__name__)


def discover_seed_step_modules() -> list[object]:
    requested_step_names = {name.strip() for name in os.environ.get("SEED_STEPS", "").split(",") if name.strip()}
    seed_step_modules = []
    for module_information in pkgutil.iter_modules(keigan.seed.__path__):
        module_name = module_information.name
        if not module_name.endswith("_seed") or module_name == "foundation_seed":
            continue
        if requested_step_names and module_name not in requested_step_names:
            continue
        try:
            seed_step_module = importlib.import_module(f"keigan.seed.{module_name}")
        except Exception:  # noqa: BLE001
            logger.exception("Seed step %s could not be imported; skipping it", module_name)
            continue
        if hasattr(seed_step_module, "seed"):
            seed_step_modules.append(seed_step_module)
    return sorted(seed_step_modules, key=lambda seed_step_module: getattr(seed_step_module, "SEED_ORDER", 100))


async def run_seed() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, use_json_format=False)
    if settings.environment == "prod":
        raise SystemExit("Refusing to seed demo data in production.")
    await create_database_schema()
    seed_context = SeedContext()
    async with open_session() as session:
        await seed_demo_applications(session, seed_context)
    async with open_session() as session:
        await seed_simulation_world(session, seed_context)
    for seed_step_module in discover_seed_step_modules():
        step_name = seed_step_module.__name__.rsplit(".", 1)[-1]
        try:
            async with open_session() as session:
                await seed_step_module.seed(session, seed_context)  # type: ignore[attr-defined]
            logger.info("Seed step %s completed", step_name)
        except Exception:  # noqa: BLE001
            logger.exception("Seed step %s failed; continuing with the next step", step_name)
    logger.info("Seed complete: %s applications, %s services", len(seed_context.application_ids_by_code), len(seed_context.service_ids_by_key))


if __name__ == "__main__":
    asyncio.run(run_seed())
