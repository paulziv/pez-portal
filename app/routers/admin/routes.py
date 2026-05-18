"""Admin panel — user management with GitHub auto-deploy.

Allows the portal admin (ziv.paul@gmail.com) to add/remove users and
toggle their app access via a UI, then commit the updated config directly
to GitHub so Railway auto-redeploys with the new settings.

Protected by require_app("admin") — only users with the "admin" slug in
USER_ROLES can access any route here.
"""

from __future__ import annotations

import base64
import re
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import app.config as _cfg
from app.auth import UserClaims, require_app
from app.config import get_settings

router = APIRouter(prefix="/apps/admin", tags=["admin"])
_require = require_app("admin")

_GITHUB_API = "https://api.github.com"
_CONFIG_PATH = "app/config.py"


# ── Schemas ───────────────────────────────────────────────────────────────────

class DeployPayload(BaseModel):
    users: dict[str, list[str]]


# ── Config patching helpers ───────────────────────────────────────────────────

def _build_user_roles_block(users: dict[str, list[str]]) -> str:
    """Render USER_ROLES as a Python literal block."""
    lines = ["USER_ROLES: dict[str, list[str]] = {"]
    for email in sorted(users.keys()):
        slugs = users[email]
        lines.append(f'    "{email}": [')
        for slug in slugs:
            lines.append(f'        "{slug}",')
        lines.append("    ],")
    lines.append("}")
    return "\n".join(lines)


def _patch_config_py(source: str, new_users: dict[str, list[str]]) -> str:
    """Replace the USER_ROLES block in config.py source with new values."""
    new_block = _build_user_roles_block(new_users)
    patched, n = re.subn(
        r'USER_ROLES: dict\[str, list\[str\]\] = \{.*?\}',
        new_block,
        source,
        flags=re.DOTALL,
    )
    if n != 1:
        raise ValueError(f"Expected to replace 1 USER_ROLES block, found {n}")
    return patched


# ── GitHub commit ─────────────────────────────────────────────────────────────

async def _github_commit(new_users: dict[str, list[str]]) -> str:
    """Fetch config.py from GitHub, patch USER_ROLES, commit back.

    Returns the short commit SHA on success.
    Raises HTTPException on any failure.
    """
    settings = get_settings()
    if not settings.github_token:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_TOKEN env var not set — cannot auto-commit. "
                   "Add it in Railway → Variables.",
        )

    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{_GITHUB_API}/repos/{settings.github_repo}/contents/{_CONFIG_PATH}"

    async with httpx.AsyncClient(timeout=15) as client:
        # ── Fetch current file + SHA ──────────────────────────────────────
        r = await client.get(url, headers=headers,
                             params={"ref": settings.github_branch})
        if r.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub fetch failed ({r.status_code}): {r.text[:300]}",
            )
        file_data = r.json()
        current_sha = file_data["sha"]
        current_source = base64.b64decode(file_data["content"]).decode()

        # ── Patch ─────────────────────────────────────────────────────────
        try:
            new_source = _patch_config_py(current_source, new_users)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        # ── Commit ────────────────────────────────────────────────────────
        r = await client.put(url, headers=headers, json={
            "message": "admin: update USER_ROLES via pez-portal admin panel",
            "content": base64.b64encode(new_source.encode()).decode(),
            "sha": current_sha,
            "branch": settings.github_branch,
        })
        if r.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"GitHub commit failed ({r.status_code}): {r.text[:300]}",
            )

    return r.json()["commit"]["sha"]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui() -> str:
    # Auth is handled client-side — the JS checks the token and redirects
    # to / if the user is not authenticated or lacks the admin role.
    # The /api/config and /api/deploy endpoints remain fully protected.
    return _ADMIN_HTML


@router.get("/api/config")
async def get_config(_user: UserClaims = Depends(_require)) -> dict:
    """Return current USER_ROLES and APP_REGISTRY as JSON."""
    return {
        "users": _cfg.USER_ROLES,
        "apps": [a for a in _cfg.APP_REGISTRY],
    }


