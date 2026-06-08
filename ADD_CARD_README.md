# Adding a Card to the Innovation Portal

Reference this file whenever a new app card needs to be added to
`https://dashboard.mytruage.org`. It covers the full workflow from
config change to live deploy.

---

## The Only File You Need to Edit

```
app/config.py
```

Two sections inside it:

| Section | Purpose |
|---|---|
| `APP_REGISTRY` | Defines every card (title, icon, color, URL, description) |
| `USER_ROLES` | Controls which users can see which cards |

---

## Step 1 — Add the Card to APP_REGISTRY

Append a new dict to the `APP_REGISTRY` list. All fields:

```python
{"slug": "my_app",                          # unique snake_case identifier
 "title": "My App",                         # card heading
 "description": "One or two sentences.",    # card body text
 "icon": "🛎️",                             # emoji shown on card
 "color": "#c2410c",                        # left border accent (hex)
 "url": "https://myapp.up.railway.app",     # where Open → goes
 "external": True},                         # True = opens in new tab with ↗ external badge
                                            # False = opens inline (portal-hosted route)
```

Optional field — only add if the card has a daily report link:

```python
 "has_daily": True,                         # shows "Open Daily Report" footer on card
```

### Accent color conventions (existing cards)

| Card | Color |
|---|---|
| Admin | `#64748b` slate |
| BenchPoint | `#005eb8` blue |
| TruAge Activation | `#087f5b` teal-green |
| TruAge Account Manager | `#b36b00` amber |
| TruAge Data Dictionary | `#0c6e5c` dark teal |
| MarketMaker | `#6741d9` purple |
| App Downloads | `#2563EB` royal blue |
| C-Store Intel | `#16a34a` green |
| Personal Email Agent | `#c2410c` burnt orange |

Pick a color not already in use. Avoid the brand palette colors
(navy `#00203F`, mint `#36ECDE`) — those are reserved for the shell UI.

---

## Step 2 — Add the Slug to USER_ROLES

`USER_ROLES` maps email addresses to the list of slugs they can see.
Add the new slug only to the users who should have access.

```python
USER_ROLES = {
    "ziv.paul@gmail.com": [
        "admin",
        "my_app",       # ← add here for Paul only, or add to others too
        ...
    ],
}
```

**Personal or admin-only apps**: add to `ziv.paul@gmail.com` only.
**Team apps**: add to everyone who needs it.

The card will not appear for any user whose email is not in `USER_ROLES`
with the matching slug — even if they are authenticated.

---

## Step 3 — Push to GitHub

The portal auto-deploys from the `paulziv/pez-portal` GitHub `main` branch.
Only `app/config.py` needs to be committed for a card-only change.

```powershell
Set-Location C:\Users\paulz\dev\pez-portal
git add app/config.py
git commit -m "feat: add <AppName> card to portal"
git push origin main
```

### If the push is rejected (remote has new commits)

```powershell
git pull origin main --rebase
```

If there is a merge conflict in `app/config.py`:

1. Open the file — look for `<<<<<<< HEAD` / `=======` / `>>>>>>>` markers.
2. Keep **all** entries from both sides — the remote added cards too, don't drop them.
3. Remove the conflict markers entirely.
4. Then:

```powershell
git add app/config.py
git rebase --continue
git push origin main
```

---

## Step 4 — Verify

Railway auto-deploys in ~60 seconds after the push lands on GitHub.

Open `https://dashboard.mytruage.org` (signed in as `ziv.paul@gmail.com`)
and confirm the new card appears with the correct icon, color, description,
and link behavior.

---

## Portal-Hosted vs External Cards

| `"external": False` | `"external": True` |
|---|---|
| App lives inside the portal codebase | App is a separate Railway service |
| URL is a relative path e.g. `/apps/my-app/` | URL is a full `https://` address |
| Requires a router in `app/routers/` and registration in `app/main.py` | No backend work needed — just the config entry |
| Shows `Open →` | Shows `Open ↗ external` badge |

For a new **external** app (already deployed elsewhere on Railway or another host),
Step 1 and Step 2 above are all that is needed. No router or main.py changes required.

For a new **portal-hosted** app, also:
- Create `app/routers/<slug>/routes.py`
- Register the router in `app/main.py`
- Add a test to `tests/test_routes.py`

---

## Quick Reference — Current Slugs

```
admin
benchmark
truage_activation
truage_account
truage_dictionary
stock
app_downloads
cstore_intel
personal_email
```

New slugs must be unique. Use `snake_case`.

---

## Auth / Access Control Notes

- Auth is handled by Auth0 (`pezdev.us.auth0.com`). Users must sign in with
  their Google account (or any Auth0-supported method).
- A user who authenticates but whose email is not in `USER_ROLES` sees an
  "Access Denied" screen.
- A user in `USER_ROLES` only sees the cards whose slugs are in their list.
- There is no additional password needed for individual cards — Auth0 + role
  scoping is sufficient for portal-hosted and external cards alike.
- For sensitive personal apps (e.g. Personal Email Agent), add the slug only
  to `ziv.paul@gmail.com` and the card will never appear for anyone else.

---

## Production URLs

| Resource | URL |
|---|---|
| Portal | `https://dashboard.mytruage.org` |
| Railway fallback URL | `https://nacsportal.up.railway.app` |
| GitHub repo | `https://github.com/paulziv/pez-portal` |
| Admin panel | `https://dashboard.mytruage.org/apps/admin/` |
