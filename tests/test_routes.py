"""Tests for top-level FastAPI routes (health, portal, /api/me auth)."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app

client = TestClient(app, raise_server_exceptions=True)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_portal_returns_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Pez Portal" in resp.text


def test_api_me_no_token_returns_401():
    resp = client.get("/api/me")
    assert resp.status_code == 401


def test_api_me_bad_token_returns_401():
    resp = client.get("/api/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_stock_ui_no_token_returns_401_or_403():
    resp = client.get("/apps/stock/", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_truage_activation_no_token_returns_401_or_403():
    resp = client.get("/apps/truage-activation/", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_truage_account_no_token_returns_401_or_403():
    resp = client.get("/apps/truage-account/", follow_redirects=False)
    assert resp.status_code in (401, 403)


def test_unknown_path_redirects_to_root():
    resp = client.get("/does-not-exist", follow_redirects=False)
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers.get("location", "").endswith("/")
