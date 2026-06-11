"""Configuration endpoints for runtime platform settings."""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class BrandingResponse(BaseModel):
    product_name: str
    logo_url: str
    primary_color: str
    favicon_url: str


@router.get("/branding", response_model=BrandingResponse)
def get_branding() -> BrandingResponse:
    """Return platform branding configuration.

    All values are configurable via environment variables. Defaults produce a
    generic Corvin deployment with no customer-specific branding.
    """
    return BrandingResponse(
        product_name=os.environ.get("CORVIN_PRODUCT_NAME", "Corvin"),
        logo_url=os.environ.get("CORVIN_LOGO_URL", "/corvin-logo.svg"),
        primary_color=os.environ.get("CORVIN_PRIMARY_COLOR", "#6366f1"),
        favicon_url=os.environ.get("CORVIN_FAVICON_URL", "/favicon.svg"),
    )
