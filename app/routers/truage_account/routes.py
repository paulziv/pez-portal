"""TruAge Account Manager Report router."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from app.auth import UserClaims, require_app

router = APIRouter(prefix="/apps/truage-account", tags=["truage-account"])
_require = require_app("truage_account")

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>TruAge Account Manager</title>
  <script src="https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js"></script>
  <style>
    :root{--bg:#F5F0E8;--surface:#FFFFFF;--border:#DDD8CE;--text:#1A2332;
          --muted:#7A7060;--navy:#00203F;--accent:#b36b00;--mint:#36ECDE;}
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
         background:var(--bg);color:var(--text);min-height:100vh;}
    header{background:var(--navy);padding:0 1.5rem;height:54px;display:flex;
           align-items:center;justify-content:space-between;}
    .header-title{font-size:0.95rem;font-weight:700;color:var(--mint);}
    .back{font-size:0.82rem;color:rgba(255,255,255,0.6);text-decoration:none;
          border:1px solid rgba(255,255,255,0.2);border-radius:6px;padding:0.3rem 0.75rem;}
    .back:hover{color:var(--mint);border-color:var(--mint);}
    main{max-width:900px;margin:0 auto;padding:2.5rem 1.5rem;}
    .placeholder{background:var(--surface);border:1px solid var(--border);
                 border-left:6px solid var(--accent);border-radius:10px;
                 padding:3rem;text-align:center;color:var(--muted);margin-top:2rem;}
    .placeholder p:first-child{font-size:1.05rem;font-weight:600;
                               color:var(--text);margin-bottom:0.5rem;}
  </style>
</head>
<body>
<header>
  <span class="header-title">&#x1F4CB; TruAge Account Manager</span>
  <a class="back" href="/">&#x2190; Portal</a>
</header>
<main>
  <div class="placeholder">
    <p>Coming soon</p>
    <p>Account manager performance and pipeline reporting will live here.</p>
  </div>
</main>
<script>
  (async () => {
    const client = await auth0.createAuth0Client({
      domain: "pezdev.us.auth0.com",
      clientId: "4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d",
      authorizationParams: { redirect_uri: window.location.origin, scope: "openid profile email" },
      cacheLocation: "localstorage",
    });
    if (!(await client.isAuthenticated())) { window.location.href = "/"; }
  })();
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui() -> str:
    # Auth handled client-side; /api/* endpoints remain protected
    return _HTML


@router.get("/api/status")
async def status(user: UserClaims = Depends(_require)) -> dict:
    return {"app": "truage_account", "status": "stub", "user": user.email}
