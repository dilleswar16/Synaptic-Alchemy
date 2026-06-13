"""
Suite-wide safety guards.

This conftest runs before any test module imports the application, so the
environment below wins over the developer's ``.env`` (``corvin.core.config_loader``
calls ``load_dotenv(override=False)``, which never overwrites variables that
are already set).

Guards:

1. **Email delivery is force-disabled.** ``POST /investigations/`` auto-sends
   an RCA PDF email when ``CORVIN_EMAIL_TO`` is configured. With a real address
   in ``.env`` the suite would attempt live email delivery on every
   investigation test — hanging on restricted networks (retry backoff) and
   spamming real inboxes with fake test data.

2. **The suite runs against a throwaway SQLite database.** Without this, any
   test that reaches the global ``get_session()`` (prediction penalties,
   investigation persistence, SLO snapshots) reads from and WRITES TO the
   developer's live ``corvin.db`` — past runs polluted it with fixture
   services like ``order-service``. The temp DB is created fresh per run via
   ``Base.metadata.create_all`` and discarded with the temp directory.

3. **Disk learnings writes are no-oped.** ``penalize_prediction`` appends
   ``penalty-*.md`` files to ``knowledge/learnings/`` — content that is
   injected into every real investigation prompt. Tests must not write there.

Individual tests that exercise these paths intentionally still work: they use
``monkeypatch.setenv`` / explicit config, which take precedence per-test.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# ── 1. Email delivery — force-disabled for the whole suite ───────────────────
os.environ["CORVIN_EMAIL_ENABLED"] = "false"
os.environ["CORVIN_EMAIL_AUTO_SEND_ON_RCA"] = "false"
os.environ["CORVIN_EMAIL_TO"] = ""
os.environ["CORVIN_EMAIL_FROM"] = ""

# Demo seeding — keep the API lifespan inert under TestClient.
os.environ["CORVIN_DEMO_MODE"] = "false"

# ── 2. Throwaway SQLite database for the global session/engine ──────────────
_TEST_DB_DIR = tempfile.mkdtemp(prefix="corvin-test-db-")
os.environ["DB_BACKEND"] = "sqlite"
os.environ["CORVIN_SQLITE_PATH"] = str(Path(_TEST_DB_DIR) / "corvin-test.db")


# ── 3. Never write learning files to knowledge/learnings/ from tests ────────
@pytest.fixture(autouse=True, scope="session")
def _no_disk_learnings():
    from corvin.core.knowledge_loader import KnowledgeLoader

    original = KnowledgeLoader.append_learning

    def _append_to_tempdir(self, investigation_id: str, content: str) -> Path:
        path = Path(_TEST_DB_DIR) / f"learning-{investigation_id}.md"
        path.write_text(content, encoding="utf-8")
        return path

    KnowledgeLoader.append_learning = _append_to_tempdir
    yield
    KnowledgeLoader.append_learning = original
