"""Builds (or rebuilds) the memory of every completed investigation (spec 34, 4.5). Safe to run again: each entry is replaced in place, and a hidden entry stays hidden.

Run it once after the revision that creates the memory tables is applied (earlier investigations have no entry until then), and after changing the similarity catalogue's key kinds.

Usage (from backend/):  .\\.venv\\Scripts\\python.exe scripts\\rebuild_incident_memory.py
It reads the same settings as the application (DATABASE_URL and the rest of the environment), so point it at the database you mean.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import Investigation
from keigan.entities.status_values import InvestigationStatus
from keigan.services.incident_memory_builder import IncidentMemoryBuilder

logger = logging.getLogger("rebuild_incident_memory")
BATCH_SIZE = 100


async def rebuild() -> dict[str, int]:
    counts = {"built": 0, "skipped": 0, "missing": 0}
    async with open_session() as session:
        investigation_ids = list((await session.scalars(select(Investigation.investigation_id).where(Investigation.investigation_status == InvestigationStatus.COMPLETED).order_by(Investigation.created_at))).all())
    for start in range(0, len(investigation_ids), BATCH_SIZE):
        async with open_session() as session:  # one transaction per batch: a failure loses at most the batch, and a rerun continues
            builder = IncidentMemoryBuilder(session)
            for investigation_id in investigation_ids[start:start + BATCH_SIZE]:
                counts[(await builder.refresh_entry(investigation_id))["status"]] += 1
        logger.info("Rebuilt %d of %d", min(start + BATCH_SIZE, len(investigation_ids)), len(investigation_ids))
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    counts = asyncio.run(rebuild())
    logger.info("Done: %d built, %d skipped, %d missing", counts["built"], counts["skipped"], counts["missing"])


if __name__ == "__main__":
    main()
