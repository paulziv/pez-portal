"""Resend-based email delivery for portal reports."""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Optional

import resend

from app.config import get_settings


def _client_ready() -> bool:
    settings = get_settings()
    if not settings.resend_api_key:
        return False
    resend.api_key = settings.resend_api_key
    return True


def send_report(
    *,
    to: str | list[str],
    report_title: str,
    html_content: str,
    filename: str,
    generated_at: Optional[datetime] = None,
) -> dict:
    """Send a report as an HTML attachment via Resend.

    Returns {"ok": True} or {"ok": False, "error": str}.
    """
    if not _client_ready():
        return {"ok": False, "error": "RESEND_API_KEY not configured"}

    settings = get_settings()
    date_str = (generated_at or datetime.utcnow()).strftime("%B %d, %Y")
    subject = f"{report_title} — {date_str}"

    body = f"""
<div style="font-family:'Inter',-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:2rem 1.5rem;background:#F5F0E8;">
  <div style="background:#00203F;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem;">
    <h1 style="color:#36ECDE;font-size:1.1rem;margin:0;">{report_title}</h1>
    <p style="color:rgba(255,255,255,0.6);font-size:0.85rem;margin:0.4rem 0 0;">{date_str}</p>
  </div>
  <p style="color:#1A2332;font-size:0.95rem;line-height:1.6;margin-bottom:1rem;">
    Your daily report is attached. Open the <code style="background:#DDD8CE;padding:0.1rem 0.4rem;border-radius:4px;">.html</code>
    file in any browser for the full interactive view.
  </p>
  <p style="color:#7A7060;font-size:0.8rem;margin-top:2rem;border-top:1px solid #DDD8CE;padding-top:1rem;">
    Sent by <strong>Innovation Portal</strong> &middot;
    <a href="https://nacsportal.up.railway.app" style="color:#2E6DA4;">nacsportal.up.railway.app</a>
  </p>
</div>
"""

    content_b64 = base64.b64encode(html_content.encode()).decode()

    try:
        resend.Emails.send({
            "from": settings.resend_from,
            "to": [to] if isinstance(to, str) else to,
            "subject": subject,
            "html": body,
            "attachments": [{"filename": filename, "content": content_b64}],
        })
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
