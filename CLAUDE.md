# Innovation Portal (pez-portal) — v1.4.0

Auth0-gated internal app portal for NACS / TruAge tools. Deployed on Railway.
Production custom domain: `https://dashboard.mytruage.org` (also reachable at
`nacsportal.up.railway.app`, but users should use the custom domain — see SSO below).

## Architecture

- **Stack**: Python 3.12, FastAPI, Auth0 SPA SDK v2 (client-side), pydantic-settings, structlog
- **Auth pattern**: Auth0 RS256 JWT. HTML shell routes return 200 freely — auth is
  handled client-side via Auth0 SPA SDK. All `/api/*` sub-routes are protected by
  `require_auth` / `require_app` FastAPI dependencies.
- **SSO handoff to sub-apps (v1.4.0)**: after login, `portal.html` writes the Auth0
  ID token to a `pez_id_token` cookie with `Domain=dashboard.mytruage.org` so
  sub-apps on subdomains (e.g. BenchPoint at `benchpoint.dashboard.mytruage.org`)
  pick up the session with zero additional prompts. The cookie is only set when the
  portal is accessed via the custom domain (`*.up.railway.app` is a public suffix —
  cookies cannot span it). Cleared on logout. Sub-app backends validate the JWT
  signature/issuer themselves and keep their own access gates.
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
  - `CRON_SECRET` — protects `/api/cron/run-daily`
  - `RESEND_API_KEY` — email delivery for daily reports (get from resend.com)
  - `RAILWAY_API_TOKEN` — needed for admin panel schedule editor (GraphQL API)
  - `APPLE_KEY_ID`, `APPLE_ISSUER_ID`, `APPLE_PRIVATE_KEY` — App Store Connect API (app_downloads module)
- Deploy: push to GitHub main → Railway auto-deploys.

## Key files

```
app/
  main.py              # FastAPI app factory, /api/me, /health, /api/cron/run-daily, /api/daily-status
  config.py            # APP_REGISTRY, USER_ROLES, EMAIL_SUBSCRIPTIONS, Settings
  auth.py              # JWT verification, require_auth, require_app dependencies
  daily_cache.py       # In-memory DailyCache; account_cache + activation_cache singletons
  email_service.py     # Resend-based email delivery for daily reports
  static/
    portal.html        # Login card + app grid SPA (Auth0 client-side)
    logo.gif           # NACS Innovation animated logo (loop=3, ~37 frames)
    nacs-innovation-logo.gif  # Cream-bg lightbulb-with-rings logo (loop=3)
  routers/
    admin/routes.py          # Admin panel — USER_ROLES, EMAIL_SUBSCRIPTIONS, report schedule
    truage_activation/routes.py   # TruAge Activation — proxies nacstar, caches daily
    truage_account/routes.py      # TruAge Account Manager — proxies nacstam (truage-pulse), caches daily
    app_downloads/routes.py       # App Downloads — Apple App Store daily install tracking
    stock/routes.py               # MarketMaker card wiring (external app)
    benchmark/                    # VESTIGIAL — empty; BenchPoint is an EXTERNAL card, no router wired
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
- MarketMaker:       `#6741d9` purple (card) / `#36ECDE` mint (dashboard UI)
- App Downloads:     `#2563EB` royal blue

## User / Role Management

`app/config.py` holds `USER_ROLES` dict mapping email → list of app slugs.
The admin panel (`/apps/admin/`) lets admins edit this via the GitHub API —
it commits a new `config.py` directly to the repo, triggering a Railway redeploy.

Currently authorised users:
- `ziv.paul@gmail.com` — all apps (admin, app_downloads, benchmark, truage_activation, truage_account, truage_dictionary, stock)
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

> **See `ADD_CARD_README.md` in the repo root for the full step-by-step guide**,
> including field reference, color conventions, git workflow, and conflict resolution.

1. Add entry to `APP_REGISTRY` in `app/config.py`
2. Add `slug` to relevant users in `USER_ROLES`
3. Create `app/routers/<slug>/routes.py` with router (external apps skip steps 3–5)
4. Register router in `app/main.py`
5. Add a test to `tests/test_routes.py`

## MarketMaker architecture (security boundary)

MarketMaker (`paulziv/marketmaker` → `stock-tracker-production-0582.up.railway.app`) is a
**read-only** subset of the full stock-tracker application.

- **MarketMaker (deployed on Railway)**: market intelligence only — live quotes, news
  synthesis, AI council of bots, strategy lab, ML/analysis. Zero trading capability.
