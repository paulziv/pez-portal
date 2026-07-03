# TruAge / NACS Ecosystem — Architecture

> The one map of the whole thing: every Railway service, the repo behind it, what it does,
> and how the pieces depend on each other. Read this first; then the per-repo `CLAUDE.md`s
> and `docs/REPORTS.md` for detail. Companion infra doc: `C:\dev\INFRA_README.md`.
> **Railway topology verified live from the dashboard on 2026-07-02.**

## The 10-second picture

```
                         Auth0 (pezdev.us.auth0.com)
                                   │  (shared client 4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d)
                                   ▼
   Browser ─▶ Innovation Portal  (pez-portal @ dashboard.mytruage.org)
                    │  proxies + caches + emails the TruAge reports; SSO cookie to subdomains
                    ├─ proxy ─▶ nacstar  (truage-activity-report)  ── HubSpot ──┐
                    ├─ proxy ─▶ nacstam  (truage-pulse / AM audit)   ── HubSpot ──┤
                    ├─ link  ─▶ benchpoint (nacs-990-benchmark)      ── IRS/LLM   │
                    ├─ link  ─▶ scraping   (cstore-frontend)         ── scrapers  │
                    └─ link  ─▶ patent-atlas, pezmarketmaker (separate project)   │
                                              one HubSpot private app (Retailer Activations
                                              pipeline + Stores custom object) ◀───────────┘
```

## Railway projects (verified 2026-07-02)

Paul's Railway account has **4 projects**. Everything in the TruAge/NACS ecosystem lives in
**one** of them — `nacs-portal`. (An earlier guess that TruAge and cstore were split into two
projects was wrong — they share `nacs-portal`.)

| Railway project | In scope? | Contents |
|---|---|---|
| **nacs-portal** (`7376f7ae-…`) | ✅ the ecosystem | portal, both TruAge report backends, BenchPoint, all cstore services, patent-atlas, both crons, 3 Postgres DBs, mcp-demo |
| **marketmaker** | ➖ out of scope | MarketMaker (read-only market intel), 2/3 services |
| **email-monitor** | ➖ ignore | personal Gmail project (not work) |
| **etsyflow** | ➖ out of scope | Etsy project (Postgres + app) |

### `nacs-portal` project — all 14 services (env: `production`, `373d0dd2-…`)
| Service | Svc ID (short) | Repo | Purpose |
|---|---|---|---|
| **pez-portal** | `a342375c` | `pez-portal` | Umbrella portal @ dashboard.mytruage.org. FastAPI. |
| **truage-activity-report** | `5e62252b` | `truage-activation-report` | `nacstar.up.railway.app`. Weekly Activation Report; HubSpot Deals+Stores. |
| **truage-pulse** | `4361dcde` | `truage-pulse` | `nacstam.up.railway.app`. AM Assignment Audit + Dictionary. |
| **nacs-990-benchmark** | `aa735a95` | `nacs-990-benchmark` | `benchpoint.dashboard.mytruage.org`. 990 benchmarking. |
| **cstore-frontend** | `190f47d2` | `convenience-store-intel` | `scraping.up.railway.app`. React/Vite + nginx (public entry). |
| **cstore-backend** | `d82a7d31` | `convenience-store-intel` | Express/Prisma API (private). |
| **cstore-scraper** | `f4e4af28` | `convenience-store-intel` | FastAPI + APScheduler scraper. |
| **cstore-postgres** | `b75ce75f` | — | Postgres `cstore_db` for the cstore services. |
| **Postgres** | `6b0771a2` | — | `postgres-production-2909c…` — shared by pez-portal + both TruAge services (see DBs below). |
| **nacs-990-db-postgres** | — | — | Postgres for BenchPoint (`bench_cache` / `bench_xml`). |
| **daily-reports-cron** | `a42ef700` | (cron) | Hits `POST {portal}/api/cron/run-daily` daily (13:00 UTC / 7am CT). |
| **daily-reports-watchdog** | `1b24be99` | (cron) | Hits `POST {portal}/api/cron/watchdog`; emails Paul if a report didn't populate. |
| **patent-atlas** | — | *(separate repo, not in this pass)* | `patent-atlas.dashboard.mytruage.org`. |
| **mcp-demo** | — | *(demo)* | ⚠️ "Build failed last week" — a demo service, not part of the ecosystem. |

Out-of-project but portal-linked: **MarketMaker** (`pezmarketmaker.up.railway.app`, project
`marketmaker`) and the personal **email-monitor** (`email-monitor.up.railway.app`).

## Per-service summary (in scope)

| Service | Framework | Deploy | Key external deps |
|---|---|---|---|
| pez-portal | **FastAPI** + uvicorn | Nixpacks, `/health` | Auth0, HubSpot (indirect via proxies), Resend, GitHub API (admin), Railway GraphQL API (admin) |
| truage-activity-report | **Flask** + gunicorn | Dockerfile | HubSpot (`HUBSPOT_TOKEN`), Resend (alerts), Postgres (opt) |
| truage-pulse | **Flask** + gunicorn | Dockerfile | HubSpot (`HUBSPOT_PRIVATE_APP_TOKEN`), Postmark (email), Postgres/SQLite |
| nacs-990-benchmark | **FastAPI** + uvicorn | Dockerfile | Gemini→OpenAI→Anthropic cascade, IRS/ProPublica/SEC, Resend, Postgres |
| convenience-store-intel | **React/Vite** + **Express/Prisma** + **FastAPI** scraper | Docker (multi-service) | OSM/USDA-SNAP/TomTom/HERE/Foursquare, Postgres |

