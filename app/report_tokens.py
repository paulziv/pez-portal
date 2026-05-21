"""Magic-link tokens for unauthenticated report access.

Tokens are stored in Postgres, expire after 24 hours, and require
no portal login. Each cron run mints fresh tokens; old ones are
cleaned up automatically.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

_TTL_HOURS = 24


def _get_conn():
    url = os.environ.get("PORTAL_DATABASE_URL")
    if not url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(url)
    except Exception as exc:
        log.warning("report_tokens: DB connect failed: %s", exc)
        return None


def _ensure_table() -> None:
    conn = _get_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS report_tokens (
                        token      TEXT PRIMARY KEY,
                        slug       TEXT NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                """)
    except Exception as exc:
        log.warning("report_tokens: could not create table: %s", exc)
    finally:
        conn.close()


def mint_token(slug: str) -> Optional[str]:
    """Create a fresh 24-hour token for a report slug. Returns the token string."""
    conn = _get_conn()
    if not conn:
        return None
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_TTL_HOURS)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO report_tokens (token, slug, expires_at) VALUES (%s, %s, %s)",
                    (token, slug, expires_at),
                )
        return token
    except Exception as exc:
        log.warning("report_tokens: mint failed for %s: %s", slug, exc)
        return None
    finally:
        conn.close()


def redeem_token(token: str) -> Optional[str]:
    """Look up a token and return its slug if valid, else None."""
    conn = _get_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT slug, expires_at FROM report_tokens WHERE token = %s",
                (token,),
            )
            row = cur.fetchone()
        if not row:
            return None
        slug, expires_at = row
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return None
        return slug
    except Exception as exc:
        log.warning("report_tokens: redeem failed: %s", exc)
        return None
    finally:
        conn.close()


def purge_expired() -> None:
    """Delete expired tokens — called at the start of each cron run."""
    conn = _get_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM report_tokens WHERE expires_at < now()")
    except Exception as exc:
        log.warning("report_tokens: purge failed: %s", exc)
    finally:
        conn.close()


_ensure_table()
