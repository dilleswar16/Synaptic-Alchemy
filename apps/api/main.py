"""
Corvin FastAPI application entry point.

Start the dev server with:
    uvicorn apps.api.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI

from apps.api.routes import investigations, triggers
from apps.teams.router import router as teams_router

app = FastAPI(
    title="Corvin API",
    description="Azure-native investigation platform – V1 control plane",
    version="0.1.0",
)

app.include_router(investigations.router, prefix="/investigations", tags=["investigations"])
app.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
app.include_router(teams_router, prefix="/teams", tags=["teams"])


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "service": "corvin-api", "version": "0.1.0"}