- **stock-tracker (NOT on Railway)**: full trading platform — includes everything in
  MarketMaker plus order execution, brokerage API credentials, and transaction management.
  Kept off Railway intentionally: if the Railway service were compromised, an attacker
  could not execute trades or access financial accounts.

The Railway service slug is `stock` for role compatibility. The GitHub repo `paulziv/marketmaker`
is the source of truth for what is deployed — **stock-tracker code must never be pushed there.**

## BenchPoint integration

BenchPoint (`https://benchpoint.dashboard.mytruage.org/ui/`) is a service
inside the `nacs-portal` Railway project (service: `nacs-990-benchmark`).

- **SSO**: ✅ Resolved — BenchPoint now uses the same Auth0 client ID
  (`4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d`) and `getIdTokenClaims().__raw` token pattern.
  Silent iframe auth (`getTokenSilently()`) was removed — it hangs in Chrome with
  third-party cookie blocking.
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
- **Daily report cron**: Railway cron service `daily-reports-cron` (ID: `a42ef700`)
  runs at 13:00 UTC (7 AM CT) using image `alpine/curl`. startCommand hardcodes the
  token directly in the URL — Railway does NOT reliably expand `$VAR` in startCommands:
  `curl -fsS -X POST https://nacsportal.up.railway.app/api/cron/run-daily?token=TOKEN`
  Both truage_account and truage_activation are populated in one call (~4 min).
  In-memory cache — clears on redeploy, repopulated by next scheduled cron run.
  Endpoint also accepts `Authorization: Bearer TOKEN` header for manual curl calls.
- **Proxied report nav bar**: `_inject_base()` in truage_account and truage_activation
  routers strips `<nav>` elements from the upstream HTML so the nacstam/nacstar app's
  own navigation (Account Management / Dictionary / Settings) doesn't show in the iframe.
- **Magic-link report delivery**: emails contain a 24-hour token URL (`/report/{token}`)
  — no portal login required. Token stored in `report_tokens` Postgres table. Expired
  tokens are purged on each cron run. See `app/report_tokens.py`.
- **Persistent report cache**: `daily_cache.py` writes to `report_cache` Postgres table
  on every `set()` and restores from DB on startup. Redeploys no longer wipe the cache.
- **Email sender**: `portal@dashboard.mytruage.org` (verified Resend domain).
  `RESEND_FROM` env var on Railway.
- **App Downloads cron**: fetches last 3 days on every run (covers weekend gaps when cron
  is weekday-only). Uses `ON CONFLICT DO NOTHING` — safe to run multiple times. Data stored
  permanently in `app_downloads` Postgres table (no expiry).
- **App Downloads backfill**: `POST /api/cron/backfill-downloads?token=CRON_SECRET` — fires
  once to pull up to 365 days of Apple history. Runs in background (~2 min). Safe to re-run.
- **Apple API key**: Key ID `TZ558AFZ78`, Issuer ID `b5455d5d-e506-4fe3-9f1d-58b3ec91cdfb`,
  vendor number `92675371`, app ID `6472091941` (SKU: org.mytruage.app.mobile.production).
  Private key stored as `APPLE_PRIVATE_KEY` env var on Railway (full .p8 PEM content).
- **Google Play**: slot is wired — set `GOOGLE_PLAY_CREDENTIALS` (service account JSON)
  and `GOOGLE_PLAY_PACKAGE_NAME` on Railway to activate Android tracking.

## App Downloads manual commands

```bash
# Test Apple fetch for yesterday only (no emails)
curl -s -X POST "https://nacsportal.up.railway.app/api/cron/run-downloads?token=CRON_SECRET"

# Trigger full 365-day backfill (background, ~2 min)
curl -s -X POST "https://nacsportal.up.railway.app/api/cron/backfill-downloads?token=CRON_SECRET"

# Check Railway logs for download activity
railway logs --service pez-portal | grep app_download
```


---

## ✅ Verified against code — 2026-07-02 (reconciliation)

This portal is the **umbrella app**. Below is the code-verified reality; a few
older lines above were slightly ahead of / behind the code and are corrected here.

