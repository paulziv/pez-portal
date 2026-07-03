# Phase 0 Runbook — Hygiene & Guardrails (explicit CLI)

> Executor split: **[CLAUDE]** = done in-repo already (working-tree edits). **[YOU]** = needs your
> credentials / a provider console / git push — explicit PowerShell (PS) or WSL commands given.
> Correction vs. earlier notes: `run_report.bat` is **git-ignored and was never committed to
> GitHub** — the token was a live secret in plaintext on the TINY disk, not a git-history leak.

## [CLAUDE] Already executed in the working tree
- `truage-activity-report/run_report.bat` line 32 token → replaced with
  `pat-na1-REPLACE-WITH-YOUR-TOKEN` placeholder. The script's resolution block now falls through
  to the `HUBSPOT_TOKEN` env var. ⚠️ **Side effect:** the next scheduled local run needs
  `HUBSPOT_TOKEN` set (see below) or it exits 1 (fails loud, no bad data).
- Docs corrected to say "git-ignored plaintext, not in history."

## [YOU] 1. Rotate the HubSpot token (the real security fix)
The token was live in plaintext, so rotate it regardless of git.
1. HubSpot → Settings → Integrations → **Private Apps** → the app whose token starts `pat-na1-7ff4aae7…`
   → **Rotate/Regenerate** (or deactivate + create new). Copy the new `pat-na1-…`.
2. Set it as a Windows **user** env var so the local scheduled `run_report.bat` keeps working:
   ```powershell
   [Environment]::SetEnvironmentVariable('HUBSPOT_TOKEN','pat-na1-NEWVALUE','User')
   # reopen the shell, then verify:
   [Environment]::GetEnvironmentVariable('HUBSPOT_TOKEN','User')
   ```
3. Confirm the file is git-ignored (expect it to print the path, exit 0):
   ```powershell
   git -C C:\Users\paulz\dev\truage-activity-report check-ignore run_report.bat
   ```
   No git-history purge is needed. (Optional: keep the sanitized file, or delete it once the two
   TruAge services read `HUBSPOT_TOKEN` from the environment.)

## [YOU] 2. Cron secret hygiene (Railway dashboard)
`CRON_SECRET` is passed as a `?token=` URL param (lands in access logs) and hardcoded in the cron
`startCommand`. In the `nacs-portal` project:
- Rotate `CRON_SECRET` (Variables → edit), and update `daily-reports-cron` + `daily-reports-watchdog`
  start commands to send it as a header instead of a query param, e.g.:
  ```
  curl -fsS -X POST -H "Authorization: Bearer ${CRON_SECRET}" https://nacsportal.up.railway.app/api/cron/run-daily
  ```
  (The endpoint already accepts the `Authorization: Bearer` form — see `app/main.py`.)
- Railway may not interpolate `${CRON_SECRET}` in a raw start command; if it doesn't, paste the
  rotated secret directly into the cron service's command (that service's logs aren't public).

## [YOU] 3. Cruft removal (optional; safe deletes)
Local, mostly untracked files. From PowerShell:
```powershell
cd C:\Users\paulz\dev\truage-activity-report
Remove-Item *.py-old, apply_*fix.sh -WhatIf     # preview
Remove-Item *.py-old, apply_*fix.sh             # then for real
cd C:\Users\paulz\dev\truage-pulse
Remove-Item apply_*fix.sh -WhatIf
```
Then `git status` in each; if any were tracked, `git rm` them and commit. Leave
`generate_report.py` / `generate_period_report.py` / `compare_asof.py` until you've confirmed
they're unused (they power the local PDF path via `run_report.bat`).
(Claude can also delete these in-repo on request now that cowork deletes are enabled — say the word.)

## Definition of done (Phase 0)
- New HubSpot token rotated; `HUBSPOT_TOKEN` user env var set; old token invalid.
- `run_report.bat` carries no real secret (done).
- `CRON_SECRET` rotated and sent via header.
- Cruft removed (optional).
Phase 0 is independent of Phase 1 — you can rotate the token in parallel with publishing truage-core.
