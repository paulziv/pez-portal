"""Portal configuration — loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── App registry ──────────────────────────────────────────────────────────────
# Each entry defines a card on the portal landing page.
# slug      : URL path segment  → /apps/<slug>/
# title     : Card heading
# description: One-line summary shown on the card
# icon      : Emoji shown on the card
# color     : CSS accent color for the card border

APP_REGISTRY = [
    {
        "slug": "benchmark",
        "title": "BenchPoint",
        "description": "990 peer benchmarking — Gemini-powered nonprofit BI comparisons.",
        "icon": "📊",
        "color": "#005eb8",
        "url": "https://990benchmark.up.railway.app/ui/",   # external for now
        "external": True,
    },
    {
        "slug": "truage_activation",
        "title": "TruAge Activation",
        "description": "TruAge activation report across retailer accounts.",
        "icon": "🪪",
        "color": "#087f5b",
        "url": "/apps/truage-activation/",
        "external": False,
    },
    {
        "slug": "truage_account",
        "title": "TruAge Account Manager",
        "description": "Account manager performance and pipeline report.",
        "icon": "📋",
        "color": "#b36b00",
        "url": "/apps/truage-account/",
        "external": False,
    },
    {
        "slug": "stock",
        "title": "Market Dashboard",
        "description": "Deribit market data — instruments, order book, price tracking.",
        "icon": "📈",
        "color": "#6741d9",
        "url": "/apps/stock/",
        "external": False,
    },
]

# ── Role-based access control ─────────────────────────────────────────────────
# Maps email address → list of app slugs the user may access.
# Add new users here; slugs must match APP_REGISTRY entries above.

USER_ROLES: dict[str, list[str]] = {
    "ziv.paul@gmail.com": [
        "benchmark",
        "truage_activation",
        "truage_account",
        "stock",
    ],
    "fgleeson@convenience.org": [
        "benchmark",
    ],
}


# ── Settings ──────────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    app_port: int = Field(8080, description="Port uvicorn listens on")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_version: str = "1.0.0"

    # Auth0
    auth0_domain: str = Field("pezdev.us.auth0.com", description="Auth0 tenant domain")
    auth0_client_id: str = Field("4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d", description="Auth0 SPA client ID")
    auth0_audience: str = Field("", description="Auth0 API audience (optional)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
