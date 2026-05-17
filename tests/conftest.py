"""Shared pytest fixtures for pez-portal tests."""

import os
import pytest

# Ensure settings validation passes without real env vars
os.environ.setdefault("AUTH0_DOMAIN", "pezdev.us.auth0.com")
os.environ.setdefault("AUTH0_CLIENT_ID", "test-client-id")
