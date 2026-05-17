# Pez Portal

Role-based internal app portal. Users log in via Auth0 and see only the apps
their email is authorised to access.

## Architecture
- **Stack**: Python 3.12, FastAPI, Auth0 SPA SDK v2, python-jose, httpx,
  pydantic-settings, structlog.
- **Auth**: Auth0 SPA (client-side JWT issuance) + python-jose RS256 validation
  on every backend route. No session cookies — Bearer tokens only.
- **RBAC**: `app/config.py` — `USER_ROLES` dict maps email → list of app slugs.
  `APP_REGISTRY` defines all portal cards. Add a user by adding their email to
  `USER_ROLES`.
- **Routing**: Each app lives under `/apps/<slug>/`. Internal apps are FastAPI
  routers mounted in `main.py`. External apps (e.g. BenchPoint) are links only.

## Apps
| Slug              | Location             | Status     |
|-------------------|----------------------|------------|
| benchmark         | 990benchmark.railway | External   |
| truage_activation | /apps/truage-activation/ | Stub    |
| truage_account    | /apps/truage-account/    | Stub    |
| stock             | /apps/stock/             | Live (public Deribit data) |

## Auth0 config
- Tenant: `pezdev.us.auth0.com`
- Client ID: `4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d` (SPA, public — OK to commit)
- Allowed Callback URLs: `https://<railway-url>, http://localhost:8080`
- Allowed Logout URLs:   `https://<railway-url>, http://localhost:8080`
- Allowed Web Origins:   `https://<railway-url>, http://localhost:8080`

## Users
| Email                        | Apps                                         |
|------------------------------|----------------------------------------------|
| ziv.paul@gmail.com           | all                                          |
| fgleeson@convenience.org     | benchmark only                               |

To add a user: edit `USER_ROLES` in `app/config.py` and redeploy.

Frank currently needs a username/password Auth0 account (he uses Microsoft 365,
not Google Workspace). Create via Auth0 dashboard → User Management → Users →
Create User. Once done, remove `connection: "google-oauth2"` from BenchPoint's
`index.html` so the login button works for all connection types.

## Deployment
- **Railway service**: `pez-portal` (separate from BenchPoint)
- **Repo**: `https://github.com/paulziv/pez-portal` (create this)
- **Branch**: `main`, auto-deploy on push
- **PORT**: Railway injects `$PORT`; Dockerfile uses `${PORT:-8080}`

## Railway env vars to set
```
AUTH0_DOMAIN=pezdev.us.auth0.com
AUTH0_CLIENT_ID=4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d
LOG_LEVEL=INFO
APP_VERSION=1.0.0
```
No secrets required — portal uses only public Auth0 keys and public Deribit API.

## Local dev
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# or
.venv/bin/pip install -r requirements.txt       # macOS/Linux

# Run
AUTH0_DOMAIN=pezdev.us.auth0.com .venv/Scripts/uvicorn app.main:app --reload --port 8080
```

## Tests
```bash
.venv/Scripts/pytest tests/ -q   # Windows
.venv/bin/pytest tests/ -q       # macOS/Linux
```

## Adding a new app
1. Create `app/routers/<slug>/` with `__init__.py` and `routes.py`.
2. Add the router to `APP_REGISTRY` in `app/config.py`.
3. Update `USER_ROLES` to grant access to the right users.
4. Mount the router in `app/main.py` (`app.include_router(...)`).
5. Write a placeholder test in `tests/`.

## Stock dashboard notes
- Shows only **public** Deribit market data — no credentials, no personal positions.
- Personal trading data lives on zivnas behind VPN (not exposed here).
- Auto-refreshes every 30 seconds.

## Open work
- Frank's Auth0 account: create username/password in Auth0 dashboard.
- TruAge routers: replace stubs with real data logic.
- Microsoft 365 SSO: requires proper Azure app registration (long-term).
