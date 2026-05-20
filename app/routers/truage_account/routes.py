"""TruAge Account Manager Report router — proxies nacstam and caches a daily snapshot."""
from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from app.auth import UserClaims, require_app
from app.daily_cache import account_cache
from app.email_service import send_report

router = APIRouter(prefix="/apps/truage-account", tags=["truage-account"])
_require = require_app("truage_account")

_UPSTREAM = "https://nacstam.up.railway.app"


def _inject_base(html: str) -> str:
    """Inject <base href> and strip upstream nav bar from proxied report HTML."""
    tag = f'<base href="{_UPSTREAM}/">'
    patched = re.sub(r'(<head\b[^>]*>)', r'\1' + tag, html, count=1, flags=re.IGNORECASE)
    if patched == html:
        patched = tag + html
    # Remove the upstream app's own nav bar (links to /audit, /dictionary, /settings, etc.)
    patched = re.sub(r'<nav\b[^>]*>.*?</nav>', '', patched, flags=re.IGNORECASE | re.DOTALL)
    return patched

# ── Live-report shell ─────────────────────────────────────────────────────────

_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>TruAge Account Manager</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#F5F0E8;min-height:100vh;}}
    header{{background:#00203F;padding:0 1.5rem;height:54px;display:flex;
            align-items:center;justify-content:space-between;}}
    .hdr-title{{font-size:0.95rem;font-weight:700;color:#36ECDE;}}
    .hdr-right{{display:flex;align-items:center;gap:0.75rem;}}
    .back{{font-size:0.82rem;color:rgba(255,255,255,0.6);text-decoration:none;
           border:1px solid rgba(255,255,255,0.2);border-radius:6px;padding:0.3rem 0.75rem;}}
    .back:hover{{color:#36ECDE;border-color:#36ECDE;}}
    .refresh-btn{{font-size:0.82rem;background:none;cursor:pointer;
                  color:rgba(255,255,255,0.5);border:1px solid rgba(255,255,255,0.15);
                  border-radius:6px;padding:0.3rem 0.75rem;}}
    .refresh-btn:hover{{color:#36ECDE;border-color:#36ECDE;}}
    .hdr-btn{{font-size:0.82rem;background:none;cursor:pointer;color:rgba(255,255,255,0.5);
             border:1px solid rgba(255,255,255,0.15);border-radius:6px;padding:0.3rem 0.75rem;}}
    .hdr-btn:hover:not(:disabled){{color:#36ECDE;border-color:#36ECDE;}}
    .hdr-btn:disabled{{opacity:0.3;cursor:not-allowed;}}
    #report-frame{{width:100%;border:none;display:block;min-height:calc(100vh - 54px);}}
    #loading{{display:flex;flex-direction:column;align-items:center;justify-content:center;
              min-height:calc(100vh - 54px);padding:2rem 1.5rem;}}
    .loader-card{{background:#fff;border:1px solid #DDD8CE;border-radius:14px;
                  padding:2.5rem 2.5rem 2rem;max-width:460px;width:100%;
                  box-shadow:0 4px 24px rgba(0,32,63,0.08);text-align:center;}}
    .loader-ring{{display:inline-block;width:48px;height:48px;margin-bottom:1.25rem;
                  border:4px solid #DDD8CE;border-top-color:#b36b00;
                  border-radius:50%;animation:spin 0.9s linear infinite;}}
    @keyframes spin{{to{{transform:rotate(360deg);}}}}
    .loader-msg{{font-size:1.05rem;font-weight:700;color:#1A2332;margin-bottom:0.3rem;}}
    .loader-sub{{font-size:0.82rem;color:#7A7060;margin-bottom:1.75rem;}}
    .steps{{text-align:left;border-top:1px solid #EDE8DF;padding-top:1.25rem;
            display:flex;flex-direction:column;gap:0.6rem;margin-top:0.25rem;}}
    .step{{display:flex;align-items:center;gap:0.75rem;font-size:0.84rem;
           color:#c5bdb3;transition:color 0.3s,font-weight 0.2s;}}
    .step.done{{color:#087f5b;}}
    .step.active{{color:#1A2332;font-weight:500;}}
    .step-icon{{width:18px;flex-shrink:0;text-align:center;font-size:0.82rem;}}
    .mini-ring{{width:13px;height:13px;border:2px solid #DDD8CE;
                border-top-color:#b36b00;border-radius:50%;
                animation:spin 0.8s linear infinite;display:inline-block;
                vertical-align:middle;}}
    .loader-warn{{display:none;margin-top:1.25rem;padding:0.75rem 1rem;
                  background:#fff8e1;border:1px solid #e6b800;border-radius:8px;
                  font-size:0.82rem;color:#7a5c00;line-height:1.5;}}
    #error-box{{display:none;padding:2rem 1.5rem;}}
    .err-card{{background:#fff;border:1px solid #DDD8CE;border-left:6px solid #C0392B;
               border-radius:10px;padding:2rem;max-width:600px;margin:0 auto;}}
    .err-card h2{{font-size:1rem;color:#1A2332;margin-bottom:0.5rem;}}
    .err-card p{{font-size:0.85rem;color:#7A7060;}}
  </style>
</head>
<body>
<header>
  <span class="hdr-title">&#x1F4CB; TruAge Account Manager</span>
  <div class="hdr-right">
    <button class="refresh-btn" onclick="triggerRefresh()" title="Fetch latest data from HubSpot">&#x21BB; Refresh</button>
    <button class="hdr-btn" id="btn-email" disabled onclick="forwardReport()" title="Email this report to yourself">&#x2709; Forward</button>
    <button class="hdr-btn" id="btn-download" disabled onclick="downloadReport()">&#x2193; Download</button>
    <a class="back" href="/">&#x2190; Portal</a>
  </div>
</header>
<div id="loading">
  <div class="loader-card">
    <div class="loader-ring"></div>
    <div class="loader-msg" id="loader-msg">Connecting to HubSpot&hellip;</div>
    <div class="loader-sub">Hang tight &mdash; this usually takes 30&ndash;45 seconds</div>
    <div class="steps">
      <div class="step pending" id="step-1"><span class="step-icon">&#x25CB;</span><span>Authenticating with HubSpot API</span></div>
      <div class="step pending" id="step-2"><span class="step-icon">&#x25CB;</span><span>Fetching account manager records</span></div>
      <div class="step pending" id="step-3"><span class="step-icon">&#x25CB;</span><span>Analysing AM assignments &amp; overlaps</span></div>
      <div class="step pending" id="step-4"><span class="step-icon">&#x25CB;</span><span>Scoring hygiene and flagging conflicts</span></div>
      <div class="step pending" id="step-5"><span class="step-icon">&#x25CB;</span><span>Assembling your report</span></div>
    </div>
    <div class="loader-warn" id="loader-warn">
      Still working&hellip; The HubSpot connection is taking longer than usual. Sit tight &mdash; it will arrive.
    </div>
  </div>
</div>
<div id="error-box" style="display:none">
  <div class="err-card">
    <h2>Report unavailable</h2>
    <p id="error-msg">The account manager report service could not be reached. Try again in a moment.</p>
  </div>
</div>
<iframe id="report-frame" style="display:none;width:100%;border:none;min-height:calc(100vh - 54px)"></iframe>
<script>
  const LOAD_MSGS = [
    ["Connecting to HubSpot…",              "Pulling your latest account data"],
    ["Analysing AM assignments…",           "Checking overlaps and territory coverage"],
    ["Scoring hygiene…",                    "Flagging conflicts and gaps"],
    ["Almost there…",                       "Assembling your report now"],
    ["Finalizing the report…",              "Just a few more seconds"],
  ];
  let _reportHtml = null;
  let _msgTimer = null;
  function startLoadingMessages(startIdx) {{
    let i = startIdx || 0;
    const msgEl = document.getElementById('loader-msg');
    const subEl = document.getElementById('loader-sub');
    function cycle() {{
      if (!msgEl) return;
      const [h, s] = LOAD_MSGS[i % LOAD_MSGS.length];
      msgEl.textContent = h; subEl.textContent = s; i++;
      _msgTimer = setTimeout(cycle, 3500);
    }}
    cycle();
  }}
  function stopLoadingMessages() {{
    if (_msgTimer) {{ clearTimeout(_msgTimer); _msgTimer = null; }}
  }}

  const _TS_KEY = 'truage_acct_fetch_ts';
  const _COOLDOWN_MS = 30000;
  function _markFetchStart() {{ localStorage.setItem(_TS_KEY, String(Date.now())); }}
  function _markFetchDone()  {{ localStorage.removeItem(_TS_KEY); }}
  function _cooldownSecs() {{
    const ts = parseInt(localStorage.getItem(_TS_KEY) || '0', 10);
    if (!ts) return 0;
    return Math.max(0, Math.ceil((_COOLDOWN_MS - (Date.now() - ts)) / 1000));
  }}

  const _STEP_MS = [600, 9000, 19000, 30000, 41000];
  let _stepTimers = [], _warnTimer = null;
  function _resetSteps() {{
    for (let i = 1; i <= 5; i++) {{
      const el = document.getElementById('step-' + i);
      if (el) {{ el.className = 'step pending'; el.querySelector('.step-icon').innerHTML = '&#x25CB;'; }}
    }}
    document.getElementById('loader-warn').style.display = 'none';
  }}
  function _setStepActive(n) {{
    if (n > 1) {{
      const prev = document.getElementById('step-' + (n-1));
      if (prev) {{ prev.className = 'step done'; prev.querySelector('.step-icon').innerHTML = '&#x2713;'; }}
    }}
    const el = document.getElementById('step-' + n);
    if (el) {{ el.className = 'step active'; el.querySelector('.step-icon').innerHTML = '<span class="mini-ring"></span>'; }}
  }}
  function _startSteps() {{
    _stepTimers.forEach(t => clearTimeout(t)); _stepTimers = [];
    if (_warnTimer) {{ clearTimeout(_warnTimer); _warnTimer = null; }}
    _resetSteps();
    _STEP_MS.forEach((ms, i) => {{ _stepTimers.push(setTimeout(() => _setStepActive(i+1), ms)); }});
    _warnTimer = setTimeout(() => {{ document.getElementById('loader-warn').style.display = 'block'; }}, 50000);
  }}
  function _stopSteps() {{
    _stepTimers.forEach(t => clearTimeout(t)); _stepTimers = [];
    if (_warnTimer) {{ clearTimeout(_warnTimer); _warnTimer = null; }}
  }}

  function showLoading(startIdx) {{
    stopLoadingMessages(); _stopSteps();
    document.getElementById('loading').style.display = '';
    document.getElementById('error-box').style.display = 'none';
    document.getElementById('report-frame').style.display = 'none';
    startLoadingMessages(startIdx); _startSteps();
  }}

  async function getToken() {{
    try {{
      const client = await auth0.createAuth0Client({{
        domain: "pezdev.us.auth0.com", clientId: "4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d",
        authorizationParams: {{ redirect_uri: window.location.origin, scope: "openid profile email" }},
        cacheLocation: "localstorage",
      }});
      if (!(await client.isAuthenticated())) {{ window.location.href = "/"; return null; }}
      const claims = await client.getIdTokenClaims();
      return claims ? claims.__raw : null;
    }} catch {{ window.location.href = "/"; return null; }}
  }}

  async function loadReport(startMsgIdx) {{
    showLoading(startMsgIdx || 0);
    const token = await getToken();
    if (!token) return;
    _markFetchStart();
    try {{
      const controller = new AbortController();
      const fetchTimeout = setTimeout(() => controller.abort(), 90000);
      const resp = await fetch('/apps/truage-account/proxy', {{
        headers: {{ 'Authorization': 'Bearer ' + token }}, signal: controller.signal,
      }});
      clearTimeout(fetchTimeout);
      if (!resp.ok) {{
        _markFetchDone(); stopLoadingMessages(); _stopSteps();
        document.getElementById('loading').style.display = 'none';
        document.getElementById('error-msg').textContent = 'Error ' + resp.status + ' — report unavailable.';
        document.getElementById('error-box').style.display = 'block';
        return;
      }}
      const html = await resp.text();
      _reportHtml = html;
      document.getElementById('btn-download').disabled = false;
      document.getElementById('btn-email').disabled = false;
      const blob = new Blob([html], {{type:'text/html'}});
      const frame = document.getElementById('report-frame');
      frame.src = URL.createObjectURL(blob);
      frame.onload = () => {{
        _markFetchDone(); stopLoadingMessages(); _stopSteps();
        document.getElementById('loading').style.display = 'none';
        frame.style.display = 'block';
      }};
    }} catch(e) {{
      _markFetchDone(); stopLoadingMessages(); _stopSteps();
      document.getElementById('loading').style.display = 'none';
      const msg = e.name === 'AbortError'
        ? 'Request timed out after 90 seconds. Try refreshing.'
        : 'Network error: ' + e.message;
      document.getElementById('error-msg').textContent = msg;
      document.getElementById('error-box').style.display = 'block';
    }}
  }}

  function downloadReport() {{
    if (!_reportHtml) return;
    const date = new Date().toISOString().split('T')[0];
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([_reportHtml], {{type:'text/html'}}));
    a.download = 'truage-account-manager-' + date + '.html';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }}

  async function forwardReport() {{
    const btn = document.getElementById('btn-email');
    btn.textContent = '⏳…'; btn.disabled = true;
    const token = await getToken();
    if (!token) {{ btn.textContent = '✉ Forward'; btn.disabled = false; return; }}
    try {{
      const r = await fetch('/apps/truage-account/email', {{method:'POST',headers:{{'Authorization':'Bearer '+token}}}});
      if (r.ok) {{
        btn.textContent = '✓ Sent';
        setTimeout(() => {{ btn.textContent = '✉ Forward'; btn.disabled = false; }}, 3000);
      }} else {{
        btn.textContent = '✗ Error';
        setTimeout(() => {{ btn.textContent = '✉ Forward'; btn.disabled = false; }}, 3000);
      }}
    }} catch(e) {{
      btn.textContent = '✗ Error';
      setTimeout(() => {{ btn.textContent = '✉ Forward'; btn.disabled = false; }}, 3000);
    }}
  }}

  async function triggerRefresh() {{
    _reportHtml = null;
    document.getElementById('btn-download').disabled = true;
    document.getElementById('btn-email').disabled = true;
    const token = await getToken();
    if (!token) return;
    const btn = document.querySelector('.refresh-btn');
    btn.textContent = '⏳ Refreshing…'; btn.disabled = true;
    try {{
      await fetch('/apps/truage-account/refresh', {{
        method: 'POST', headers: {{ 'Authorization': 'Bearer ' + token }}
      }});
      setTimeout(() => loadReport(2).then(() => {{ btn.textContent = '↻ Refresh'; btn.disabled = false; }}), 8000);
    }} catch(e) {{ btn.textContent = '↻ Refresh'; btn.disabled = false; }}
  }}

  startLoadingMessages(0); _startSteps();
  const sdk = document.createElement('script');
  sdk.src = 'https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js';
  sdk.onload = () => {{ const rem = _cooldownSecs(); if (rem > 0) showCooldown(rem); else loadReport(); }};
  document.head.appendChild(sdk);

  function showCooldown(secs) {{
    showLoading(0);
    const warn = document.getElementById('loader-warn'); warn.style.display = 'block';
    let s = secs;
    function tick() {{
      warn.textContent = `A report was just requested. Waiting ${{s}}s before retrying…`;
      if (s <= 0) {{ warn.style.display = 'none'; loadReport(0); return; }}
      s--; setTimeout(tick, 1000);
    }}
    tick();
  }}
</script>
</body>
</html>"""

# ── Daily report shell ─────────────────────────────────────────────────────────

_DAILY_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Daily Report — TruAge Account Manager</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
          background:#F5F0E8;min-height:100vh;}}
    header{{background:#00203F;padding:0 1.5rem;height:54px;display:flex;
            align-items:center;justify-content:space-between;}}
    .hdr-title{{font-size:0.95rem;font-weight:700;color:#36ECDE;}}
    .hdr-right{{display:flex;align-items:center;gap:1rem;}}
    .hdr-meta{{font-size:0.78rem;color:rgba(255,255,255,0.5);}}
    .back{{font-size:0.82rem;color:rgba(255,255,255,0.6);text-decoration:none;
           border:1px solid rgba(255,255,255,0.2);border-radius:6px;padding:0.3rem 0.75rem;}}
    .back:hover{{color:#36ECDE;border-color:#36ECDE;}}
    .hdr-btn{{font-size:0.82rem;background:none;cursor:pointer;color:rgba(255,255,255,0.5);
             border:1px solid rgba(255,255,255,0.15);border-radius:6px;padding:0.3rem 0.75rem;}}
    .hdr-btn:hover:not(:disabled){{color:#36ECDE;border-color:#36ECDE;}}
    .hdr-btn:disabled{{opacity:0.3;cursor:not-allowed;}}
    #report-frame{{width:100%;border:none;display:block;min-height:calc(100vh - 54px);}}
    #loading{{display:flex;align-items:center;justify-content:center;
              min-height:calc(100vh - 54px);color:#7A7060;font-size:0.9rem;}}
  </style>
</head>
<body>
<header>
  <span class="hdr-title">&#x1F4CB; Account Manager &mdash; Daily Report</span>
  <div class="hdr-right">
    <span class="hdr-meta" id="gen-time"></span>
    <button class="hdr-btn" id="btn-email" disabled onclick="forwardReport()" title="Email this report to yourself">&#x2709; Forward</button>
    <button class="hdr-btn" id="btn-download" disabled onclick="downloadReport()">&#x2193; Download</button>
    <a class="back" href="/">&#x2190; Portal</a>
  </div>
</header>
<div id="loading">Loading report&hellip;</div>
<iframe id="report-frame" style="display:none;width:100%;border:none;min-height:calc(100vh - 54px)"></iframe>
<script>
  async function load() {{
    try {{
      const client = await auth0.createAuth0Client({{
        domain:"pezdev.us.auth0.com", clientId:"4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d",
        authorizationParams:{{redirect_uri:window.location.origin,scope:"openid profile email"}},
        cacheLocation:"localstorage",
      }});
      if (!(await client.isAuthenticated())) {{ window.location.href = "/"; return; }}
      const claims = await client.getIdTokenClaims();
      const token = claims ? claims.__raw : null;
      if (!token) {{ window.location.href = "/"; return; }}

      const r = await fetch('/apps/truage-account/daily/content', {{
        headers:{{'Authorization':'Bearer '+token}}
      }});
      if (r.status === 503) {{
        document.getElementById('loading').textContent = 'Daily report not yet available. Check back after 7 AM.';
        return;
      }}
      if (!r.ok) {{ document.getElementById('loading').textContent = 'Error loading report (' + r.status + ').'; return; }}
      const meta = r.headers.get('X-Generated-At');
      if (meta) {{
        const t = new Date(meta);
        document.getElementById('gen-time').textContent =
          'Generated ' + t.toLocaleTimeString([], {{hour:'2-digit',minute:'2-digit'}});
      }}
      const html = await r.text();
      _reportHtml = html;
      document.getElementById('btn-download').disabled = false;
      document.getElementById('btn-email').disabled = false;
      const frame = document.getElementById('report-frame');
      frame.src = URL.createObjectURL(new Blob([html], {{type:'text/html'}}));
      frame.onload = () => {{
        document.getElementById('loading').style.display = 'none';
        frame.style.display = 'block';
      }};
    }} catch(e) {{
      document.getElementById('loading').textContent = 'Error: ' + e.message;
    }}
  }}
  function downloadReport() {{
    if (!_reportHtml) return;
    const date = new Date().toISOString().split('T')[0];
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([_reportHtml], {{type:'text/html'}}));
    a.download = 'truage-account-manager-daily-' + date + '.html';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }}
  async function forwardReport() {{
    const btn = document.getElementById('btn-email');
    btn.textContent = '⏳…'; btn.disabled = true;
    try {{
      const client = await auth0.createAuth0Client({{
        domain:"pezdev.us.auth0.com", clientId:"4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d",
        authorizationParams:{{redirect_uri:window.location.origin,scope:"openid profile email"}},
        cacheLocation:"localstorage",
      }});
      const claims = await client.getIdTokenClaims();
      const token = claims ? claims.__raw : null;
      if (!token) {{ btn.textContent = '✉ Forward'; btn.disabled = false; return; }}
      const r = await fetch('/apps/truage-account/email', {{method:'POST',headers:{{'Authorization':'Bearer '+token}}}});
      if (r.ok) {{
        btn.textContent = '✓ Sent';
        setTimeout(() => {{ btn.textContent = '✉ Forward'; btn.disabled = false; }}, 3000);
      }} else {{
        btn.textContent = '✗ Error';
        setTimeout(() => {{ btn.textContent = '✉ Forward'; btn.disabled = false; }}, 3000);
      }}
    }} catch(e) {{
      btn.textContent = '✗ Error';
      setTimeout(() => {{ btn.textContent = '✉ Forward'; btn.disabled = false; }}, 3000);
    }}
  }}
  let _reportHtml = null;
  const sdk = document.createElement('script');
  sdk.src = 'https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js';
  sdk.onload = load;
  document.head.appendChild(sdk);
</script>
</body>
</html>"""


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui() -> str:
    return _SHELL.replace('{{', '{').replace('}}', '}')


@router.get("/daily", response_class=HTMLResponse, include_in_schema=False)
async def daily_ui() -> str:
    return _DAILY_SHELL.replace('{{', '{').replace('}}', '}')


@router.get("/daily/content", include_in_schema=False)
async def daily_content(user: UserClaims = Depends(_require)) -> HTMLResponse:
    if not account_cache.available:
        raise HTTPException(status_code=503, detail="Daily report not yet available")
    return HTMLResponse(
        content=account_cache.html,
        headers={"X-Generated-At": account_cache.generated_at.isoformat() + "Z"},
    )


@router.get("/proxy", response_class=HTMLResponse, include_in_schema=False)
async def proxy_report(user: UserClaims = Depends(_require)) -> HTMLResponse:
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(f"{_UPSTREAM}/audit/report")
        if resp.status_code not in (200, 202):
            raise HTTPException(status_code=502, detail="Upstream returned non-200")
        return HTMLResponse(content=_inject_base(resp.text), status_code=200)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream timed out")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream unreachable: {exc}")


@router.post("/refresh")
async def refresh_report(user: UserClaims = Depends(_require)) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{_UPSTREAM}/refresh")
        return JSONResponse({"status": "triggered", "upstream": resp.status_code})
    except Exception as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=502)


@router.get("/api/status")
@router.post("/email")
async def email_report(user: UserClaims = Depends(_require)) -> JSONResponse:
    """Send the cached daily report to the requesting user's email."""
    if not account_cache.available:
        raise HTTPException(status_code=503, detail="Daily report not yet available — run the cron first.")
    from datetime import date
    filename = f"truage-account-manager-{date.today()}.html"
    result = send_report(
        to=user.email,
        report_title="TruAge Account Manager Report",
        html_content=account_cache.html,
        filename=filename,
        generated_at=account_cache.generated_at,
    )
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result["error"])
    return JSONResponse({"status": "sent", "to": user.email})


async def status(user: UserClaims = Depends(_require)) -> dict:
    return {"app": "truage_account", "upstream": _UPSTREAM, "user": user.email,
            "daily": account_cache.to_status()}


async def run_daily() -> str:
    """Fetch /audit/report directly (blocking endpoint), cache when a full report arrives."""
    import asyncio
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            await client.post(f"{_UPSTREAM}/refresh")
    except Exception:
        pass
    # /audit/report is a blocking endpoint — retry up to 3× with a 2-min timeout each.
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                resp = await client.get(f"{_UPSTREAM}/audit/report")
            if resp.status_code == 200 and len(resp.text) > 10_000:
                account_cache.set(_inject_base(resp.text))
                _send_subscribed_emails()
                return f"ok (attempt {attempt + 1})"
        except Exception:
            pass
        if attempt < 2:
            await asyncio.sleep(10)
    return "error: upstream report not ready after 3 attempts"


def _send_subscribed_emails() -> None:
    """Fire-and-forget: email all subscribed users for the account manager report."""
    import app.config as _cfg
    from datetime import date
    slug = "truage_account"
    subscribers = [e for e, slugs in _cfg.EMAIL_SUBSCRIPTIONS.items() if slug in slugs]
    if not subscribers or not account_cache.available:
        return
    filename = f"truage-account-manager-{date.today()}.html"
    for email in subscribers:
        send_report(
            to=email,
            report_title="TruAge Account Manager Report",
            html_content=account_cache.html,
            filename=filename,
            generated_at=account_cache.generated_at,
        )
