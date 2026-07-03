# Phase 1 — Step 4 (HubSpot client/pull) + Cutover — turnkey session plan

> Resume point for the focused session. Prereqs done: `config` + `testrecords` adopted, verified
> green against baselines, committed locally (activation `58a6854`; pulse commit similar). NOT pushed.
> `truage-core` v0.1.0 is on GitHub (`main` + tag) and editable-installed in both service venvs.
> This step needs a live HubSpot token + network — that's why it's its own pass.

## Why Step 4 needs live verification
The characterization harnesses compute from a **saved** pull (activation) / **recorded cassette**
(pulse), so they don't exercise the live fetch path. Swapping the client is therefore verified
against live data, not the existing snapshots.

---

## Step 4A — Activation: fetch_from_hubspot.py → truage-core client/pull
**Edit (Claude, in the session):** replace the in-file HTTP layer + fetchers
(`_request_with_retry`, `hs_post`, `hs_get`, `fetch_stage_labels`, `fetch_all_deals`,
`fetch_all_stores`, and the `DEAL_SEARCH_URL`/`STORE_SEARCH_URL`/`PAGE_SIZE`/`MAX_RETRIES`/
`BASE_BACKOFF_SECONDS` constants) with calls into `truage_core.hubspot`:
```python
from truage_core.hubspot import get_client, pull
def main(...):
    client = get_client()                      # token: HUBSPOT_TOKEN → HUBSPOT_PRIVATE_APP_TOKEN
    stage_labels = pull.fetch_stage_labels(client)
    deals  = pull.fetch_all_deals(client)
    stores = pull.fetch_all_stores(client)      # unchanged write_pull(...) below
```
`write_pull()` / arg parsing / `main()` stay. Output shape is identical by construction
(truage_core.pull was copied from this file).

**Live verify (you):** prove the new fetch produces the same pull JSON as the old one.
```powershell
cd C:\Users\paulz\dev\truage-activity-report ; .\.venv\Scripts\Activate.ps1
$env:HUBSPOT_TOKEN=[Environment]::GetEnvironmentVariable('HUBSPOT_TOKEN','User')
git stash                                   # old fetch
python fetch_from_hubspot.py --output pull_old.json
git stash pop                               # new fetch (Claude's edit)
python fetch_from_hubspot.py --output pull_new.json
# compare ignoring the pulled_at timestamp:
python - <<'PY'
import json
a=json.load(open("pull_old.json")); b=json.load(open("pull_new.json"))
a.pop("pulled_at",None); b.pop("pulled_at",None)
print("IDENTICAL" if a==b else "DRIFT — inspect")
PY
```
`IDENTICAL` → the fetch swap is safe. Then re-run the report characterization compare (still green,
since it reads a saved pull) as a final belt-and-suspenders.

---

## Step 4B — Pulse: use truage-core client + move the harness patch point
**Edit (Claude):** point `pulse/hubspot_client.py`'s `get_client`/`HubSpotClient` usage at
`truage_core.hubspot.client` (simplest: make `pulse/hubspot_client.py` re-export from truage-core,
so `pulse/audit/data.py` imports are untouched):
```python
# pulse/hubspot_client.py becomes a thin shim:
from truage_core.hubspot.client import HubSpotClient, HubSpotError, get_client  # noqa: F401
```
**Update the harness patch point** in `tests/characterization/chartest_audit.py`: change the two
`HC.HubSpotClient._request` monkeypatch targets from `pulse.hubspot_client` to
`truage_core.hubspot.client` (import `truage_core.hubspot.client as HC`).

**Live verify (you):** re-record against the new client, then compare to the EXISTING baseline
(the audit output must be unchanged):
```powershell
cd C:\Users\paulz\dev\truage-pulse ; .\.venv\Scripts\Activate.ps1
$env:HUBSPOT_PRIVATE_APP_TOKEN=[Environment]::GetEnvironmentVariable('HUBSPOT_TOKEN','User')
python tests\characterization\chartest_audit.py record   --out tests\characterization\cassette_v2.json
python tests\characterization\chartest_audit.py snapshot --cassette tests\characterization\cassette_v2.json --out tests\characterization\candidate_v2
python tests\characterization\chartest_audit.py compare tests\characterization\baseline tests\characterization\candidate_v2
```
`✓ identical` → pulse client swap safe. (Delete the old `cassette.json`/`baseline` afterward if you like.)

---

## Step 5 — Cutover (publish install path + deploy)
1. **Read-only PAT (now that the repo exists):** fine-grained token → resource owner `paulziv`,
   **Only select repositories → truage-core**, **Contents: Read-only**. Test:
   ```powershell
   $env:TRUAGE_CORE_PAT="github_pat_..."
   git ls-remote "https://$($env:TRUAGE_CORE_PAT)@github.com/paulziv/truage-core"   # must list refs
   ```
2. **Add the dependency** to BOTH `requirements.txt` (Claude can edit), pinned:
   ```
   truage-core @ git+https://${TRUAGE_CORE_PAT}@github.com/paulziv/truage-core@v0.1.0
   ```
3. **Railway:** in `nacs-portal` project shared variables add `TRUAGE_CORE_PAT` (the read-only PAT)
   and `HUBSPOT_TOKEN` (the rotated token); reference both from `truage-activity-report` and
   `truage-pulse` services. (Portal already has its own vars.)
4. **Push = deploy** (both repos, together):
   ```powershell
   cd C:\Users\paulz\dev\truage-activity-report ; git add -A ; git commit -m "Phase 1: truage-core client/pull + requirements" ; git push
   cd C:\Users\paulz\dev\truage-pulse           ; git add -A ; git commit -m "Phase 1: truage-core client shim + requirements" ; git push
   ```
5. **Watch one run:** hit `/api/cron/run-daily` (or wait for 13:00 UTC), confirm both reports render
   + emails send; check `/status` (nacstar) and `/audit` (nacstam).
6. **Cleanup (Claude, on request):** delete now-dead duplicated code and stale files, update each
   `CLAUDE.md` to point at truage-core. Candidates: activation `generate_report.py-old*` (already
   gone), any leftover local client code fully replaced by truage-core.

## Rollback
- Pre-push: everything is local; `git restore`/`git reset` per repo.
- Post-push: re-pin the previous commit and redeploy; truage-core tag is immutable so the library
  can't shift under you. Any red `compare`/`DRIFT` = stop, don't push.

## Definition of done (Phase 1 complete)
Both services import truage-core for constants, test rules, AND HubSpot access; duplicated code
deleted; one `HUBSPOT_TOKEN` shared var; both reports verified byte-identical across the whole
migration; docs/CLAUDE.md updated.
