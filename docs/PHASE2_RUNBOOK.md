# Phase 2 Runbook — Logging, Tracing & one Ops view

> Goal: one JSON log format everywhere, a correlation ID that follows a request/cron-run across
> portal → backends, and a shared run/error log surfaced on a single portal ops page — replacing
> per-service `/history` + `/errors` islands and "scroll three log streams."
> Foundation shipped in **truage-core v0.2.0** (`logging`, `runlog`), unit-tested.

## Built (this session) — truage-core v0.2.0
- `truage_core.logging`: `configure_logging(level, service=…)`, `get_logger()`, correlation id via
  contextvar — `new_request_id()`, `bind_request_id()`, `current_request_id()`, `outgoing_headers()`
  (`X-Request-ID`), and a structlog processor that stamps `request_id` + `service` on every line.
- `truage_core.runlog`: `init_tables()`, `record_run(...)`, `record_error(...)`,
  `recent_runs(...)`, `recent_errors(...)` — Postgres via `DATABASE_URL` (the shared nacs-portal
  Postgres), SQLite fallback locally.

## Publish v0.2.0 (you)
`git tag v0.2.0 && git push origin v0.2.0` in truage-core, then bump the pin in all three services'
`requirements.txt` to `@v0.2.0`.

## Adoption — services (Claude edits; low risk, no characterization gate needed since these are
observability side-effects, but verified by import + a live cron run)
**truage-activity-report** and **truage-pulse**:
1. At startup call `truage_core.logging.configure_logging("INFO", service="nacstar"|"nacstam")`.
2. Replace the local run/error persistence with `truage_core.runlog`:
   - activation `run_history.record_run(...)` → `runlog.record_run("nacstar","activation",…)`.
   - pulse `storage.record_error(...)`/`get_recent_errors` → `runlog.record_error("nacstam",…)` / `recent_errors`.
   (Keep pulse's settings/rules/score storage as-is — audit-specific.)
3. Correlation id (Flask): a `@app.before_request` that does
   `truage_core.logging.bind_request_id(request.headers.get("X-Request-ID"))`.

## Adoption — portal (Claude edits)
1. `configure_logging("INFO", service="pez-portal")` at startup (replaces the inline structlog block).
2. FastAPI middleware: read-or-mint `X-Request-ID`, `bind_request_id`, echo on response.
3. On the proxied calls in `truage_activation`/`truage_account` routers and the cron `run_daily`
   fan-out, add `headers=truage_core.logging.outgoing_headers()` to the httpx requests → the id now
   spans portal → nacstar/nacstam in the logs.
4. Cron: wrap each `run_daily` with `runlog.record_run(...)` (ok/error + duration + correlation id).
5. **Ops page:** add `GET /api/ops` (admin-gated) returning `runlog.recent_runs()/recent_errors()`,
   and extend `app/static/ops.html` to render them (filter by service). Retire per-service
   `/history` + `/errors` once this is in.

## Deploy + verify
- Push all three; confirm builds. Trigger `POST /api/cron/run-daily`.
- **Success = one `request_id` value appears in portal logs AND the matching nacstar/nacstam log
  lines for that run**, and the ops page lists the run (+ any error) across services.

## Then — remaining phases (recommended order)
- **Phase 6 (Resend unify) — small, do next.** Add `truage_core.email` (Resend wrapper); point
  pulse's `pulse/email.py` at it; retire Postmark. One provider/key/domain.
- **Phase 5 (portal owns cache).** Make backends stateless; portal `report_cache` becomes the only
  cache — remove pulse's in-proc `cached(300)` and any activation `/tmp` remnants.
- **Phase 7 (optional, biggest).** Merge nacstar+nacstam into one `truage-reports` FastAPI service
  (two routers, reports stay distinct) on the shared report-app skeleton. Reversible via hostname
  aliases; only worth it once 2/5/6 are in.
- (Phases 3–4 already shipped in Phase 1.)

## Rollback
truage-core is tag-pinned (immutable), so v0.2.0 can't shift under you. Per-service adoption is a
small revert + re-pin to v0.1.0. Logging/runlog changes are additive — worst case a service logs
in the old format; no report output is affected.

---

## Phase 2 — AS-BUILT (code complete, pending deploy)

**truage-core v0.2.1** adds:
- `logging.configure_stdlib_json(level, service=…)` + `JsonFormatter`/`RequestIdFilter` — one-line JSON logs w/ `request_id`+`service` for the stdlib-logging Flask apps, **no call-site changes**.
- `logging` correlation-id contextvar: `new_request_id`, `bind_request_id`, `current_request_id`, `outgoing_headers()`, `REQUEST_ID_HEADER="X-Request-ID"`.
- `runlog` shared `run_log`/`error_log` with **`RUNLOG_DATABASE_URL`** precedence (→ `DATABASE_URL` → SQLite).

**Code changes (all self-verified: 24/24 core tests, py_compile clean):**
- activation `app.py` — `configure_stdlib_json(service="nacstar")`, `before_request` adopts `X-Request-ID`, `run_history`→`runlog`, `/history` reads `runlog`.
- pulse `app.py` — same, `service="nacstam"`; `storage.record_error`→`runlog.record_error`, `/errors` reads `runlog`.
- portal `main.py` — `@app.middleware("http")` mints/adopts+echoes `X-Request-ID` (bound into structlog contextvars + tclog); `runlog.init_tables()` on startup (portal owns the DB); admin-gated `GET /api/ops` → `{runs, errors}`.
- portal activation+account routers — `run_daily` forwards `outgoing_headers()` to the backends and writes `runlog.record_run("portal", …)`.
- portal `Dockerfile` — installs `git` (needed for the `git+https` truage-core dep).
- all three `requirements.txt` pinned `truage-core@v0.2.1`.

**DEPLOY (user):**
1. Publish: `cd truage-core; git add -A; git commit -m "v0.2.1"; git push; git tag v0.2.1; git push origin v0.2.1`
2. Railway env (nacs-portal project):
   - `RUNLOG_DATABASE_URL` = **portal's Postgres conn string** → set on **nacstar, nacstam, AND portal**.
   - `TRUAGE_CORE_PAT` (build var) → confirm it exists on the **portal** service too (backends already have it).
3. Push all three repos → auto-deploy.

**VERIFY:**
- `curl -X POST "https://nacsportal.up.railway.app/api/cron/run-daily?token=$CRON_SECRET"`
- In Railway logs: the portal cron line's `request_id` appears **unchanged** in nacstar + nacstam logs for that run. ✅ one id spans portal→backends.
- `GET /api/ops` (admin bearer) lists the run rows (`portal` + backends) and any errors. `/history`+`/errors` on the backends now read the shared log.
