# Portal vNext — Migration Plan

> A sequenced, low-risk plan to streamline the TruAge/NACS reporting stack: shared library,
> uniform scaffolding, one cache, unified logging/tracing, and the portal as the single hub.
> **Non-goal:** we are NOT collapsing the two reports. The **Activation Report** and the
> **AM Assignment Audit** stay as two distinct reports — they measure different things. What we
> consolidate is everything *under* them (HTTP scaffolding, HubSpot access, caching, email,
> logging). Companion docs: `ARCHITECTURE.md`, `REPORTS.md`.

## Target end-state (topology)

```
BEFORE                                   AFTER (vNext)
──────                                   ────────────
pez-portal      (FastAPI hub)            pez-portal      (FastAPI hub — owns auth, cache, email, cron, ops)
nacstar         (Flask, subprocess)  ─┐
nacstam         (Flask, package)     ─┴▶ truage-reports (FastAPI — /activation + /audit + /dictionary routers)
nacs-990        (FastAPI)                nacs-990        (FastAPI, unchanged)
cstore ×4       (dormant)                cstore ×4       (dormant)
                                         truage-core     (shared pip package: HubSpot client, KPI rules, email, logging)
```

Two always-on TruAge services (portal + `truage-reports`) instead of three, both on one stack,
sharing one library and one cache. **The two reports remain separate routes/cards throughout.**

## Guiding principles

- **Every phase ships independently and is reversible.** Old services stay live until the new
  path is verified; the portal's proxy layer is the switch.
- **Characterization tests are the safety net.** Before refactoring any report, snapshot its
  numbers + rendered HTML from a *fixed* HubSpot pull (`hubspot_pull.json`) and diff after each
  change. A report's output must be byte-for-byte (or metric-for-metric) identical across a refactor.
- **No behavior changes ride along with structural changes.** KPI logic changes, if any, are
  separate commits from moves/renames.

---

## Phase 0 — Guardrails & hygiene (do first; fast, near-zero risk)

**Goal:** stop the bleeding on secrets and clear cruft so later refactors are legible.

Steps
- **Rotate the shared HubSpot private-app token** (it sits in plaintext in `truage-activity-report/run_report.bat:32`, which is **git-ignored** — NOT in GitHub history, but a live secret on the TINY disk). Issue a new token, set it as a **Railway shared variable** in the `nacs-portal` project, and reference it from both TruAge services instead of two copies.
- **Rotate `CRON_SECRET`**; switch `daily-reports-cron` / `daily-reports-watchdog` to send it via the `Authorization: Bearer` header (already supported in `app/main.py`) instead of the `?token=` URL param (which lands in access logs).
- **Delete cruft** (after confirming unused): `truage-activity-report/*.py-old` (×3), `apply_*fix.sh` in both TruAge repos, `run_report.bat` (post-rotation). Confirm whether `generate_report.py` (local PDF), `generate_period_report.py`, `compare_asof.py` are still used; if not, remove.
- **Remove the failed `mcp-demo`** service from `nacs-portal` if it's a dead demo.

Done when: no secrets in git; both services read the token from one Railway variable; repo trees contain only live files.
Rollback: trivial (revert deletions; secrets are additive).

---

## Phase 1 — Extract `truage-core` (the shared library)

**Goal:** one source of truth for HubSpot access and KPI primitives, so the two reports can't drift.

Create a small pip-installable package (`paulziv/truage-core`), referenced from each service's
`requirements.txt` via a pinned git URL. Move in, with tests:
- **HubSpot client** — one implementation of the retry/backoff + **fail-loud** policy (the
  2026-07-01 fix), replacing `truage-activity-report/fetch_from_hubspot.py`'s `_request_with_retry`
  and `truage-pulse/pulse/hubspot_client.py`.
- **Stage + owner config** — `STAGE_ROLES`, the stage-role validation, and the owner-ID maps
  (`AM_OWNER_IDS`, `INACTIVE_OWNER_IDS`, `OTHER_OWNER_IDS`).
- **Test-record rules** — both mechanisms in one place: deal name-based (`TEST_EXACT_NAMES` /
  `TEST_SUBSTRING_PATTERNS`) and store `is_test_data`-based.
- **Email** — one Resend wrapper (Phase 6 moves pulse onto it).
- **Logging + run/error records** — structlog config + a `record_run` / `record_error` helper
  writing to the shared Postgres (Phase 2 schema).

Crucial boundary: `truage-core` holds **primitives**, not report logic. Each report keeps its own
compute module (`activation` vs `audit`) that *uses* these primitives. The reports stay distinct.

Done when: both services import `truage-core` for the above; the duplicated copies are deleted;
`truage-core` has unit tests for retry, test-exclusion, and stage validation.
Rollback: services pin the previous git SHA of `truage-core`.

---

## Phase 2 — Unify logging & tracing

**Goal:** one filterable log format and end-to-end traceability of a report run.

Steps
- **structlog JSON everywhere** (via `truage-core`). Converts the two Flask apps off stdlib logging
  to match portal + 990.
- **Correlation ID.** The portal mints an `X-Request-ID` per request/cron run and forwards it on
  every proxied call (`app/routers/truage_activation`, `truage_account`, and the `run_daily`
  fan-out). Backends log it. One daily run is now traceable portal → backend in the logs.
- **Shared `run_history` / `error_log` tables** in the shared Postgres, written by *all* TruAge
  services via `truage-core`. Fold the existing per-service `/history` (`run_history.py`) and
  `/errors` (`storage.get_recent_errors`) into this shared schema.
- **One ops page.** Extend the portal's existing `app/static/ops.html` + `/api/daily-status` into
  a single admin view that reads the shared tables — replaces scrolling three services' logs.

