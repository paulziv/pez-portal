"""Tests for top-level FastAPI routes (health, portal, /api/me auth)."""

import pytest
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
    assert b"Pez Portal" in content
    assert b"auth0-spa-js" in content


def test_api_me_no_token_returns_401():
    resp = client.get("/api/me")
    assert resp.status_code == 401


def test_api_me_bad_token_returns_401():
    resp = client.get("/api/me", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401


def test_stock_no_token():
    resp = client.get("/apps/stock/", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_truage_activation_no_token():
    resp = client.get("/apps/truage-activation/", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_truage_account_no_token():
    resp = client.get("/apps/truage-account/", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_admin_no_token():
    resp = client.get("/apps/admin/", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_unknown_path_redirects():
    resp = client.get("/does-not-exist", follow_redirects=False)
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers.get("location", "").endswith("/")