## Cross-service dependencies (the wiring that matters)

- **Portal → TruAge report backends (proxy).** pez-portal's `truage_activation` router
  proxies `https://nacstar.up.railway.app` (and POSTs `/refresh` to trigger a fresh HubSpot
  pull); `truage_account` router proxies `https://nacstam.up.railway.app` (GET `/audit/report`;
  pulse has no `/refresh`). Both strip the upstream `<nav>` via `_inject_base()`. **If nacstar/
  nacstam are down, the portal's TruAge cards fail** (502/504).
- **Daily cron fan-out.** `daily-reports-cron` (13:00 UTC / 7am CT) hits
  `POST {portal}/api/cron/run-daily?token=CRON_SECRET`, which refreshes + caches both TruAge
  reports and App Downloads, then emails magic-link report URLs (Resend). `daily-reports-watchdog`
  hits `/api/cron/watchdog` and emails Paul if either report didn't populate that day.
- **Shared Auth0 + SSO cookie.** Tenant `pezdev.us.auth0.com`, client `4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d`.
  After login, pez-portal writes `pez_id_token` (ID-token JWT) as a cookie scoped to
  `dashboard.mytruage.org`. **BenchPoint has no Auth0 client of its own** — it reads that cookie.
  This only works via the custom domain (`*.up.railway.app` is a public suffix; cookies can't span it).
- **Access control source of truth.** `USER_ROLES` in `pez-portal/app/config.py` (email → app
  slugs) governs which cards a user sees; the admin panel edits it by committing `config.py` via
  the GitHub API, triggering a Railway redeploy. BenchPoint's own gate is the `bench_users` table.
- **Shared HubSpot — ONE private app (confirmed).** Both TruAge services hit the same HubSpot org
  using the **same private-app token** — HubSpot forces a private app, and Paul reused one token
  to avoid maintaining two apps. The env-var *names* differ only by history:
  `HUBSPOT_TOKEN` (truage-activity-report) and `HUBSPOT_PRIVATE_APP_TOKEN` (truage-pulse) carry
  the same value.
- **Email providers diverge.** pez-portal, truage-activity-report, and nacs-990 use **Resend**;
  truage-pulse uses **Postmark**. Not a bug, but a consistency wart worth knowing.

## Databases — 3 Postgres instances (confirmed)

| Railway service | Used by | Holds |
|---|---|---|
| **Postgres** (`postgres-production-2909c…`, svc `6b0771a2`) | pez-portal (`PORTAL_DATABASE_URL`) + truage-activity-report & truage-pulse (`DATABASE_URL`) | portal `report_cache` / `report_tokens` / `app_downloads`; the two TruAge services' run history |
| **cstore-postgres** (`b75ce75f`) | cstore-backend (Prisma) + cstore-scraper (psycopg2) | `cstore_db` — 170k+ store records, scrape jobs |
| **nacs-990-db-postgres** | nacs-990-benchmark | `bench_cache` / `bench_xml` |

## Deploy model (from INFRA_README)
GitHub (`github.com/paulziv`) is source of truth; Railway auto-deploys from each repo's default
branch on push. **cstore's default branch is `master`; all others use `main`.** Never edit code
on Railway directly.

## Operational notes spotted in Railway logs (2026-07-02) — not doc-critical
- **cstore Foursquare scraping is failing 100%** — every state returns `401 Unauthorized`
  (`FOURSQUARE_API_KEY` appears invalid/expired). The scraper degrades gracefully (logs "0 places").
- **cstore-scraper hourly `_retry_pending_jobs` throws `RuntimeError: no running event loop`** —
  the APScheduler lambda calls `asyncio.create_task` outside the loop. Retries aren't running.
- **mcp-demo** in nacs-portal has a failed build (unrelated to the ecosystem).
These are flagged for awareness only; fixing them is out of scope for this documentation pass.


---

## ✅ Phase 1 shipped (2026-07-03) — shared `truage-core` library
The two TruAge report backends no longer carry duplicated HubSpot code. A shared package
**`truage-core`** (private repo `paulziv/truage-core`, v0.1.0) is the single source for:
`config` (pipeline/stage roles, deal/store properties, GOAL, owner-ID maps), `testrecords`
(the two test-exclusion rules), and `hubspot` (unified fail-loud client + high-level pulls).
Both `nacstar` (truage-activity-report) and `nacstam` (truage-pulse) depend on it via a git+PAT
pin in requirements; their Dockerfiles install `git` for the build. ~450 lines of duplication
removed; both reports verified byte-identical. Next phases (logging/tracing, single cache,
Resend unification) per `PORTAL_VNEXT_MIGRATION.md`.
