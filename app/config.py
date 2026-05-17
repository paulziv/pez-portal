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
     "url": "https://990benchmark.up.railway.app/ui/", "external": True},
    {"slug": "truage_activation", "title": "TruAge Activation",
     "description": "TruAge activation report across retailer accounts.",
     "icon": "🪪", "color": "#087f5b",
     "url": "/apps/truage-activation/", "external": False},
    {"slug": "truage_account", "title": "TruAge Account Manager",
     "description": "Account manager performance and pipeline report.",
     "icon": "📋", "color": "#b36b00",
     "url": "/apps/truage-account/", "external": False},
    {"slug": "stock", "title": "Market Dashboard",
     "description": "Deribit market data — instruments, order book, price tracking.",
     "icon": "📈", "color": "#6741d9",
     "url": "/apps/stock/", "external": False},
]

# "admin" role maps to the admin card above; only users with this slug see it.
USER_ROLES: dict[str, list[str]] = {
    "ziv.paul@gmail.com": [
        "admin", "benchmark", "truage_activation", "truage_account", "stock",
    ],
    "fgleeson@convenience.org": ["benchmark"],
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )
    app_port: int = Field(8080)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_version: str = "1.0.0"
    auth0_domain: str = Field("pezdev.us.auth0.com")
    auth0_client_id: str = Field("4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d")
    auth0_audience: str = Field("")
    github_token: str = Field("")
    github_repo: str = Field("paulziv/pez-portal")
    github_branch: str = Field("main")


@lru_cache
def get_settings() -> Settings:
    return Settings()