### Framework & entry
- **FastAPI** + **uvicorn** (1 worker), Python 3.12. NOT Flask. Entry: `app/main.py::create_app()`.
- Deps (`requirements.txt`): fastapi, uvicorn[standard], python-jose[cryptography] (Auth0 JWT), httpx (proxying), pydantic-settings, structlog, resend (email), psycopg2-binary (Postgres), aiofiles (StaticFiles).
- Swagger/`/openapi.json` are exposed **only when not production** (they'd list the admin GitHub-commit and Railway-cron endpoints).

### Routers actually wired in `main.py`
`admin`, `truage_activation`, `truage_account`, `stock`, `app_downloads`.
There is **no `truage_dictionary` router** — the "TruAge Data Dictionary" card is an
**external link** to `https://nacstam.up.railway.app/dictionary` (i.e. truage-pulse's
own /dictionary page). The `benchmark/` folder is **empty/vestigial**; BenchPoint is an
external subdomain card, not a proxied router.

### Sub-app / upstream map (the key cross-service dependency)
| Portal card (slug) | Internal? | Upstream / URL | Backing repo |
|---|---|---|---|
| TruAge Activation (`truage_activation`) | proxy router | `https://nacstar.up.railway.app` | `truage-activation-report` |
| TruAge Account Manager (`truage_account`) | proxy router | `https://nacstam.up.railway.app` | `truage-pulse` |
| TruAge Data Dictionary (`truage_dictionary`) | external card | `https://nacstam.up.railway.app/dictionary` | `truage-pulse` |
| BenchPoint (`benchmark`) | external card | `https://benchpoint.dashboard.mytruage.org/ui/` | `nacs-990-benchmark` |
| MarketMaker (`stock`) | external card | `https://pezmarketmaker.up.railway.app` | `marketmaker` |
| C-Store Intel (`cstore_intel`) | external card | `https://scraping.up.railway.app` | `convenience-store-intel` |
| Patent Atlas (`patent_atlas`) | external card | `https://patent-atlas.dashboard.mytruage.org` | *(not in our scope; separate repo)* |
| Personal Email Agent (`personal_email`) | external card | `https://email-monitor.up.railway.app/` | *(personal project — ignore)* |
| App Downloads (`app_downloads`) | internal router | `/apps/app-downloads/` (Apple App Store Connect API) | this repo |
| Admin (`admin`) | internal router | `/apps/admin/` | this repo |

APP_REGISTRY lives in `app/config.py` (also holds `USER_ROLES` and `EMAIL_SUBSCRIPTIONS`).

### How proxy / cache / email actually work (verified)
- **Proxy**: `truage_activation` and `truage_account` routers fetch the upstream report
  HTML with httpx and run it through `_inject_base()` — injects `<base href="{upstream}/">`
  and strips the upstream `<nav>` so the embedded report has no duplicate navigation.
- **Refresh semantics differ**: activation's `run_daily()` POSTs `{nacstar}/refresh`
  (triggers a fresh HubSpot pull) then polls `/`. Account manager (`nacstam`/pulse) has
  **no `/refresh`** — it pulls live — so `run_daily()` just GETs `{nacstam}/audit/report`.
- **Cache**: `app/daily_cache.py` — `account_cache` + `activation_cache` singletons; writes
  each snapshot to the Postgres `report_cache` table and restores on startup (survives redeploys).
- **Email**: `app/email_service.py` uses **Resend** (from `portal@dashboard.mytruage.org`).
  Daily emails contain a 24-hour **magic-link** `/report/{token}` (no login) — tokens in the
  Postgres `report_tokens` table (`app/report_tokens.py`), purged each cron run.
- **Cron**: `POST /api/cron/run-daily?token=CRON_SECRET` fires all three `run_daily()` tasks
  in the background (Railway cron `daily-reports-cron`, 13:00 UTC / 7am CT). Also:
  `/api/cron/run-downloads`, `/api/cron/backfill-downloads`, and `/api/cron/watchdog`
  (emails Paul if either daily report didn't populate today). All gated by `CRON_SECRET`
  via `?token=` or `Authorization: Bearer`.
- **Auth**: Auth0 SPA (client-side) issues an RS256 ID token; `portal.html` stores it in a
  `pez_id_token` cookie scoped to `dashboard.mytruage.org` for SSO into subdomain sub-apps.
  `/api/*` protected by `require_auth`/`require_app`; `/api/me` returns the caller's visible
  apps from `USER_ROLES`. HTML shells return 200 freely (gate is client-side + per-API).

### Note on the two Postgres databases
This portal reads `PORTAL_DATABASE_URL` (see `app_downloads/routes.py`) for its own tables
(`report_cache`, `report_tokens`, `app_downloads`), which is a **separate** database from the
`DATABASE_URL` used by the truage-activation-report / truage-pulse services. **Verified 2026-07-02:** there are 3 Postgres services in the `nacs-portal` Railway project — this shared `Postgres` (`postgres-production-2909c…`, used by pez-portal + both TruAge backends), `cstore-postgres` (cstore only), and `nacs-990-db-postgres` (BenchPoint only).
