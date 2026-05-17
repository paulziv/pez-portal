"""Tests for app.config — registry structure and role mapping."""

import pytest
from app.config import APP_REGISTRY, USER_ROLES, get_settings


def test_app_registry_has_required_keys():
    required = {"slug", "title", "description", "icon", "color", "url", "external"}
    for app in APP_REGISTRY:
        missing = required - app.keys()
        assert not missing, f"App '{app.get('slug')}' is missing keys: {missing}"


def test_app_registry_slugs_unique():
    slugs = [app["slug"] for app in APP_REGISTRY]
    assert len(slugs) == len(set(slugs)), "Duplicate slugs found in APP_REGISTRY"


def test_user_roles_slugs_exist_in_registry():
    valid_slugs = {app["slug"] for app in APP_REGISTRY}
    for email, slugs in USER_ROLES.items():
        for slug in slugs:
            assert slug in valid_slugs, (
                f"User '{email}' has slug '{slug}' not in APP_REGISTRY"
            )


def test_paul_has_all_apps():
    paul_roles = USER_ROLES.get("ziv.paul@gmail.com", [])
    all_slugs = {app["slug"] for app in APP_REGISTRY}
    assert all_slugs == set(paul_roles), (
        f"Paul is missing apps: {all_slugs - set(paul_roles)}"
    )


def test_frank_has_only_benchmark():
    frank_roles = USER_ROLES.get("fgleeson@convenience.org", [])
    assert frank_roles == ["benchmark"], f"Unexpected roles for Frank: {frank_roles}"


def test_settings_defaults():
    settings = get_settings()
    assert settings.auth0_domain == "pezdev.us.auth0.com"
    assert settings.app_version == "1.0.0"
    assert settings.log_level == "INFO"
