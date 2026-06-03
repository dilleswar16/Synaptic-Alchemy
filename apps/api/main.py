"""
Corvin FastAPI application entry point.

Start the dev server with:
    uvicorn apps.api.main:app --reload --port 8000
"""

from __future__ import annotations

# Inject OS trust store BEFORE any Azure SDK imports to handle corporate proxies.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import asyncio
import logging
import os
import warnings

# LiteLLM's ResponseAPIUsage Pydantic model doesn't include `video_tokens`
# which Azure AI Foundry now returns in Responses API usage objects.
# The serialization still works correctly — suppress the noise.
warnings.filterwarnings(
    "ignore",
    message=".*ResponseAPIUsage.*",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*Pydantic serializer warnings.*",
    category=UserWarning,
)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routes import investigations, triggers
from apps.api.routes.ai_features import router as ai_features_router
from apps.api.routes.applications import router as applications_router
from apps.api.routes.corvin_agent import router as corvin_router
from apps.api.routes.slo import router as slo_router
from apps.api.routes.validations import router as validations_router
from apps.teams.router import router as teams_router
from corvin.core.config_loader import get_env, load_config
from corvin.storage.db import get_engine, get_session, is_sqlite
from corvin.storage.models import Base
from corvin.slo.snapshot import run_forever as slo_run_forever
from corvin.triggers.predictive import PredictiveMonitor

_log = logging.getLogger("corvin.main")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Auto-create all tables when running in SQLite mode (no Alembic required)."""
    predictive_task: asyncio.Task | None = None
    if is_sqlite():
        Base.metadata.create_all(get_engine())

    # ── Demo data seeding ─────────────────────────────────────────────────
    # Default changed to "false" — onboard applications via the UI instead.
    if os.getenv("CORVIN_DEMO_MODE", "false").strip().lower() == "true":
        try:
            from apps.api.seed_demo import ensure_demo_data
            db = next(get_session())
            try:
                seeded = ensure_demo_data(db)
                if seeded:
                    _log.info("Demo mode: database seeded with sample fleet data.")
            finally:
                db.close()
        except Exception as _seed_err:  # noqa: BLE001
            _log.warning("Demo seed failed (non-fatal): %s", _seed_err)
    slo_task: asyncio.Task | None = None
    try:
        policy = load_config("policies/investigation", get_env())
        if policy.get("predictive_background_enabled", True):
            interval_seconds = int(policy.get("predictive_interval_seconds", 300))
            predictive_task = asyncio.create_task(
                PredictiveMonitor().run_forever(interval_seconds=interval_seconds)
            )
        slo_interval = int(policy.get("slo_snapshot_interval_seconds", 3600))
        slo_task = asyncio.create_task(slo_run_forever(interval_seconds=slo_interval))
    except Exception:
        predictive_task = None
        if slo_task is None:
            try:
                slo_task = asyncio.create_task(slo_run_forever())
            except Exception:
                pass
    yield
    for task in (predictive_task, slo_task):
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Corvin API",
    description="Azure-native investigation platform – V1 control plane",
    version="0.1.0",
    lifespan=_lifespan,
)

_cors_origins_raw = os.environ.get("CORVIN_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176,http://localhost:5177").strip()
_allow_all_origins = _cors_origins_raw == "*"
_allowed_origins = (
    ["*"]
    if _allow_all_origins
    else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"] if _allow_all_origins else ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"] if _allow_all_origins else ["Content-Type", "Authorization"],
)

app.include_router(investigations.router, prefix="/investigations", tags=["investigations"])
app.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
app.include_router(teams_router, prefix="/teams", tags=["teams"])
app.include_router(corvin_router, prefix="/corvin", tags=["corvin"])
app.include_router(applications_router, prefix="/applications", tags=["applications"])
app.include_router(slo_router, prefix="/slo", tags=["slo"])
app.include_router(validations_router, prefix="/validations", tags=["validations"])
app.include_router(ai_features_router, prefix="/ai", tags=["ai-features"])


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": "corvin-api", "version": "0.1.0"}