Done when: every service emits JSON logs with a correlation ID; the portal ops page shows the last
N runs/errors across all TruAge services from one query.

---

## Phase 3 — De-subprocess the Activation Report

**Goal:** kill the fragile `subprocess` + `/tmp` handoff in `truage-activity-report` — the hardest
thing in the system to trace.

Steps
- Snapshot characterization baseline: run today's `app.py` pipeline on a fixed pull, save the
  rendered HTML + the computed metrics dict.
- Refactor `generate_report_html.py` to expose `load_data()` / `compute_metrics()` / `render()` as
  importable functions (it already essentially has these). Have `app.py` call them **in-process**
  using the `truage-core` HubSpot client — no `subprocess`, no `/tmp/*.json`, no 120s timeouts.
- Delete the now-dead `alerting.py` crash-string plumbing in favor of structlog + shared `error_log`.
- Diff against the baseline — metrics and HTML must match exactly.

Done when: `truage-activity-report` computes in-process with real tracebacks; characterization diff is clean.
Rollback: keep the old `app.py` behind a flag until the diff is verified across a few daily runs.

---

## Phase 4 — Uniform stack + shared report-app skeleton

**Goal:** both reports on FastAPI, sharing one HTTP skeleton, so a report is "fill in compute," not "re-plumb."

Steps
- Build a `report_app` skeleton (in `truage-core` or a thin shared module): the loading-shell
  pattern (from `pulse/app.py`), `/health`, `/errors`, standalone-HTML export (`export.to_standalone_html`),
  and cache-aware serving. Parameterized by a `compute()` callable + template.
- Port the **AM Audit** (already FastAPI-shaped in spirit) and the **Activation Report** (now
  in-process from Phase 3) onto the skeleton as two routers: `/audit`, `/activation` (+ `/dictionary`).
- **Decision point — one service or two?** Recommended: **merge into a single `truage-reports`
  service** exposing both routers. Rationale: one deploy, one log stream, one HubSpot connection,
  one cache client. The two **reports stay distinct** (separate routes, separate portal cards,
  separate compute modules) — only the *container* consolidates. Keep `nacstar`/`nacstam` hostnames
  as aliases during transition so nothing external breaks.

Done when: both reports run on the shared skeleton; (if merged) one `truage-reports` service serves
`/activation` and `/audit`, with the old hostnames still resolving.

---

## Phase 5 — Portal owns caching (backends go stateless)

**Goal:** collapse three cache layers (pulse in-proc 5-min, portal Postgres `report_cache`, activation `/tmp`) into one.

Steps
- Make the report backends **stateless compute endpoints** — they render on request, no local cache.
- The portal's `daily_cache.py` (Postgres `report_cache`, already durable across redeploys) becomes
  the **only** cache. It owns TTL, the refresh trigger, and magic-link (`report_tokens`) delivery.
- Remove pulse's in-process `cached(ttl=300)` and any residual `/tmp` writes.

Done when: exactly one cache layer (portal Postgres); redeploying a backend never serves stale or
empty data because the portal holds the last good render.

---

## Phase 6 — Unify email on Resend

**Goal:** one email provider, one sender domain, one key.

Steps
- Point `truage-pulse` at the `truage-core` Resend wrapper (it currently uses Postmark via
  `pulse/email.py`). Portal, activation-report, and 990 are already Resend.
- Retire the Postmark key and `pulse/email.py`.

Done when: all services send via Resend from `portal@dashboard.mytruage.org`; Postmark removed.

---

## Phase 7 — Portal vNext cutover & doc refresh

**Goal:** flip to the consolidated topology and update the source of truth.

Steps
- Repoint the portal's proxy/registry: `app/routers/truage_activation` and `truage_account` target
  the `truage-reports` service (or keep proxying `nacstar`/`nacstam` aliases that now point there).
  Update `APP_REGISTRY` URLs in `app/config.py` if any change.
- Verify a full daily cron run end-to-end via correlation ID (portal → truage-reports → email).
- **Decommission** the old `nacstar` / `nacstam` services once the alias window passes.
- Update `docs/ARCHITECTURE.md`, `docs/REPORTS.md`, and each `CLAUDE.md` to the new topology; bump
  the portal version.

Done when: two always-on TruAge services (portal + truage-reports), one library, one cache, one log
format, one email provider — and the docs match.

---

## Sequence rationale & risk

| Phase | Effort | Impact | Risk | Why here |
|---|---|---|---|---|
| 0 Hygiene | S | Med (security) | ⬇ Low | Unblocks safe refactoring; no logic touched |
| 1 truage-core | M | **High** | Low | Everything else builds on it; kills drift |
| 2 Logging/tracing | M | **High** | Low | Makes the *rest* of the migration observable |
| 3 De-subprocess | M | High | Med | Biggest fragility removal; guarded by char-tests |
| 4 Uniform skeleton | M–L | High | Med | The consolidation payoff; reversible via aliases |
| 5 One cache | S–M | Med | Med | Depends on 4; simplifies invalidation |
| 6 Resend | S | Low–Med | Low | Independent; do anytime after Phase 1 |
| 7 Cutover | S | — | Med | Only after 3–5 verified in parallel |

**Reversibility spine:** old services stay up and old hostnames keep resolving until Phase 7; the
portal proxy is the cutover switch; every report refactor is gated by a characterization diff.

## Explicitly out of scope
- Merging the two **reports** (they stay separate — this plan only shares their plumbing).
- cstore (dormant); when revived, adopt `truage-core` + the logging/skeleton standards, and
  consider collapsing `cstore-scraper` + `cstore-backend`.
- Database consolidation (the 3 Postgres are cleanly separated by concern; leave them).
- BenchPoint stays its own service (different domain, different data model).
