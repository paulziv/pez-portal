"""Tests for top-level FastAPI routes (health, portal, /api/me auth)."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=True)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_portal_html_file_exists():
    from pathlib import Path
    portal = Path(__file__).parent.parent / "app" / "static" / "portal.html"
    assert portal.exists(), "portal.html is missing"
    content = portal.read_bytes()
    assert b"<!DOCTYPE html>" in content
    assert b"Innovation Portal" in content  # renamed from Pez Portal
    assert b"auth0-spa-js" in content


def test_api_me_no_token_returns_401():
    resp = client.get("/api/me")
    assert resp.status_code == 401


def test_api_me_bad_token_returns_401():
    resp = client.get("/api/me", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401


# HTML shell routes return 200 — auth is handled client-side via Auth0 SPA SDK.
# The API sub-routes (/api/*) remain protected and return 401 without a token.

def test_stock_ui_returns_html():
    resp = client.get("/apps/stock/", follow_redirects=False)
    assert resp.status_code == 200
    assert b"auth0-spa-js" in resp.content


def test_stock_api_no_token_returns_401():
    resp = client.get("/apps/stock/api/index-price", follow_redirects=False)
    assert resp.status_code in (401, 403, 422)


def test_truage_activation_ui_returns_html():
    resp = client.get("/apps/truage-activation/", follow_redirects=False)
    assert resp.status_code == 200
    assert b"auth0-spa-js" in resp.content


def test_truage_activation_api_no_token_returns_401():
    resp = client.get("/apps/truage-activation/api/status", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_truage_account_ui_returns_html():
    resp = client.get("/apps/truage-account/", follow_redirects=False)
    assert resp.status_code == 200
    assert b"auth0-spa-js" in resp.content


def test_truage_account_api_no_token_returns_401():
    resp = client.get("/apps/truage-account/api/status", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_admin_ui_returns_html():
    resp = client.get("/apps/admin/", follow_redirects=False)
    assert resp.status_code == 200
    assert b"auth0-spa-js" in resp.content


def test_admin_api_no_token_returns_401():
    resp = client.get("/apps/admin/api/config", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_unknown_path_redirects():
    resp = client.get("/does-not-exist", follow_redirects=False)
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers.get("location", "").endswith("/")