@router.post("/api/deploy")
async def deploy(
    payload: DeployPayload,
    _user: UserClaims = Depends(_require),
) -> dict:
    """Commit updated USER_ROLES to GitHub and update in-memory state immediately.

    Changes take effect in the running container right away; Railway redeploys
    from the GitHub commit in ~2 minutes so the change survives restarts.
    """
    new_users = {k.strip().lower(): v for k, v in payload.users.items()}

    # Validate slugs
    valid_slugs = {a["slug"] for a in _cfg.APP_REGISTRY} | {"admin"}
    for email, slugs in new_users.items():
        bad = set(slugs) - valid_slugs
        if bad:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown app slugs for {email!r}: {sorted(bad)}",
            )

    # Commit to GitHub
    commit_sha = await _github_commit(new_users)

    # Update in-memory immediately (same process, same dict object)
    _cfg.USER_ROLES.clear()
    _cfg.USER_ROLES.update(new_users)

    settings = get_settings()
    return {
        "status": "deployed",
        "commit_sha": commit_sha[:8],
        "commit_url": f"https://github.com/{settings.github_repo}/commit/{commit_sha}",
        "message": "Saved. Railway will redeploy in ~2 min.",
    }


# ── Admin UI HTML ─────────────────────────────────────────────────────────────

_ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Admin — Pez Portal</title>
  <style>
    :root{--bg:#0f172a;--panel:#1e293b;--panel2:#273449;--text:#e2e8f0;
          --muted:#94a3b8;--accent:#38bdf8;--border:#334155;
          --ok:#34d399;--warn:#fbbf24;--err:#f87171;}
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:var(--bg);color:var(--text);min-height:100vh;}
    header{background:var(--panel);border-bottom:1px solid var(--border);
           padding:0 1.5rem;height:54px;display:flex;align-items:center;
           justify-content:space-between;}
    .hdr-left{display:flex;align-items:center;gap:0.75rem;}
    .hdr-title{font-weight:700;font-size:1rem;color:var(--accent);}
    .hdr-back{font-size:0.82rem;color:var(--muted);text-decoration:none;}
    .hdr-back:hover{color:var(--accent);}
    main{max-width:1000px;margin:0 auto;padding:2rem 1.5rem;}
    h2{font-size:1rem;font-weight:700;margin-bottom:1rem;color:var(--text);}
    .section{background:var(--panel);border:1px solid var(--border);
             border-radius:8px;padding:1.25rem;margin-bottom:1.5rem;}
    table{width:100%;border-collapse:collapse;font-size:0.83rem;}
    th{text-align:left;padding:0.45rem 0.6rem;color:var(--muted);
       border-bottom:1px solid var(--border);font-weight:500;white-space:nowrap;}
    td{padding:0.42rem 0.6rem;border-bottom:1px solid rgba(51,65,85,0.5);
       vertical-align:middle;}
    tr:last-child td{border-bottom:none;}
    .email-cell{font-size:0.84rem;}
    .cb-cell{text-align:center;}
    input[type=checkbox]{width:15px;height:15px;accent-color:var(--accent);cursor:pointer;}
    .btn-del{background:none;border:none;cursor:pointer;color:var(--muted);
             font-size:1rem;padding:0 4px;line-height:1;}
    .btn-del:hover{color:var(--err);}
    .add-row{display:flex;gap:0.6rem;margin-top:1rem;flex-wrap:wrap;align-items:center;}
    input[type=text]{background:var(--panel2);color:var(--text);
                     border:1px solid var(--border);border-radius:6px;
                     padding:0.42rem 0.75rem;font-size:0.84rem;width:260px;}
    input[type=text]:focus{outline:none;border-color:var(--accent);}
    .btn{background:var(--accent);color:#0f172a;font-weight:600;
         border:none;border-radius:6px;padding:0.45rem 1rem;
         font-size:0.84rem;cursor:pointer;}
    .btn:hover{opacity:0.88;}
    .btn:disabled{opacity:0.4;cursor:not-allowed;}
    .btn-ghost{background:none;border:1px solid var(--border);color:var(--muted);
               border-radius:6px;padding:0.45rem 0.9rem;font-size:0.84rem;cursor:pointer;}
    .btn-ghost:hover{border-color:var(--accent);color:var(--accent);}
    .deploy-bar{display:flex;gap:0.75rem;align-items:center;margin-bottom:1.5rem;}
    .dirty-badge{font-size:0.78rem;color:var(--warn);background:rgba(251,191,36,0.1);
                 border:1px solid var(--warn);border-radius:4px;
                 padding:0.15rem 0.5rem;display:none;}
    .dirty-badge.show{display:inline;}
    .status{font-size:0.82rem;padding:0.6rem 1rem;border-radius:6px;
            margin-bottom:1rem;display:none;}
    .status.ok{background:rgba(52,211,153,0.1);color:var(--ok);
               border:1px solid rgba(52,211,153,0.3);display:block;}
    .status.err{background:rgba(248,113,113,0.1);color:var(--err);
                border:1px solid rgba(248,113,113,0.3);display:block;}
    .apps-list{display:flex;flex-wrap:wrap;gap:0.5rem;}
    .app-chip{background:var(--panel2);border:1px solid var(--border);
              border-radius:4px;padding:0.2rem 0.6rem;font-size:0.78rem;color:var(--muted);}
    .spinner{display:inline-block;width:14px;height:14px;
             border:2px solid var(--border);border-top-color:var(--accent);
             border-radius:50%;animation:spin 0.8s linear infinite;vertical-align:middle;}
    @keyframes spin{to{transform:rotate(360deg);}}
  </style>
