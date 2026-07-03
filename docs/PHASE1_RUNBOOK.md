# Phase 1 Runbook — Extract `truage-core` (config + testrecords + HubSpot client/pull)

> Execution checklist for Phase 1 of `PORTAL_VNEXT_MIGRATION.md`. Companion:
> `truage-core-BLUEPRINT.md` (what to build), `truage-core-SETUP.md` (private repo + PAT).
> Guardrail: **every code step is gated by the characterization harness** — a report's output
> must be identical before/after. The two reports stay distinct; only plumbing moves.

## Do-I-need-more-prep? (assessment)
Almost no. The blueprint + setup doc + harness cover it. Two real prerequisites remain, both
because I authored the harness but **could not execute it here** (no HubSpot token / installed
deps in this environment):

1. **Prove the harness runs in your env and capture baselines** (Step 0 below). This validates my
   harness code against the live deps and locks the "before" snapshots. This is the one hard gate.
2. **Create the `truage-core` repo skeleton** (Step 1) — pyproject + `src/truage_core/` + pytest.

Everything else (module APIs, call-site map, adoption order, token decision) is already specified.
Phase 0 hygiene (token rotation, cruft, cron secret) is independent and can run in parallel or first.

## Step 0 — Capture characterization baselines (BEFORE any code change)
- **Activation:** `python tests/characterization/chartest_activation.py snapshot --pull hubspot_pull.json --asof <YYYY-MM-DD> --out tests/characterization/baseline` (from `truage-activity-report`).
- **Audit:** record a cassette with a live token, then snapshot to `baseline/` (from `truage-pulse`).
- Commit nothing; these dirs are throwaway. If either harness errors, fix the harness first — a
  green baseline is the prerequisite for trusting every later `compare`.
- Keep the exact `--asof` and pull/cassette you used; reuse them verbatim for the candidate.

## Step 1 — Scaffold `truage-core` (v0.0.0, empty but installable)
- Private repo per `truage-core-SETUP.md`; `pyproject.toml`, `src/truage_core/__init__.py`, `tests/`.
- Add pytest + a trivial test; tag `v0.0.0`. Confirm `pip install git+…@v0.0.0` works locally with the PAT.

## Step 2 — `config` (pure constants; zero behavior risk)
- Move into `truage_core/config.py`: `PIPELINE_ID`, `STORE_OBJECT_TYPE`, `DEAL_PROPERTIES`,
  `STORE_PROPERTIES`, `STAGE_ROLES`, `EARLY_FUNNEL_STAGES`, `GOAL`/`GOAL_DATE`, and the owner-ID maps.
- Tag `v0.1.0-config`. In each service, replace the local constants with imports from `truage_core.config`.
- **Gate:** re-snapshot candidate + `compare` for BOTH reports → must be identical.

## Step 3 — `testrecords`
- Move `is_test_deal(name)` (name rules) and `is_test_store(store)` (field rule) into
  `truage_core/testrecords.py`. Point `Deal.is_test_record` and the store check at them.
- Tag `v0.1.0-test`. **Gate:** compare both reports → identical. (This is the highest-value
  correctness consolidation — the exclusion logic that drove the reconciliation bug.)

## Step 4 — `hubspot.client` + `hubspot.pull`
- Implement the unified `HubSpotClient` (fail-loud retry) + `get_client()` (token order:
  arg → `HUBSPOT_TOKEN` → `HUBSPOT_PRIVATE_APP_TOKEN`) and `pull.py` (deals/stores/stage labels).
- Swap activation's `fetch_from_hubspot` internals and pulse's `hubspot_client` to `truage_core`.
- **Canonical token:** set a single Railway **shared** var `HUBSPOT_TOKEN` in `nacs-portal` and
  reference from both services; keep the `HUBSPOT_PRIVATE_APP_TOKEN` fallback until both are cut over.
- Tag `v0.1.0`. **Gate:** re-record the audit cassette against the new client, re-snapshot both,
  `compare` → identical. (Re-record because the client boundary changed; the *output* must not.)

## Step 5 — Land & verify
- Pin `truage-core @ …@v0.1.0` in both services' `requirements.txt`; deploy to Railway.
- Watch one real daily cron run end-to-end; confirm both reports render and emails send.
- Delete the now-dead duplicated code (old `fetch_from_hubspot` internals, `pulse/hubspot_client.py`,
  local constants/test rules). Update each repo's `CLAUDE.md` to point at `truage-core`.

## Definition of done (Phase 1)
- Both services import `truage-core` for constants, test rules, and HubSpot access; duplicates deleted.
- `truage-core` v0.1.0 tagged with unit tests (retry 429/5xx/4xx/exhaustion, `is_test_*`, stage validation).
- Characterization `compare` is green for BOTH reports against the Step 0 baselines.
- One HubSpot token in a Railway shared var; docs updated.

## Rollback
- Per step: re-pin the previous `truage-core` tag and revert the service's import swap (small, isolated).
- Nothing is deleted until Step 5, after the gate passes — so any red `compare` is a revert, not a fix-forward.
