"""App Downloads router — daily installs from Apple App Store and Google Play."""
from __future__ import annotations

import gzip
import logging
import os
import time
from datetime import date, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse

from app.auth import UserClaims, require_app

log = logging.getLogger(__name__)

router = APIRouter(prefix="/apps/app-downloads", tags=["app-downloads"])
_require = require_app("app_downloads")

_APPLE_API_BASE = "https://api.appstoreconnect.apple.com/v1"
_VENDOR_NUMBER = "92675371"

# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_conn():
    url = os.environ.get("PORTAL_DATABASE_URL")
    if not url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(url)
    except Exception as exc:
        log.warning("app_downloads: DB connect failed: %s", exc)
        return None


def _ensure_table() -> None:
    conn = _get_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS app_downloads (
                        id          SERIAL PRIMARY KEY,
                        report_date DATE NOT NULL,
                        platform    VARCHAR(20) NOT NULL,
                        downloads   INTEGER NOT NULL DEFAULT 0,
                        updates     INTEGER NOT NULL DEFAULT 0,
                        UNIQUE (report_date, platform)
                    )
                """)
    except Exception as exc:
        log.warning("app_downloads: could not create table: %s", exc)
    finally:
        conn.close()


def _has_data(report_date: date, platform: str) -> bool:
    conn = _get_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM app_downloads WHERE report_date = %s AND platform = %s",
                (report_date, platform),
            )
            return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        conn.close()


def _upsert(report_date: date, platform: str, downloads: int, updates: int) -> None:
    conn = _get_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO app_downloads (report_date, platform, downloads, updates)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (report_date, platform) DO NOTHING
                """, (report_date, platform, downloads, updates))
    except Exception as exc:
        log.warning("app_downloads: upsert failed: %s", exc)
    finally:
        conn.close()


