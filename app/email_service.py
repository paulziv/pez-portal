"""Report-ready email delivery via the shared truage_core.email helper (Resend)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from truage_core import email as tcemail

from app.config import get_settings

log = logging.getLogger(__name__)

_BASE_URL = "https://nacsportal.up.railway.app"


def send_report(
    *,
    to: str | list[str],
    report_title: str,
    report_url: str,
    generated_at: Optional[datetime] = None,
) -> dict:
    """Send a report-ready notification email with a magic-link view button.

    Sends from the unified reports@ address (see truage_core.email).
    Returns {"ok": True, ...} or {"ok": False, "error": str}.
    """
    date_str = (generated_at or datetime.utcnow()).strftime("%B %d, %Y")
    subject = f"{report_title} — {date_str}"

    body = f"""
<div style="font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            max-width:580px;margin:0 auto;padding:2rem 1.5rem;background:#F5F0E8;">

  <!-- Header -->
  <div style="background:#00203F;border-radius:10px;padding:1.5rem 2rem;margin-bottom:1.5rem;">
    <p style="color:#36ECDE;font-size:0.75rem;font-weight:600;letter-spacing:0.08em;
              text-transform:uppercase;margin:0 0 0.35rem;">Innovation Portal</p>
    <h1 style="color:#ffffff;font-size:1.15rem;font-weight:700;margin:0;">{report_title}</h1>
    <p style="color:rgba(255,255,255,0.55);font-size:0.82rem;margin:0.4rem 0 0;">{date_str}</p>
  </div>

  <!-- Body -->
  <p style="color:#1A2332;font-size:0.95rem;line-height:1.65;margin:0 0 1.5rem;">
    Your daily report is ready. Click the button below to view it — no login required.
    The link is valid for 24 hours.
  </p>

  <!-- CTA button -->
  <div style="text-align:center;margin-bottom:2rem;">
    <a href="{report_url}"
       style="display:inline-block;background:#00203F;color:#36ECDE;
              font-size:0.92rem;font-weight:600;text-decoration:none;
              padding:0.75rem 2rem;border-radius:8px;letter-spacing:0.02em;">
      View Report &rarr;
    </a>
  </div>

  <!-- Note -->
  <p style="color:#7A7060;font-size:0.78rem;line-height:1.5;
            border-top:1px solid #DDD8CE;padding-top:1rem;margin:0;">
    This link expires after 24 hours. A fresh link will arrive with tomorrow&rsquo;s report.<br>
    Sent by <strong>Innovation Portal</strong> &middot;
    <a href="{_BASE_URL}" style="color:#2E6DA4;text-decoration:none;">nacsportal.up.railway.app</a>
  </p>

</div>
"""

    result = tcemail.send(
        to=to,
        subject=subject,
        html=body,
        purpose="reports",
        api_key=get_settings().resend_api_key or None,
    )
    if result.get("ok"):
        log.info("email sent: report=%r to=%r subject=%r", report_title, to, subject)
    else:
        log.warning("email send FAILED: report=%r to=%r error=%s", report_title, to, result.get("error"))
    return result
