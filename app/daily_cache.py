"""In-memory daily report cache — one instance per report, shared across requests."""
from __future__ import annotations

from datetime import datetime
from typing import Optional


class DailyCache:
    def __init__(self) -> None:
        self.html: Optional[str] = None
        self.generated_at: Optional[datetime] = None

    def set(self, html: str) -> None:
        self.html = html
        self.generated_at = datetime.utcnow()

    @property
    def available(self) -> bool:
        return self.html is not None

    def to_status(self) -> dict:
        return {
            "available": self.available,
            "generated_at": self.generated_at.isoformat() + "Z" if self.generated_at else None,
        }


# Module-level singletons — survive for the lifetime of the Railway container.
# Reset to empty on redeploy; the 7am cron repopulates them.
account_cache    = DailyCache()
activation_cache = DailyCache()