</head>
<body>
<header>
  <div class="hdr-left">
    <span style="font-size:1.1rem">⚙️</span>
    <span class="hdr-title">Portal Admin</span>
  </div>
  <a class="hdr-back" href="/">← Back to portal</a>
</header>

<main>
  <div id="status-bar" class="status"></div>

  <div class="deploy-bar">
    <button class="btn" id="btn-deploy" disabled onclick="deploy()">Deploy to GitHub</button>
    <button class="btn-ghost" id="btn-discard" style="display:none" onclick="discardChanges()">Discard changes</button>
    <span class="dirty-badge" id="dirty-badge">Unsaved changes</span>
    <span id="deploy-spinner" style="display:none"><span class="spinner"></span> Committing…</span>
  </div>

  <!-- Users section -->
  <div class="section">
    <h2>👤 Users</h2>
    <table id="users-table">
      <thead id="users-thead"></thead>
      <tbody id="users-tbody"></tbody>
    </table>

    <!-- Add user row -->
    <div class="add-row">
      <input type="text" id="new-email" placeholder="user@example.com" autocomplete="off"/>
      <button class="btn" onclick="addUser()">+ Add User</button>
    </div>
  </div>

  <!-- Apps section (read-only) -->
  <div class="section">
    <h2>📦 Registered Apps</h2>
    <div class="apps-list" id="apps-list"></div>
    <p style="font-size:0.78rem;color:var(--muted);margin-top:0.75rem;">
      Adding new apps requires a code change (new router + config.py entry + redeploy).
    </p>
  </div>
</main>

