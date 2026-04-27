"""
Corvin FastAPI application entry point.

Start the dev server with:
    uvicorn apps.api.main:app --reload --port 8000
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routes import investigations, triggers
from apps.teams.router import router as teams_router

app = FastAPI(
    title="Corvin API",
    description="Azure-native investigation platform – V1 control plane",
    version="0.1.0",
)

_allowed_origins = [o.strip() for o in os.environ.get("CORVIN_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)

app.include_router(investigations.router, prefix="/investigations", tags=["investigations"])
app.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
app.include_router(teams_router, prefix="/teams", tags=["teams"])


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": "corvin-api", "version": "0.1.0"}
