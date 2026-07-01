"""Portal configuration — loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


APP_REGISTRY = [
    {
        "slug": 'benchmark',
        "title": 'BenchPoint',
        "description": '990 peer benchmarking — Gemini-powered nonprofit BI comparisons.',
        "icon": '📊',
        "color": '#005eb8',
        "order": 20,
        "url": 'https://benchpoint.dashboard.mytruage.org/ui/',
        "external": True,
    },
    {
        "slug": 'truage_activation',
        "title": 'TruAge Activation',
        "description": 'Live HubSpot pull — activation rates across all retailer accounts. Allow 30–60 seconds for the report to run.',
        "icon": '🪪',
        "color": '#087f5b',
        "order": 30,
        "url": '/apps/truage-activation/',
        "external": False,
        "has_daily": True,
    },
    {
        "slug": 'truage_account',
        "title": 'TruAge Account Manager',
        "description": 'Live HubSpot pull — account manager performance and pipeline. Allow 30–60 seconds for the report to run.',
        "icon": '📋',
        "color": '#b36b00',
        "order": 40,
        "url": '/apps/truage-account/',
        "external": False,
        "has_daily": True,
    },
    {
        "slug": 'truage_dictionary',
        "title": 'TruAge Data Dictionary',
        "description": 'HubSpot field definitions, owner roster, and data standards.',
        "icon": '📖',
        "color": '#0c6e5c',
        "order": 50,
        "url": 'https://nacstam.up.railway.app/dictionary',
        "external": True,
    },
    {
        "slug": 'stock',
        "title": 'MarketMaker',
        "description": 'Market intelligence terminal — live quotes, news synthesis, strategy lab, and AI council. Read-only; no trading capability.',
        "icon": '📈',
        "color": '#6741d9',
        "order": 60,
        "url": 'https://pezmarketmaker.up.railway.app',
        "external": True,
    },
    {
        "slug": 'app_downloads',
        "title": 'App Downloads',
        "description": 'Daily install and update counts for the TruAge mobile app — App Store and Google Play.',
        "icon": '📱',
        "color": '#2563EB',
        "order": 70,
        "url": '/apps/app-downloads/',
        "external": False,
    },
    {
        "slug": 'cstore_intel',
        "title": 'C-Store Intel',
        "description": 'US convenience store database — 150k+ locations, chain analytics, market density, and gap intelligence.',
        "icon": '🏪',
        "color": '#16a34a',
        "order": 80,
        "url": 'https://scraping.up.railway.app',
        "external": True,
    },
    {
        "slug": 'patent_atlas',
        "title": 'Patent Atlas',
        "description": 'Global patent portfolio and IP operations tracker — families, applications, deadlines, renewals, disclosures, and reports.',
        "icon": '🗺️',
        "color": '#4f46e5',
        "order": 85,
        "url": 'https://patent-atlas.dashboard.mytruage.org',
        "external": True,
    },
    {
        "slug": 'personal_email',
        "title": 'Personal Email Agent',
        "description": 'Rules control panel and activity tracker for the personal Gmail monitor. Review classifications, tune interruption rules, and track open loops.',
        "icon": '🛎️',
        "color": '#c2410c',
        "order": 90,
        "url": 'https://email-monitor.up.railway.app/',
        "external": True,
    },
    {
        "slug": 'admin',
        "title": 'Admin',
        "description": 'Manage portal users and app access.',
        "icon": '⚙️',
        "color": '#64748b',
        "order": 91,
        "url": '/apps/admin/',
        "external": False,
    },
]

# "admin" role maps to the admin card above; only users with this slug see it.
# email → list of report slugs they're subscribed to for daily delivery
EMAIL_SUBSCRIPTIONS: dict[str, list[str]] = {
    "emcfarlane@mytruage.org": [
        "truage_activation",
        "truage_account",
    ],
    "fgleeson@convenience.org": [
        "truage_activation",
        "truage_account",
    ],
    "lrountree@mytruage.org": [
        "truage_activation",
        "truage_account",
    ],
    "mterry@mytruage.org": [
        "truage_activation",
        "truage_account",
    ],
    "pabernathy@mytruage.org": [
        "truage_activation",
        "truage_account",
    ],
    "pziv@convenience.org": [
        "truage_activation",
        "truage_account",
    ],
    "ssikorski@convenience.org": [
        "truage_activation",
        "truage_account",
    ],
    "ziv.paul@gmail.com": [
    ],
}

USER_ROLES: dict[str, list[str]] = {
    "emcfarlane@mytruage.org": [
        "truage_activation",
        "truage_account",
        "truage_dictionary",
        "app_downloads",
        "cstore_intel",
    ],
    "fgleeson@convenience.org": [
        "truage_account",
        "truage_activation",
        "truage_dictionary",
        "app_downloads",
        "benchmark",
        "cstore_intel",
    ],
    "lorijoziv@gmail.com": [
        "benchmark",
        "stock",
        "cstore_intel",
    ],
    "lrountree@mytruage.org": [
        "truage_activation",
        "truage_account",
        "truage_dictionary",
        "app_downloads",
    ],
    "mterry@mytruage.org": [
        "truage_activation",
        "truage_account",
        "truage_dictionary",
        "app_downloads",
    ],
    "pabernathy@mytruage.org": [
        "truage_activation",
        "truage_account",
        "truage_dictionary",
        "app_downloads",
    ],
    "pziv@convenience.org": [
        "benchmark",
        "cstore_intel",
        "truage_activation",
        "truage_account",
        "truage_dictionary",
        "stock",
        "app_downloads",
        "personal_email",
        "patent_atlas",
    ],
    "ssikorski@convenience.org": [
        "truage_activation",
        "truage_account",
        "truage_dictionary",
        "app_downloads",
        "cstore_intel",
    ],
    "ziv.paul@gmail.com": [
        "admin",
        "app_downloads",
        "benchmark",
        "cstore_intel",
        "truage_activation",
        "truage_account",
        "truage_dictionary",
        "stock",
        "personal_email",
        "patent_atlas",
    ],
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )
    app_port: int = Field(8080)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_version: str = "1.4.0"

    # Railway auto-populates RAILWAY_ENVIRONMENT_NAME on every service (production/
    # dev/demo/etc). Defaults to "production" when unset so docs/schema endpoints
    # fail closed rather than fail open.
    environment: str = Field(
        "production",
        validation_alias="RAILWAY_ENVIRONMENT_NAME",
        description="Deployment environment name — controls whether /docs, /redoc, "
        "and /openapi.json are exposed.",
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    auth0_domain: str = Field("pezdev.us.auth0.com")
    auth0_client_id: str = Field("4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d")
    auth0_audience: str = Field("")
    github_token: str = Field("")
    github_repo: str = Field("paulziv/pez-portal")
    github_branch: str = Field("main")
    cron_secret: str = Field("")
    resend_api_key: str = Field("")
    resend_from: str = Field("Innovation Portal <portal@dashboard.mytruage.org>")
    railway_api_token: str = Field("")
    railway_cron_service_id: str = Field("a42ef700-4ced-4e14-a533-7e6e04266b30")
    railway_environment_id: str = Field("373d0dd2-7ba2-4bd7-8e47-a031738d47aa")
    apple_key_id: str = Field("")
    apple_issuer_id: str = Field("")
    apple_private_key: str = Field("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
