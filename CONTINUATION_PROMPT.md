# Innovation Portal — Continuation Prompt

Paste this at the start of a new session to resume where we left off.

---

We are building **pez-portal** — an internal FastAPI app portal for NACS / TruAge tools,
deployed at `https://nacsportal.up.railway.app` on Railway.
GitHub repo: `https://github.com/paulziv/pez-portal`
Local working tree: `C:\Users\paulz\dev\pez-portal`

## What was completed this session

- **Brand refresh**: cream `#F5F0E8` bg, white cards, navy `#00203F` header,
  mint `#36ECDE` accent, Inter font, 6px left card borders, renamed to "Innovation Portal"
- **Auth fix (all apps)**: HTML shell routes now return 200 freely — auth is
  client-side via Auth0 SPA SDK. All `/api/*` sub-routes remain protected.
  Root cause was `Depends(require_auth)` on the GET `/` route, which browsers
  can't satisfy (no Bearer token on navigation).
- **Token fix**: All pages use `getIdTokenClaims().__raw` (ID token JWT) not
  `getTokenSilently()` (returns opaque token that python-jose rejects).
- **File corruption repair**: Several Python files were truncated mid-edit
  (main.py, config.py, stock/routes.py, admin/routes.py, test_config.py).
  All repaired. Lesson: use `python3 -c "import ast; ast.parse(open(f).read())"` 
  to validate files before committing.
- **Tests**: Updated test_routes.py to reflect client-side auth pattern.
  19/19 passing.
- **NACS Innovation logo GIF**: Generated cream-bg animated lightbulb with
  rotating orbital rings in mint/navy. Saved as `app/static/nacs-innovation-logo.gif`.
- **CLAUDE.md**: Written for pez-portal with full architecture, auth pattern,
  brand palette, and common commands.
- **Git push**: All changes pushed to `paulziv/pez-portal` main (Railway auto-deploys).

## Open items to pick up next

### 1. BenchPoint — duplicate login
BenchPoint (`https://990benchmark.up.railway.app/ui/`) has its own auth setup.
Goal: share the same Auth0 tenant so portal session carries over (no second login).
Approach: configure BenchPoint to use Auth0 tenant `pezdev.us.auth0.com` with the
same client ID, OR use Auth0 SSO (both apps in same tenant get SSO automatically
if using the same Auth0 application). Check BenchPoint's auth code in
`C:\Users\paulz\dev\nacs-990-benchmark`.

### 2. BenchPoint — brand colors
BenchPoint UI has some non-brand greens/blues. Update CSS in the nacs-990-benchmark
repo to use the brand palette (see CLAUDE.md in pez-portal for colors).

### 3. New logo — swap into portal
The new animated logo is at `app/static/nacs-innovation-logo.gif`.
To use it on the login card, update `portal.html` line:
  `<img src="/static/logo.gif"` → `<img src="/static/nacs-innovation-logo.gif"`
User may want to A/B compare both first.

### 4. TruAge apps — build real content
Both TruAge routers are stubs ("Coming soon"). When ready, real data logic goes in:
- `app/routers/truage_activation/routes.py`
- `app/routers/truage_account/routes.py`

### 5. Auth0 — add Frank's account
Create `fgleeson@convenience.org` in Auth0 User Management → Users → Create User
(they're in USER_ROLES for benchmark but may not have an Auth0 account yet).

### 6. Auth0 Universal Login logo
Paste `https://nacsportal.up.railway.app/static/logo.gif` into
Auth0 → Branding → Universal Login → Logo URL.

## Key file locations

```
C:\Users\paulz\dev\pez-portal\         ← portal repo
C:\Users\paulz\dev\nacs-990-benchmark\ ← BenchPoint repo (nacs-990-benchmark)
```

## Auth pattern (don't break this)

Every HTML-serving route must have NO auth dependency:
```python
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui() -> str:          # ← no Depends() here
    return _HTML
```

Every page's JS must init Auth0 and redirect to `/` if not authenticated:
```javascript
const client = await auth0.createAuth0Client({...cacheLocation:"localstorage"});
if (!(await client.isAuthenticated())) { window.location.href = "/"; return; }
const claims = await client.getIdTokenClaims();
_token = claims.__raw;   // ← always use __raw, never getTokenSilently()
```

Every API fetch must include the Bearer token:
```javascript
fetch(url, { headers: { Authorization: `Bearer ${_token}` } })
```
