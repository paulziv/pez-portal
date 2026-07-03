# SESSION RESUME — TruAge/NACS Portal vNext

> ✅ **PHASE 1 COMPLETE & LIVE (2026-07-03).** truage-core adopted (config, testrecords, hubspot
> client/pull) across both TruAge services, verified byte-identical, deployed to Railway
> (git-in-Dockerfile fix applied), reports serving. Post-deploy cleanup done: docs/CLAUDE.md
> updated, characterization scratch removed + git-ignored. Remaining is NON-URGENT (below).
> Next uncommitted bits: the doc/CLAUDE.md/.gitignore edits from cleanup (commit when ready).


_Last updated: 2026-07-02, end of session (~90% limit)._

## Where we are
Documentation pass = done. **Phase 1 of the Portal vNext migration (truage-core consolidation) is
code-complete, verified, and just pushed to Railway.**

- **`truage-core` v0.1.0** — private repo `paulziv/truage-core` (main + `v0.1.0` tag), unit tests pass.
  Modules: `config`, `testrecords`, `hubspot.client` (fail-loud retry), `hubspot.pull`.
- **Adopted in both services, each verified byte-identical via the characterization harness:**
  - config (owner maps in pulse; pipeline/stage/goal constants in activation)
  - testrecords (activation)
  - hubspot client/pull (pulse = shim over truage-core; activation `fetch_from_hubspot.py` rewired)
  - Live old-vs-new pull diff on activation: **FULL IDENTICAL**.
- **Pushed to `main`:** truage-activity-report `9dac4b4`, truage-pulse `08902bf` → Railway auto-deploy.
- `requirements.txt` in both pins `truage-core @ git+https://${TRUAGE_CORE_PAT}@github.com/paulziv/truage-core@v0.1.0`.

## BUILD FIX APPLIED (2026-07-03) — re-push pending
First deploy of both services FAILED — not the PAT (that authenticated fine), but the
`python:3.12-slim` image has no `git`, which pip needs to install the `git+https://` truage-core
dep (`ERROR: Cannot find command 'git'`). **Fix applied:** both Dockerfiles now
`apt-get install -y --no-install-recommends git` before `pip install`. **Next action: commit +
push both repos to redeploy**, then verify (below). truage-core install itself + PAT + Railway
vars are confirmed working.

## FIRST thing on resume — confirm the deploy
The build needs **`TRUAGE_CORE_PAT`** (read-only PAT) present as a **service** var in Railway for
BOTH `truage-activity-report` and `truage-pulse`, or pip can't install truage-core and the build fails.
1. Check Railway build logs for both services — expect a successful `pip install truage-core … @v0.1.0`.
2. Confirm reports render: `nacstar.up.railway.app/status` (ok) and `nacstam.up.railway.app/audit`.
3. If a build FAILED (missing `TRUAGE_CORE_PAT` / auth): add the read-only PAT + `HUBSPOT_TOKEN` as
   nacs-portal shared vars, reference them into both services, redeploy. (Last good deploy keeps
   running until a build succeeds, so prod isn't down.)

## Then — post-deploy cleanup to CLOSE Phase 1 (Claude can do these; safe file edits)
- Update `truage-activity-report/CLAUDE.md` + `truage-pulse/CLAUDE.md` to note truage-core adoption.
- Update `pez-portal/docs/ARCHITECTURE.md` + `REPORTS.md` where they describe the (now shared) HubSpot
  client / constants / test rules.
- Remove local scratch artifacts: each repo's `tests/characterization/{baseline,candidate,cassette.json}`
  (throwaway; keep the `chartest_*.py` harnesses + READMEs).

## Still open (independent)
- **Phase 0 — rotate the HubSpot token** in HubSpot's console (it was live plaintext in the
  now-sanitized `run_report.bat`), and use that rotated value for the `HUBSPOT_TOKEN` Railway var.
- **Phase 0 — cron secret**: rotate `CRON_SECRET`, switch cron to the `Authorization: Bearer` header.
- Optional cruft deletes (see `PHASE0_RUNBOOK.md`).

## What's next after Phase 1 (from PORTAL_VNEXT_MIGRATION.md)
Phase 2 logging/tracing (structlog + correlation IDs + shared run_history/error_log + one ops page),
Phase 5 single portal cache, Phase 6 unify email on Resend, Phase 7 optional merge of the two
report backends into one `truage-reports` service (reports stay distinct). Each behind the same
characterization-gate discipline.

## Doc index (all in pez-portal/docs/)
ARCHITECTURE.md · REPORTS.md · PORTAL_VNEXT_MIGRATION.md · truage-core-BLUEPRINT.md ·
truage-core-SETUP.md · PHASE0_RUNBOOK.md · PHASE1_RUNBOOK.md · PHASE1_STEP4_AND_CUTOVER.md · this file.
Harnesses: `truage-activity-report/tests/characterization/`, `truage-pulse/tests/characterization/`.
