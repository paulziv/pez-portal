"""TruAge Activation Report router.

Placeholder — replace the stub UI and API endpoints with real
TruAge data logic when ready.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.auth import UserClaims, require_app

router = APIRouter(prefix="/apps/truage-activation", tags=["truage-activation"])

_require = require_app("truage_activation")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui(_user: UserClaims = Depends(_require)) -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>TruAge Activation Report</title>
  <style>
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:#f4f8ef;color:#123044;margin:0;padding:2rem;}
    h1{color:#005eb8;}
    .back{display:inline-block;margin-bottom:1.5rem;color:#005eb8;text-decoration:none;font-size:0.9rem;}
    .placeholder{background:#fff;border:1px solid #b9d0a9;border-radius:8px;
                 padding:3rem;text-align:center;color:#506575;margin-top:2rem;}
  </style>
</head>
<body>
  <a class="back" href="/">← Back to portal</a>
  <h1>🪪 TruAge Activation Report</h1>
  <div class="placeholder">
    <p style="font-size:1.1rem;margin-bottom:0.5rem;">Coming soon</p>
    <p>TruAge activation data and reporting will live here.</p>
  </div>
</body>
</html>"""


@router.get("/api/status")
async def status(user: UserClaims = Depends(_require)) -> dict:
    """Health / stub endpoint for the TruAge Activation app."""
    return {"app": "truage_activation", "status": "stub", "user": user.email}
