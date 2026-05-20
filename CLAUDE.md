# Innovation Portal (pez-portal)

Auth0-gated internal app portal for NACS / TruAge tools. Deployed on Railway.

## Architecture

- **Stack**: Python 3.12, FastAPI, Auth0 SPA SDK v2 (client-side), pydantic-settings, structlog
- **Auth pattern**: Auth0 RS256 JWT. HTML shell routes return 200 freely — auth is
  handled client-side via Auth0 SPA SDK. All `/api/*` sub-routes are protected by
  `require_auth` / `require_app` FastAPI dependencies.
- **Token pattern**: Always use `getIdTokenClaims().__raw` (the ID token JWT), NOT
  `getTokenSilently()`. Without an `audience`, Auth0 returns an opaque access token
  that python-jose cannot verify.
- **Static files**: served via `StaticFiles` mount — requires `aiofiles` in
  requirements.txt or Railway startup will crash with "Not Found".
- **Single worker** (Railway free tier) — no shared state issues.

## Auth0 Config

- Tenant:    `pezdev.us.auth0.com`
- Client ID: `4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d`
- Allowed Callback + Logout URLs: `https://nacsportal.up.railway.app`
- Allowed Web Origins: `https://nacsportal.up.railway.app`

## Deployment

- **Production**: `https://nacsportal.up.railway.app`
- **Platform**: Railway (auto-deploys from `paulziv/pez-portal` main branch)
- **Env vars** required on Railway:
  - `AUTH0_CLIENT_ID`, `AUTH0_DOMAIN`, `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH`
- Deploy: push to GitHub main → Railway auto-deploys.

## Key files

```
app/
  main.py              # FastAPI app factory, /api/me, /health
  config.py            # APP_REGISTRY, USER_ROLES, Settings (pydantic-settings)
  auth.py              # JWT verification, require_auth, require_app dependencies
  static/
    portal.html        # Login card + app grid SPA (Auth0 client-side)
    logo.gif           # NACS Innovation animated logo (loop=3, ~37 frames)
    nacs-innovation-logo.gif  # New cream-bg lightbulb-with-rings logo (loop=3)
  routers/
    admin/routes.py          # Admin panel — edit USER_ROLES via GitHub API
    stock/routes.py          # Market Dashboard — Deribit public API proxy
    truage_activation/routes.py   # TruAge Activation report
    truage_account/routes.py      # TruAge Account Manager
    truage_dictionary/routes.py   # TruAge Data Dictionary
tests/
  test_config.py       # APP_REGISTRY structure, USER_ROLES integrity
  test_routes.py       # HTTP-level route tests via TestClient
  test_admin_patch.py  # Unit tests for admin panel config patching
```

## Brand Palette

```
--bg:      #F5F0E8  warm cream background
--surface: #FFFFFF  card surface
--border:  #DDD8CE  sand border
--text:    #1A2332  ink
--muted:   #7A7060  warm gray
--navy:    #00203F  Core Navy (header, buttons)
--accent:  #2E6DA4  Mid Blue (links, arrows)
--mint:    #36ECDE  Neon Mint (header title, hover glow)
--danger:  #C0392B  error red
```

Per-app accent colors (card left border):
- Admin:             `#64748b` slate
- BenchPoint:        `#005eb8` blue
- TruAge Activation: `#087f5b` teal-green
- TruAge Account:    `#b36b00` amber
- TruAge Dictionary: `#0c6e5c` dark teal
- Market Dashboard:  `#6741d9` purple (card) / `#36ECDE` mint (dashboard UI)

## User / Role Management

`app/config.py` holds `USER_ROLES` dict mapping email → list of app slugs.
The admin panel (`/apps/admin/`) lets admins edit this via the GitHub API —
it commits a new `config.py` directly to the repo, triggering a Railway redeploy.

Currently authorised users:
- `ziv.paul@gmail.com` — all apps (admin, benchmark, truage_activation, truage_account, truage_dictionary, stock)
- `fgleeson@convenience.org` — benchmark, stock, truage_account, truage_activation, truage_dictionary (intentional showcase)
- `lorijoziv@gmail.com` — benchmark, stock
- `lrountree@mytruage.org` — truage_activation, truage_account, truage_dictionary
- `pabernathy@mytruage.org` — truage_activation, truage_account, truage_dictionary
- `ssikorski@convenience.org` — truage_activation, truage_account, truage_dictionary

## Adding a new user

1. Open `https://nacsportal.up.railway.app/apps/admin/`
2. Click "Add user", enter email, tick the desired app checkboxes
3. Click "Deploy changes" — Railway redeploys in ~60 seconds

Or directly in `app/config.py`:
```python
USER_ROLES["new.user@example.com"] = ["benchmark", "truage_activation"]
```
Then push to GitHub main.

## Adding a new app

1. Add entry to `APP_REGISTRY` in `app/config.py`
2. Add `slug` to relevant users in `USER_ROLES`
3. Create `app/routers/<slug>/routes.py` with router
4. Register router in `app/main.py`
5. Add a test to `tests/test_routes.py`

## BenchPoint integration (open items)

BenchPoint (`https://nacs-990-benchmark-production.up.railway.app/ui/`) is a service
inside the `nacs-portal` Railway project (service: `nacs-990-benchmark`).

- **SSO**: BenchPoint uses a different Auth0 client ID — users must log in twice.
  Fix: update BenchPoint to use client ID `4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d`
  (same as pez-portal) on tenant `pezdev.us.auth0.com`.
- **Brand colours**: BenchPoint UI has some off-brand colours (Bootstrap defaults).
  Needs CSS update in the `paulziv/nacs-990-benchmark` repo.

## Common commands

```bash
# Install deps
pip install -r requirements.txt -r requirements-dev.txt

# Run locally
AUTH0_DOMAIN=pezdev.us.auth0.com AUTH0_CLIENT_ID=4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d \
  uvicorn app.main:app --reload --port 8080

# Run tests
python3 -m pytest tests/ -q

# Deploy
git push origin main   # Railway auto-deploys
```

## Known gotchas

- **File truncation**: Large Python files with embedded HTML strings can truncate
  during context-window edits. Use `python3 -c "import ast; ast.parse(open(f).read())"` 
  to validate all files before pushing. The admin panel now validates with `ast.parse`
  before committing to GitHub, but direct edits have no such guard.
- **Config caching**: `get_settings()` is `@lru_cache`. If you change `.env` at
  runtime, restart the server.
- **Admin panel GitHub deploy**: requires `GITHUB_TOKEN` env var with `repo` scope
  and `GITHUB_REPO=paulziv/pez-portal` set on Railway.
- **Railway auth**: use `RAILWAY_API_TOKEN` (not `RAILWAY_TOKEN`) for non-interactive
  CLI and GraphQL API access. Token from https://railway.com/account/tokens.