def _fetch_history(days: int = 365) -> list[dict]:
    conn = _get_conn()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT report_date, platform, downloads, updates
                FROM app_downloads
                WHERE report_date >= %s
                ORDER BY report_date DESC, platform
            """, (date.today() - timedelta(days=days),))
            rows = cur.fetchall()
        return [
            {"date": r[0].isoformat(), "platform": r[1], "downloads": r[2], "updates": r[3]}
            for r in rows
        ]
    except Exception as exc:
        log.warning("app_downloads: fetch history failed: %s", exc)
        return []
    finally:
        conn.close()


# ── Apple App Store Connect ───────────────────────────────────────────────────

def _apple_jwt() -> Optional[str]:
    key_id = os.environ.get("APPLE_KEY_ID")
    issuer_id = os.environ.get("APPLE_ISSUER_ID")
    private_key = os.environ.get("APPLE_PRIVATE_KEY", "").replace("\\n", "\n")
    if not all([key_id, issuer_id, private_key]):
        log.warning("app_downloads: Apple credentials not configured (APPLE_KEY_ID / APPLE_ISSUER_ID / APPLE_PRIVATE_KEY)")
        return None
    try:
        from jose import jwt as jose_jwt
        now = int(time.time())
        payload = {
            "iss": issuer_id,
            "iat": now,
            "exp": now + 1200,
            "aud": "appstoreconnect-v1",
        }
        return jose_jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": key_id, "typ": "JWT"})
    except Exception as exc:
        log.warning("app_downloads: Apple JWT generation failed: %s", exc)
        return None


async def _fetch_apple(report_date: date) -> tuple[int, int]:
    """Return (downloads, updates) from Apple Sales Reports for the given date."""
    token = _apple_jwt()
    if not token:
        return 0, 0
    params = {
        "filter[frequency]": "DAILY",
        "filter[reportType]": "SALES",
        "filter[reportSubType]": "SUMMARY",
        "filter[vendorNumber]": _VENDOR_NUMBER,
        "filter[reportDate]": report_date.strftime("%Y-%m-%d"),
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_APPLE_API_BASE}/salesReports",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
        if resp.status_code == 404:
            # No report available — common for weekends / holidays
            log.info("app_downloads: no Apple report for %s", report_date)
            return 0, 0
        if resp.status_code != 200:
            log.warning("app_downloads: Apple API returned %s: %s", resp.status_code, resp.text[:200])
            return 0, 0

        raw = gzip.decompress(resp.content).decode("utf-8")
        lines = raw.strip().split("\n")
        if len(lines) < 2:
            return 0, 0
        headers = lines[0].split("\t")
        try:
            type_idx = headers.index("Product Type Identifier")
            units_idx = headers.index("Units")
        except ValueError:
            log.warning("app_downloads: unexpected Apple report column layout")
            return 0, 0

        _DOWNLOAD_TYPES = {"1", "1F", "2", "2F"}
        _UPDATE_TYPES = {"7", "7F"}
        downloads = 0
        updates = 0
        for line in lines[1:]:
            cols = line.split("\t")
            if len(cols) <= max(type_idx, units_idx):
                continue
            ptype = cols[type_idx].strip()
            try:
                units = int(float(cols[units_idx].strip()))
            except ValueError:
                continue
            if ptype in _DOWNLOAD_TYPES:
                downloads += units
            elif ptype in _UPDATE_TYPES:
                updates += units
        return downloads, updates
    except Exception as exc:
        log.warning("app_downloads: Apple fetch failed: %s", exc)
        return 0, 0


# ── Google Play (ready to enable) ─────────────────────────────────────────────
# Set GOOGLE_PLAY_CREDENTIALS (service account JSON string) and
# GOOGLE_PLAY_PACKAGE_NAME on Railway to activate.

async def _fetch_google(report_date: date) -> tuple[int, int]:
    """Return (downloads, updates) from Google Play Developer Reporting API."""
    creds_json = os.environ.get("GOOGLE_PLAY_CREDENTIALS")
    package_name = os.environ.get("GOOGLE_PLAY_PACKAGE_NAME")
    if not creds_json or not package_name:
        return 0, 0
    # TODO: implement OAuth2 service account flow + Play Developer Reporting API
    # Requires: google-auth, google-auth-httplib2 packages added to requirements.txt
    return 0, 0


# ── Daily fetch (called from main cron) ──────────────────────────────────────

async def run_daily() -> str:
    has_apple_creds = all([
        os.environ.get("APPLE_KEY_ID"),
        os.environ.get("APPLE_ISSUER_ID"),
        os.environ.get("APPLE_PRIVATE_KEY"),
    ])
    if not has_apple_creds:
        return "error — Apple credentials not set (need APPLE_KEY_ID, APPLE_ISSUER_ID, APPLE_PRIVATE_KEY on Railway)"

    # Check the last 3 days so weekends aren't skipped when cron runs Mon–Fri
    fetched = []
    for days_ago in range(1, 4):
        report_date = date.today() - timedelta(days=days_ago)
        if _has_data(report_date, "apple"):
            continue
        apple_dl, apple_up = await _fetch_apple(report_date)
        google_dl, google_up = await _fetch_google(report_date)
        if apple_dl > 0 or apple_up > 0:
            _upsert(report_date, "apple", apple_dl, apple_up)
        if os.environ.get("GOOGLE_PLAY_CREDENTIALS") and (google_dl > 0 or google_up > 0):
            _upsert(report_date, "google", google_dl, google_up)
        log.info("app_downloads: %s — apple dl=%d up=%d", report_date, apple_dl, apple_up)
        fetched.append(f"{report_date}: {apple_dl} dl")

    if not fetched:
        return "skipped — last 3 days already in DB"
    return "ok — " + ", ".join(fetched)


async def run_backfill(days: int = 365) -> str:
    """Fetch up to 365 days of history, skipping dates already in DB."""
    import asyncio
    has_apple_creds = all([
        os.environ.get("APPLE_KEY_ID"),
        os.environ.get("APPLE_ISSUER_ID"),
        os.environ.get("APPLE_PRIVATE_KEY"),
    ])
    if not has_apple_creds:
        return "error — Apple credentials not set"

    fetched = skipped = errors = 0
    for days_ago in range(1, days + 1):
        report_date = date.today() - timedelta(days=days_ago)
        if _has_data(report_date, "apple"):
            skipped += 1
            continue
        try:
            apple_dl, apple_up = await _fetch_apple(report_date)
            if apple_dl > 0 or apple_up > 0:
                _upsert(report_date, "apple", apple_dl, apple_up)
            fetched += 1
        except Exception as exc:
            log.warning("app_downloads backfill: error on %s: %s", report_date, exc)
            errors += 1
        await asyncio.sleep(0.3)

    log.info("app_downloads backfill complete: fetched=%d skipped=%d errors=%d", fetched, skipped, errors)
    return f"backfill complete — fetched {fetched} days, skipped {skipped} existing, {errors} errors"


# ── HTML shell ────────────────────────────────────────────────────────────────

_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>App Downloads</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#F5F0E8;color:#1A2332;min-height:100vh;}
    header{background:#00203F;padding:0 1.5rem;height:54px;display:flex;
           align-items:center;justify-content:space-between;}
    .hdr-title{font-size:0.95rem;font-weight:700;color:#36ECDE;}
    .back{font-size:0.82rem;color:rgba(255,255,255,0.6);text-decoration:none;
          border:1px solid rgba(255,255,255,0.2);border-radius:6px;padding:0.3rem 0.75rem;}
    .back:hover{color:#36ECDE;border-color:#36ECDE;}
    main{padding:1.5rem;max-width:1100px;margin:0 auto;}
    #loading{display:flex;align-items:center;justify-content:center;
             min-height:calc(100vh - 54px);}
    .loader-ring{width:40px;height:40px;border:4px solid #DDD8CE;border-top-color:#2563EB;
                 border-radius:50%;animation:spin 0.9s linear infinite;margin-right:1rem;}
    @keyframes spin{to{transform:rotate(360deg);}}
    .loader-text{color:#7A7060;font-size:0.9rem;}
    #content{display:none;}
    .cards{display:flex;gap:1rem;margin-bottom:1.5rem;flex-wrap:wrap;}
    .card{background:#fff;border:1px solid #DDD8CE;border-radius:10px;
          padding:1.25rem 1.5rem;min-width:150px;flex:1;}
    .card-label{font-size:0.72rem;color:#7A7060;text-transform:uppercase;
                letter-spacing:0.05em;margin-bottom:0.3rem;}
    .card-value{font-size:2rem;font-weight:700;color:#00203F;line-height:1;}
    .card-sub{font-size:0.78rem;color:#7A7060;margin-top:0.3rem;}
    .card.apple{border-top:3px solid #555;}
    .card.google{border-top:3px solid #4285F4;}
    .card.total{border-top:3px solid #36ECDE;}
    .section-title{font-size:0.8rem;font-weight:600;text-transform:uppercase;
                   letter-spacing:0.06em;color:#7A7060;margin:0 0 0.75rem;}
    .chart-wrap{background:#fff;border:1px solid #DDD8CE;border-radius:10px;
                padding:1.25rem 1.25rem 1rem;margin-bottom:1.5rem;}
    table{width:100%;border-collapse:collapse;background:#fff;
          border:1px solid #DDD8CE;border-radius:10px;overflow:hidden;}
    th{background:#f0ebe2;font-size:0.72rem;text-transform:uppercase;
       letter-spacing:0.04em;color:#7A7060;padding:0.6rem 1rem;text-align:left;}
    th.num,td.num{text-align:right;}
    td{padding:0.55rem 1rem;font-size:0.85rem;border-top:1px solid #EDE8DF;}
    .muted{color:#7A7060;}
    .bold{font-weight:600;color:#00203F;}
    tr:hover td{background:#faf7f2;}
    .no-data{text-align:center;color:#7A7060;padding:3rem;font-size:0.9rem;}
    #error-box{display:none;padding:2rem;}
    .err-card{background:#fff;border:1px solid #DDD8CE;border-left:6px solid #C0392B;
              border-radius:10px;padding:2rem;max-width:500px;margin:0 auto;}
    .err-card h2{font-size:1rem;color:#1A2332;margin-bottom:0.5rem;}
    .err-card p{font-size:0.85rem;color:#7A7060;}
  </style>
</head>
<body>
<header>
  <span class="hdr-title">&#x1F4F1; App Downloads</span>
  <a class="back" href="/">&#x2190; Portal</a>
</header>

<div id="loading">
  <div class="loader-ring"></div>
  <span class="loader-text">Loading download data&hellip;</span>
</div>

<div id="error-box">
  <div class="err-card">
    <h2>Unable to load</h2>
    <p id="error-msg">Download data could not be retrieved.</p>
  </div>
</div>

<main id="content">
  <div class="cards">
    <div class="card total">
      <div class="card-label">Total Downloads</div>
      <div class="card-value" id="stat-total">—</div>
      <div class="card-sub">All platforms &middot; all time</div>
    </div>
    <div class="card apple">
      <div class="card-label">App Store (iOS)</div>
      <div class="card-value" id="stat-apple">—</div>
      <div class="card-sub" id="stat-apple-up"></div>
    </div>
    <div class="card google">
      <div class="card-label">Google Play (Android)</div>
      <div class="card-value" id="stat-google">—</div>
      <div class="card-sub" id="stat-google-up"></div>
    </div>
  </div>

  <div class="chart-wrap">
    <div class="section-title">Daily Downloads &mdash; Last 365 Days</div>
    <canvas id="dlChart" height="75"></canvas>
  </div>

  <div class="section-title">History</div>
  <div id="table-wrap"></div>
</main>

<script>
async function getToken() {
  try {
    const client = await auth0.createAuth0Client({
      domain: "pezdev.us.auth0.com",
      clientId: "4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d",
      authorizationParams: { redirect_uri: window.location.origin, scope: "openid profile email" },
      cacheLocation: "localstorage",
    });
    if (!(await client.isAuthenticated())) { window.location.href = "/"; return null; }
    const claims = await client.getIdTokenClaims();
    return claims ? claims.__raw : null;
  } catch { window.location.href = "/"; return null; }
}

function fmt(n) { return (n ?? 0).toLocaleString(); }

async function load() {
  const token = await getToken();
  if (!token) return;
  try {
    const r = await fetch('/apps/app-downloads/data', {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (!r.ok) {
      document.getElementById('loading').style.display = 'none';
      document.getElementById('error-msg').textContent = 'Error ' + r.status + ' loading data.';
      document.getElementById('error-box').style.display = 'block';
      return;
    }
    const d = await r.json();
    render(d);
  } catch(e) {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('error-msg').textContent = 'Network error: ' + e.message;
    document.getElementById('error-box').style.display = 'block';
  }
}

function render(d) {
  document.getElementById('stat-total').textContent  = fmt(d.total_apple + d.total_google);
  document.getElementById('stat-apple').textContent  = fmt(d.total_apple);
  document.getElementById('stat-google').textContent = fmt(d.total_google);
  document.getElementById('stat-apple-up').textContent  = fmt(d.total_apple_updates) + ' updates · all time';
  document.getElementById('stat-google-up').textContent = fmt(d.total_google_updates) + ' updates · all time';

  // Line chart
  new Chart(document.getElementById('dlChart'), {
    type: 'line',
    data: {
      labels: d.chart_dates,
      datasets: [
        {
          label: 'App Store',
          data: d.chart_apple,
          borderColor: 'rgba(85,85,85,0.9)',
          backgroundColor: 'rgba(85,85,85,0.08)',
          fill: true, tension: 0.3, pointRadius: 1, pointHoverRadius: 4,
        },
        {
          label: 'Google Play',
          data: d.chart_google,
          borderColor: 'rgba(66,133,244,0.9)',
          backgroundColor: 'rgba(66,133,244,0.08)',
          fill: true, tension: 0.3, pointRadius: 1, pointHoverRadius: 4,
        },
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top' } },
      scales: {
        x: { ticks: { maxTicksLimit: 12, maxRotation: 0 } },
        y: { beginAtZero: true }
      }
    }
  });

  // Monthly table
  const wrap = document.getElementById('table-wrap');
  if (!d.monthly || !d.monthly.length) {
    wrap.innerHTML = '<div class="no-data">No data yet — check back after the first daily sync.</div>';
  } else {
    const trs = d.monthly.map(m => {
      const label = new Date(m.month + '-02').toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      return `<tr>
        <td>${label}</td>
        <td class="num">${fmt(m.apple_dl)}</td>
        <td class="num">${fmt(m.google_dl)}</td>
        <td class="num bold">${fmt(m.total)}</td>
      </tr>`;
    }).join('');
    wrap.innerHTML = `<table>
      <thead><tr>
        <th>Month</th>
        <th class="num">App Store</th>
        <th class="num">Google Play</th>
        <th class="num">Total Downloads</th>
      </tr></thead>
      <tbody>${trs}</tbody>
    </table>`;
  }

  document.getElementById('loading').style.display = 'none';
  document.getElementById('content').style.display = 'block';
}

const sdk = document.createElement('script');
sdk.src = 'https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js';
sdk.onload = load;
document.head.appendChild(sdk);
</script>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui() -> str:
    return _SHELL


@router.get("/data")
async def data(user: UserClaims = Depends(_require)) -> JSONResponse:
    rows = _fetch_history(365)
    total_apple = sum(r["downloads"] for r in rows if r["platform"] == "apple")
    total_google = sum(r["downloads"] for r in rows if r["platform"] == "google")
    total_apple_updates = sum(r["updates"] for r in rows if r["platform"] == "apple")
    total_google_updates = sum(r["updates"] for r in rows if r["platform"] == "google")

    # Daily totals for chart (ascending)
    by_date: dict[str, dict] = {}
    for r in rows:
        d = r["date"]
        if d not in by_date:
            by_date[d] = {"apple": 0, "google": 0}
        by_date[d][r["platform"]] += r["downloads"]
    chart_dates = sorted(by_date.keys())
    chart_apple  = [by_date[d]["apple"]  for d in chart_dates]
    chart_google = [by_date[d]["google"] for d in chart_dates]

    # Monthly aggregation for table
    by_month: dict[str, dict] = {}
    for r in rows:
        month = r["date"][:7]  # YYYY-MM
        if month not in by_month:
            by_month[month] = {"apple_dl": 0, "google_dl": 0}
        if r["platform"] == "apple":
            by_month[month]["apple_dl"] += r["downloads"]
        else:
            by_month[month]["google_dl"] += r["downloads"]
    monthly = [
        {"month": m, "apple_dl": v["apple_dl"], "google_dl": v["google_dl"],
         "total": v["apple_dl"] + v["google_dl"]}
        for m, v in sorted(by_month.items(), reverse=True)
    ]

    return JSONResponse({
        "rows": rows,
        "total_apple": total_apple,
        "total_google": total_google,
        "total_apple_updates": total_apple_updates,
        "total_google_updates": total_google_updates,
        "chart_dates": chart_dates,
        "chart_apple": chart_apple,
        "chart_google": chart_google,
        "monthly": monthly,
    })


@router.get("/api/status")
async def status(user: UserClaims = Depends(_require)) -> dict:
    rows = _fetch_history(1)
    return {"app": "app_downloads", "latest": rows[0] if rows else None, "user": user.email}


_ensure_table()
