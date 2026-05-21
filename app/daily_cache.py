"""Daily report cache — persisted to Postgres so redeploys don't wipe reports."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_conn():
    """Return a psycopg2 connection, or None if PORTAL_DATABASE_URL is unset."""
    url = os.environ.get("PORTAL_DATABASE_URL")
    if not url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(url)
    except Exception as exc:
        log.warning("report_cache: DB connect failed: %s", exc)
        return None


def _ensure_table() -> None:
    conn = _get_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS report_cache (
                        slug         TEXT PRIMARY KEY,
                        html         TEXT NOT NULL,
                        generated_at TIMESTAMPTZ NOT NULL
                    )
                """)
    except Exception as exc:
        log.warning("report_cache: could not create table: %s", exc)
    finally:
        conn.close()


def _db_load(slug: str) -> tuple[Optional[str], Optional[datetime]]:
    conn = _get_conn()
    if not conn:
        return None, None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT html, generated_at FROM report_cache WHERE slug = %s",
                (slug,),
            )
            row = cur.fetchone()
        if row:
            return row[0], row[1]
    except Exception as exc:
        log.warning("report_cache: load failed for %s: %s", slug, exc)
    finally:
        conn.close()
    return None, None


def _db_save(slug: str, html: str, generated_at: datetime) -> None:
    conn = _get_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO report_cache (slug, html, generated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (slug) DO UPDATE
                        SET html = EXCLUDED.html,
                            generated_at = EXCLUDED.generated_at
                """, (slug, html, generated_at))
    except Exception as exc:
        log.warning("report_cache: save failed for %s: %s", slug, exc)
    finally:
        conn.close()


# ── Cache class ───────────────────────────────────────────────────────────────

class DailyCache:
    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.html: Optional[str] = None
        self.generated_at: Optional[datetime] = None
        self._restore()

    def _restore(self) -> None:
        """Load the last cached report from DB on startup."""
        html, generated_at = _db_load(self.slug)
        if html:
            self.html = html
            self.generated_at = generated_at
            log.info("report_cache: restored %s from DB (generated %s)", self.slug, generated_at)

    def set(self, html: str) -> None:
        self.generated_at = datetime.utcnow()
        self.html = html
        _db_save(self.slug, html, self.generated_at)

    @property
    def available(self) -> bool:
        return self.html is not None

    def to_status(self) -> dict:
        return {
            "available": self.available,
            "generated_at": self.generated_at.isoformat() + "Z" if self.generated_at else None,
        }


# ── Startup ───────────────────────────────────────────────────────────────────

_ensure_table()

account_cache    = DailyCache("truage_account")
activation_cache = DailyCache("truage_activation")
