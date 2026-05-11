"""
Corvin FastAPI application entry point.

Start the dev server with:
    uvicorn apps.api.main:app --reload --port 8000
"""

from __future__ import annotations

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

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routes import investigations, triggers
from apps.teams.router import router as teams_router
from corvin.storage.db import get_engine, is_sqlite
from corvin.storage.models import Base


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Auto-create all tables when running in SQLite mode (no Alembic required)."""
    if is_sqlite():
        Base.metadata.create_all(get_engine())
    yield


app = FastAPI(
    title="Corvin API",
    description="Azure-native investigation platform – V1 control plane",
    version="0.1.0",
    lifespan=_lifespan,
)

_cors_origins_raw = os.environ.get("CORVIN_ALLOWED_ORIGINS", "http://localhost:5173").strip()
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
    allow_methods=["*"] if _allow_all_origins else ["GET", "POST", "PATCH"],
    allow_headers=["*"] if _allow_all_origins else ["Content-Type"],
)

app.include_router(investigations.router, prefix="/investigations", tags=["investigations"])
app.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
app.include_router(teams_router, prefix="/teams", tags=["teams"])


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": "corvin-api", "version": "0.1.0"}
