"""Portal configuration — loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


APP_REGISTRY = [
    {"slug": "admin", "title": "Admin",
     "description": "Manage portal users and app access.",
     "icon": "⚙️", "color": "#64748b",
     "url": "/apps/admin/", "external": False},
    {"slug": "benchmark", "title": "BenchPoint",
     "description": "990 peer benchmarking — Gemini-powered nonprofit BI comparisons.",
     "icon": "📊", "color": "#005eb8",
     "url": "https://nacs-990-benchmark-production.up.railway.app/ui/", "external": True},
    {"slug": "truage_activation", "title": "TruAge Activation",
     "description": "Live HubSpot pull — activation rates across all retailer accounts. Allow 30–60 seconds for the report to run.",
     "icon": "🪪", "color": "#087f5b",
     "url": "/apps/truage-activation/", "external": False, "has_daily": True},
    {"slug": "truage_account", "title": "TruAge Account Manager",
     "description": "Live HubSpot pull — account manager performance and pipeline. Allow 30–60 seconds for the report to run.",
     "icon": "📋", "color": "#b36b00",
     "url": "/apps/truage-account/", "external": False, "has_daily": True},
    {"slug": "truage_dictionary", "title": "TruAge Data Dictionary",
     "description": "HubSpot field definitions, owner roster, and data standards.",
     "icon": "📖", "color": "#0c6e5c",
     "url": "https://nacstam.up.railway.app/dictionary", "external": True},
    {"slug": "stock", "title": "MarketMaker",
     "description": "Market intelligence terminal — live quotes, news synthesis, strategy lab, and AI council. Read-only; no trading capability.",
     "icon": "📈", "color": "#6741d9",
     "url": "https://stock-tracker-production-0582.up.railway.app", "external": True},
]

# "admin" role maps to the admin card above; only users with this slug see it.
USER_ROLES: dict[str, list[str]] = {
    "fgleeson@convenience.org": [
        "benchmark",
        "stock",
        "truage_account",
        "truage_activation",
        "truage_dictionary",
    ],
    "lorijoziv@gmail.com": [
        "benchmark",
        "stock",
    ],
    "lrountree@mytruage.org": [
        "truage_activation",
        "truage_account",
        "truage_dictionary",
    ],
    "mterry@mytruage.org": [
        "truage_activation",
        "truage_account",
        "truage_dictionary",
    ],
    "pabernathy@mytruage.org": [
        "truage_activation",
        "truage_account",
        "truage_dictionary",
    ],
    "ssikorski@convenience.org": [
        "truage_activation",
        "truage_account",
        "truage_dictionary",
    ],
    "ziv.paul@gmail.com": [
        "admin",
        "benchmark",
        "truage_activation",
        "truage_account",
        "truage_dictionary",
        "stock",
    ],
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )
    app_port: int = Field(8080)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_version: str = "1.1.0"
    auth0_domain: str = Field("pezdev.us.auth0.com")
    auth0_client_id: str = Field("4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d")
    auth0_audience: str = Field("")
    github_token: str = Field("")
    github_repo: str = Field("paulziv/pez-portal")
    github_branch: str = Field("main")
    cron_secret: str = Field("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
