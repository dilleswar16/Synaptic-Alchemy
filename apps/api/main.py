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

from corvin.core.logging_config import setup_logging

# Structured logging must be configured before any module logs at import time.
setup_logging()

from apps.api.errors import install_error_handlers
from apps.api.middleware import ApiVersionMiddleware, RequestContextMiddleware
from apps.api.routes import investigations, triggers
from apps.api.routes.ai_features import router as ai_features_router
from apps.api.routes.applications import router as applications_router
from apps.api.routes.chaos import router as chaos_router
from apps.api.routes.config import router as config_router
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

# ── Startup env var validation ────────────────────────────────────────────────
# Required for production; warnings only in dev so the server still starts.
_REQUIRED_ENV_VARS: list[tuple[str, str]] = [
    ("AZURE_OPENAI_API_KEY",   "LLM API key — investigations will fail without this"),
    ("LITELLM_ENDPOINT",       "LiteLLM / Azure AI Foundry endpoint for the LLM backend"),
    ("DATABASE_URL",           "Postgres connection string — only required when not using SQLite"),
]
_OPTIONAL_ENV_VARS: list[tuple[str, str]] = [
    ("CORVIN_PRODUCT_NAME",    "Branding: product display name (default: Corvin)"),
    ("CORVIN_LOGO_URL",        "Branding: logo URL served to the frontend"),
    ("CORVIN_PRIMARY_COLOR",   "Branding: primary accent colour (default: #6366f1)"),
    ("CORVIN_ALLOWED_ORIGINS", "CORS: comma-separated allowed origins (default: localhost ports)"),
    ("CORVIN_LOG_LEVEL",       "Logging: DEBUG | INFO | WARNING | ERROR (default: INFO)"),
    ("CORVIN_LOG_FORMAT",      "Logging: json | text (default: json)"),
]


def _validate_env() -> None:
    """Log warnings for missing env vars at startup. Never raises."""
    is_sqlite_mode = os.environ.get("DATABASE_URL", "").startswith("sqlite") or not os.environ.get("DATABASE_URL")
    for var, description in _REQUIRED_ENV_VARS:
        if var == "DATABASE_URL" and is_sqlite_mode:
            continue  # SQLite path — DATABASE_URL not required
        if not os.environ.get(var, "").strip():
            _log.warning("Missing env var %s: %s", var, description)
    for var, description in _OPTIONAL_ENV_VARS:
        if not os.environ.get(var, "").strip():
            _log.debug("Optional env var not set — using default: %s (%s)", var, description)

    # TD-H7 guard: PredictiveMonitor and the SLO monitor run inside each API
    # worker. Until leader election lands, more than one worker means duplicate
    # background DB writes and duplicate LLM calls.
    for worker_var in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        raw_workers = os.environ.get(worker_var, "").strip()
        if raw_workers.isdigit() and int(raw_workers) > 1:
            _log.warning(
                "%s=%s — background monitors (predictive, SLO) run per-worker and will "
                "duplicate work. Run a single API worker until leader election is "
                "implemented (TD-H7), or disable monitors on extra workers.",
                worker_var, raw_workers,
            )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Auto-create all tables when running in SQLite mode (no Alembic required)."""
    _validate_env()
    predictive_task: asyncio.Task | None = None
    if is_sqlite():
        Base.metadata.create_all(get_engine())

    # ── Demo data seeding ─────────────────────────────────────────────────
    # Default changed to "false" — onboard applications via the UI instead.
    if os.getenv("CORVIN_DEMO_MODE", "false").strip().lower() == "true":
        try:
            from apps.api.seed_demo import ensure_demo_data
            with get_session() as db:
                seeded = ensure_demo_data(db)
            if seeded:
                _log.info("Demo mode: database seeded with sample fleet data.")
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

install_error_handlers(app)

_cors_origins_raw = os.environ.get("CORVIN_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176,http://localhost:5177").strip()
_allow_all_origins = _cors_origins_raw == "*"
if _allow_all_origins:
    # TD-H6 guard: wildcard disables CORS protection entirely.
    _log.warning(
        "CORVIN_ALLOWED_ORIGINS='*' — CORS protection is disabled. Set an explicit "
        "comma-separated origin allowlist before any non-local deployment (TD-H6)."
    )
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
# Outermost first at request time: RequestContext → ApiVersion → CORS → routes.
# add_middleware() prepends, so these are added after CORS to wrap it.
app.add_middleware(ApiVersionMiddleware)
app.add_middleware(RequestContextMiddleware)

app.include_router(config_router, prefix="/config", tags=["config"])
app.include_router(investigations.router, prefix="/investigations", tags=["investigations"])
app.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
app.include_router(teams_router, prefix="/teams", tags=["teams"])
app.include_router(corvin_router, prefix="/corvin", tags=["corvin"])
app.include_router(applications_router, prefix="/applications", tags=["applications"])
app.include_router(slo_router, prefix="/slo", tags=["slo"])
app.include_router(validations_router, prefix="/validations", tags=["validations"])
app.include_router(ai_features_router, prefix="/ai", tags=["ai-features"])
app.include_router(chaos_router, prefix="/chaos", tags=["chaos"])


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": "corvin-api", "version": "0.1.0"}