<script>
  // ── State ──────────────────────────────────────────────────────────────────
  let _config  = { users: {}, apps: [] };   // last saved state from server
  let _pending = {};                         // local working copy
  let _dirty   = false;

  const APP_SLUGS = [];  // filled after config load (excludes "admin")

  // ── Boot ───────────────────────────────────────────────────────────────────
  async function init() {
    const token = await getToken();
    if (!token) { window.location.href = "/"; return; }

    const resp = await apiFetch("/apps/admin/api/config", token);
    if (!resp.ok) { window.location.href = "/"; return; }

    _config = await resp.json();
    _pending = deepClone(_config.users);

    // Collect app slugs (exclude "admin" — it's a meta-role)
    APP_SLUGS.length = 0;
    (_config.apps || []).forEach(a => {
      if (a.slug !== "admin") APP_SLUGS.push(a.slug);
    });

    renderApps();
    renderTable();
  }

  // ── Token (from Auth0 SDK stored in localStorage) ─────────────────────────
  async function getToken() {
    // The portal stores the token in the Auth0 SPA SDK cache.
    // We reach it by re-initializing the client read-only.
    try {
      const client = await auth0.createAuth0Client({
        domain: "pezdev.us.auth0.com",
        clientId: "4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d",
        authorizationParams: { redirect_uri: window.location.origin, scope: "openid profile email" },
        cacheLocation: "localstorage",
      });
      if (!(await client.isAuthenticated())) return null;
      const claims = await client.getIdTokenClaims();
      return claims ? claims.__raw : null;
    } catch { return null; }
  }

  async function apiFetch(url, token, options = {}) {
    return fetch(url, {
      ...options,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json",
                 ...(options.headers || {}) },
    });
  }

  // ── Rendering ──────────────────────────────────────────────────────────────
  function renderTable() {
    // Header
    document.getElementById("users-thead").innerHTML = `<tr>
      <th>Email</th>
      ${APP_SLUGS.map(s => `<th class="cb-cell">${s}</th>`).join("")}
      <th></th>
    </tr>`;

    // Rows
    const emails = Object.keys(_pending).sort();
    document.getElementById("users-tbody").innerHTML = emails.map(email => `
      <tr>
        <td class="email-cell">${escHtml(email)}</td>
        ${APP_SLUGS.map(slug => `
          <td class="cb-cell">
            <input type="checkbox"
              ${(_pending[email] || []).includes(slug) ? "checked" : ""}
              onchange="toggleApp('${escAttr(email)}','${escAttr(slug)}',this.checked)"/>
          </td>`).join("")}
        <td><button class="btn-del" title="Remove user" onclick="removeUser('${escAttr(email)}')">🗑</button></td>
      </tr>`).join("") || `<tr><td colspan="${APP_SLUGS.length + 2}" style="color:var(--muted);padding:1rem 0.6rem;">No users yet.</td></tr>`;
  }

  function renderApps() {
    document.getElementById("apps-list").innerHTML =
      (_config.apps || []).filter(a => a.slug !== "admin").map(a =>
        `<div class="app-chip">${escHtml(a.icon || "")} ${escHtml(a.title)}</div>`
      ).join("");
  }

  // ── User edits ─────────────────────────────────────────────────────────────
  function toggleApp(email, slug, checked) {
    const slugs = _pending[email] || [];
    if (checked && !slugs.includes(slug)) slugs.push(slug);
    if (!checked) { const i = slugs.indexOf(slug); if (i > -1) slugs.splice(i,1); }
    _pending[email] = slugs;
    markDirty();
  }

  function addUser() {
    const input = document.getElementById("new-email");
    const email = input.value.trim().toLowerCase();
    if (!email || !email.includes("@")) { showStatus("Enter a valid email address.", false); return; }
    if (_pending[email]) { showStatus(`${email} is already in the list.`, false); return; }
    _pending[email] = [];
    input.value = "";
    markDirty();
    renderTable();
  }

  function removeUser(email) {
    if (!confirm(`Remove ${email}?`)) return;
    delete _pending[email];
    markDirty();
    renderTable();
  }

  function discardChanges() {
    _pending = deepClone(_config.users);
    markClean();
    renderTable();
  }

  // ── Dirty state ───────────────────────────────────────────────────────────
  function markDirty() {
    _dirty = true;
    document.getElementById("btn-deploy").disabled = false;
    document.getElementById("btn-discard").style.display = "";
    document.getElementById("dirty-badge").classList.add("show");
  }

  function markClean() {
    _dirty = false;
    document.getElementById("btn-deploy").disabled = true;
    document.getElementById("btn-discard").style.display = "none";
    document.getElementById("dirty-badge").classList.remove("show");
  }

  // ── Deploy ────────────────────────────────────────────────────────────────
  async function deploy() {
    // Always preserve admin's own "admin" slug so we don't lock ourselves out
    const payload = deepClone(_pending);
    for (const [email, slugs] of Object.entries(payload)) {
      // Re-inject "admin" for any user that had it in the saved config
      if ((_config.users[email] || []).includes("admin") && !slugs.includes("admin")) {
        slugs.unshift("admin");
      }
    }

    document.getElementById("btn-deploy").disabled = true;
    document.getElementById("deploy-spinner").style.display = "";
    document.getElementById("status-bar").className = "status";

    const token = await getToken();
    try {
      const resp = await apiFetch("/apps/admin/api/deploy", token, {
        method: "POST",
        body: JSON.stringify({ users: payload }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        showStatus("Error: " + (data.detail || resp.status), false);
        document.getElementById("btn-deploy").disabled = false;
      } else {
        showStatus(
          `✓ Committed <a href="${escHtml(data.commit_url)}" target="_blank" rel="noopener" style="color:var(--ok)">${data.commit_sha}</a> — ${escHtml(data.message)}`,
          true
        );
        _config = { ..._config, users: deepClone(payload) };
        markClean();
        renderTable();
      }
    } catch (e) {
      showStatus("Network error: " + e.message, false);
      document.getElementById("btn-deploy").disabled = false;
    } finally {
      document.getElementById("deploy-spinner").style.display = "none";
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function showStatus(html, ok) {
    const el = document.getElementById("status-bar");
    el.innerHTML = html;
    el.className = "status " + (ok ? "ok" : "err");
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function deepClone(obj) { return JSON.parse(JSON.stringify(obj)); }

  function escHtml(s) {
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
                    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }
  function escAttr(s) { return String(s).replace(/'/g,"&#39;").replace(/"/g,"&quot;"); }

  // Auth0 SDK needed for getToken()
  const sdk = document.createElement("script");
  sdk.src = "https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js";
  sdk.onload = init;
  document.head.appendChild(sdk);
</script>
</body>
</html>"""
for getToken()
  const sdk = document.createElement("script");
  sdk.src = "https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js";
  sdk.onload = init;
  document.head.appendChild(sdk);
</script>
</body>
</html>"""
