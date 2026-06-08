"""Unit tests for admin panel config.py patching logic."""

import ast
import pytest

from app.routers.admin.routes import (
    _build_app_registry_block,
    _build_user_roles_block,
    _patch_config_py,
)

_MINIMAL_CONFIG = '''\
"""Portal configuration."""

APP_REGISTRY = [
    {
        "slug": "benchmark",
        "title": "BenchPoint",
        "description": "Benchmark app.",
        "icon": "📊",
        "color": "#005eb8",
        "order": 20,
        "url": "https://example.com",
        "external": True,
    },
]

USER_ROLES: dict[str, list[str]] = {
    "alice@example.com": [
        "benchmark",
    ],
}


class Settings:
    pass
'''


def test_roundtrip_preserves_structure():
    users = {"alice@example.com": ["benchmark"]}
    patched = _patch_config_py(_MINIMAL_CONFIG, users)
    ast.parse(patched)
    assert 'APP_REGISTRY = [' in patched
    assert 'class Settings' in patched


def test_user_roles_updated():
    users = {"bob@example.com": ["stock", "benchmark"]}
    patched = _patch_config_py(_MINIMAL_CONFIG, users)
    assert '"bob@example.com"' in patched
    assert '"alice@example.com"' not in patched


def test_backslash_in_replacement_is_literal():
    # re.sub replacement strings treat \1, \n etc. specially — lambda prevents that.
    # Emails won't have backslashes, but slugs/emails with special chars must be safe.
    users = {"alice@example.com": ["benchmark"]}
    patched = _patch_config_py(_MINIMAL_CONFIG, users)
    ast.parse(patched)  # would raise SyntaxError if backslash mangling occurred


def test_multiple_users_sorted():
    users = {"zoe@example.com": ["stock"], "alice@example.com": ["benchmark"]}
    patched = _patch_config_py(_MINIMAL_CONFIG, users)
    alice_pos = patched.index('"alice@example.com"')
    zoe_pos = patched.index('"zoe@example.com"')
    assert alice_pos < zoe_pos


def test_raises_if_no_user_roles_block():
    bad_source = '"""config"""\nAPP_REGISTRY = []\n'
    with pytest.raises(ValueError, match="Expected to replace 1 USER_ROLES block"):
        _patch_config_py(bad_source, {"a@b.com": []})


def test_patched_source_is_valid_python():
    users = {
        "ziv.paul@gmail.com": ["admin", "benchmark", "stock"],
        "frank@example.org": ["benchmark"],
    }
    patched = _patch_config_py(_MINIMAL_CONFIG, users)
    ast.parse(patched)


def test_build_user_roles_block_empty():
    block = _build_user_roles_block({})
    assert block == "USER_ROLES: dict[str, list[str]] = {\n}"


def test_build_user_roles_block_structure():
    block = _build_user_roles_block({"a@b.com": ["x", "y"]})
    ast.parse(block.replace("USER_ROLES: dict[str, list[str]] = ", "roles = "))
    assert '"x"' in block
    assert '"y"' in block


def test_build_app_registry_block_structure():
    block = _build_app_registry_block([
        {
            "slug": "benchmark",
            "title": "BenchPoint",
            "description": "Benchmark app.",
            "icon": "📊",
            "color": "#005eb8",
            "order": 20,
            "url": "https://example.com",
            "external": True,
        }
    ])
    ast.parse(block.replace("APP_REGISTRY = ", "apps = "))
    assert '"order": 20' in block
    assert '"color": ' in block


def test_patch_config_can_update_app_registry():
    users = {"alice@example.com": ["benchmark"]}
    apps = [
        {
            "slug": "benchmark",
            "title": "BenchPoint",
            "description": "Benchmark app.",
            "icon": "📊",
            "color": "#123456",
            "order": 5,
            "url": "https://example.com",
            "external": True,
        }
    ]
    patched = _patch_config_py(_MINIMAL_CONFIG, users, new_apps=apps)
    ast.parse(patched)
    assert '"color": \'#123456\'' in patched
    assert '"order": 5' in patched
