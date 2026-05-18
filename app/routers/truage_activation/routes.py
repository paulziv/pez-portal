"""TruAge Activation Report router — proxies the live report from nacstam.up.railway.app."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from app.auth import UserClaims, require_app

router = APIRouter(prefix="/apps/truage-activation", tags=["truage-activation"])
_require = require_app("truage_activation")

_UPSTREAM = "https://nacstar.up.railway.app"

# Wrapper shell — injects portal nav around the proxied report
_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>TruAge Activation Report</title>
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
           border:1px solid rgba(255,255,255,0.2);border-radius:6px;
           padding:0.3rem 0.75rem;}}
    .back:hover{{color:#36ECDE;border-color:#36ECDE;}}
    .refresh-btn{{font-size:0.82rem;background:none;cursor:pointer;color:rgba(255,255,255,0.5);
                  border:1px solid rgba(255,255,255,0.15);border-radius:6px;
                  padding:0.3rem 0.75rem;}}
    .refresh-btn:hover{{color:#36ECDE;border-color:#36ECDE;}}
    #report-frame{{width:100%;border:none;display:block;min-height:calc(100vh - 54px);}}
    #loading{{padding:4rem 2rem;text-align:center;}}
    .loader-ring{{
      display:inline-block;width:44px;height:44px;margin-bottom:1.25rem;
      border:4px solid #DDD8CE;border-top-color:#36ECDE;
      border-radius:50%;animation:spin 0.9s linear infinite;
    }}
    @keyframes spin{{to{{transform:rotate(360deg);}}}}
    .loader-msg{{font-size:1rem;font-weight:600;color:#1A2332;margin-bottom:0.35rem;}}
    .loader-sub{{font-size:0.82rem;color:#7A7060;}}
    #error-box{{display:none;padding:2rem 1.5rem;}}
    .err-card{{background:#fff;border:1px solid #DDD8CE;border-left:6px solid #C0392B;
               border-radius:10px;padding:2rem;max-width:600px;margin:0 auto;}}
    .err-card h2{{font-size:1rem;color:#1A2332;margin-bottom:0.5rem;}}
    .err-card p{{font-size:0.85rem;color:#7A7060;}}
  </style>
</head>
<body>
<header>
  <span class="hdr-title">&#x1FAA6; TruAge Activation Report</span>
  <div class="hdr-right">
    <button class="refresh-btn" onclick="triggerRefresh()" title="Fetch latest data from HubSpot">&#x21BB; Refresh</button>
    <a class="back" href="/">&#x2190; Portal</a>
  </div>
</header>
<div id="loading">
  <div class="loader-ring"></div>
  <div class="loader-msg" id="loader-msg">Connecting to HubSpot&hellip;</div>
  <div class="loader-sub" id="loader-sub">This usually takes 10&ndash;20 seconds</div>
</div>
<div id="error-box" style="display:none">
  <div class="err-card">
    <h2>Report unavailable</h2>
    <p id="error-msg">The activation report service could not be reached. Try again in a moment.</p>
  </div>
</div>
<iframe id="report-frame" style="display:none;width:100%;border:none;min-height:calc(100vh - 54px)">
</iframe>
<script>
  const LOAD_MSGS = [
    ["Connecting to HubSpot…",        "Pulling your latest account data"],
    ["Crunching the numbers…",         "Counting retailers, checking activations"],
    ["Scanning retailer accounts…",    "Matching accounts to territories"],
    ["Checking activation status…",    "This usually takes 10–20 seconds"],
    ["Almost there…",                  "Building your report now"],
    ["Finalizing the report…",         "Just a few more seconds"],
  ];

  let _msgTimer = null;
  function startLoadingMessages(startIdx) {{
    let i = startIdx || 0;
    const msgEl = document.getElementById('loader-msg');
    const subEl = document.getElementById('loader-sub');
    function cycle() {{
      if (!msgEl) return;
      const [h, s] = LOAD_MSGS[i % LOAD_MSGS.length];
      msgEl.textContent = h;
      subEl.textContent = s;
      i++;
      _msgTimer = setTimeout(cycle, 3500);
    }}
    cycle();
  }}
  function stopLoadingMessages() {{
    if (_msgTimer) {{ clearTimeout(_msgTimer); _msgTimer = null; }}
  }}
  function showLoading(startIdx) {{
    stopLoadingMessages();
    document.getElementById('loading').style.display = 'block';
    document.getElementById('error-box').style.display = 'none';
    document.getElementById('report-frame').style.display = 'none';
    startLoadingMessages(startIdx);
  }}

  async function getToken() {{
    try {{
      const client = await auth0.createAuth0Client({{
        domain: "pezdev.us.auth0.com",
        clientId: "4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d",
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
    try {{
      const resp = await fetch('/apps/truage-activation/proxy', {{
        headers: {{ 'Authorization': 'Bearer ' + token }}
      }});
      if (!resp.ok) {{
        stopLoadingMessages();
        document.getElementById('loading').style.display = 'none';
        document.getElementById('error-msg').textContent = 'Error ' + resp.status + ' — report unavailable.';
        document.getElementById('error-box').style.display = 'block';
        return;
      }}
      const html = await resp.text();
      const blob = new Blob([html], {{type: 'text/html'}});
      const url  = URL.createObjectURL(blob);
      const frame = document.getElementById('report-frame');
      frame.src = url;
      frame.onload = () => {{
        stopLoadingMessages();
        document.getElementById('loading').style.display = 'none';
        frame.style.display = 'block';
      }};
    }} catch(e) {{
      stopLoadingMessages();
      document.getElementById('loading').style.display = 'none';
      document.getElementById('error-msg').textContent = 'Network error: ' + e.message;
      document.getElementById('error-box').style.display = 'block';
    }}
  }}

  async function triggerRefresh() {{
    const token = await getToken();
    if (!token) return;
    const btn = document.querySelector('.refresh-btn');
    btn.textContent = '⏳ Refreshing…';
    btn.disabled = true;
    try {{
      await fetch('/apps/truage-activation/refresh', {{
        method: 'POST',
        headers: {{ 'Authorization': 'Bearer ' + token }}
      }});
      // Show loading with a "refresh" message set starting mid-rotation
      setTimeout(() => loadReport(2).then(() => {{
        btn.textContent = '↻ Refresh';
        btn.disabled = false;
      }}), 8000);
    }} catch(e) {{
      btn.textContent = '↻ Refresh';
      btn.disabled = false;
    }}
  }}

  // Start message rotation immediately — don't wait for Auth0 SDK download
  startLoadingMessages(0);

  // Bootstrap Auth0 SDK
  const sdk = document.createElement('script');
  sdk.src = 'https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js';
  sdk.onload = loadReport;
  document.head.appendChild(sdk);
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui() -> str:
    """Portal shell — served publicly; client-side Auth0 check gates the /proxy call."""
    return _SHELL


@router.get("/proxy", response_class=HTMLResponse, include_in_schema=False)
async def proxy_report(user: UserClaims = Depends(_require)) -> HTMLResponse:
    """Server-side proxy — fetches the live report from the upstream service."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{_UPSTREAM}/")
        if resp.status_code == 202:
            # Report not generated yet — upstream is still starting up
            return HTMLResponse(
                content="<html><body style='font-family:sans-serif;padding:3rem;color:#7A7060'>"
                        "<p>Report is being generated — refresh in a moment.</p></body></html>",
                status_code=202,
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Upstream returned non-200")
        return HTMLResponse(content=resp.text, status_code=200)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream timed out")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream unreachable: {exc}")


@router.post("/refresh")
async def refresh_report(user: UserClaims = Depends(_require)) -> JSONResponse:
    """Trigger a fresh HubSpot pull on the upstream service."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{_UPSTREAM}/refresh")
        return JSONResponse({"status": "triggered", "upstream": resp.status_code})
    except Exception as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=502)


@router.get("/api/status")
async def status(user: UserClaims = Depends(_require)) -> dict:
    return {"app": "truage_activation", "upstream": _UPSTREAM, "user": user.email}
