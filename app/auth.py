"""Auth0 JWT validation for FastAPI routes.

Usage — protect an API route:
    from app.auth import require_auth, UserClaims
    @router.get("/data")
    async def get_data(user: UserClaims = Depends(require_auth)):
        return {"email": user.email}

The portal landing page (static HTML) handles auth client-side via the
Auth0 SPA SDK. This module protects the backend API routes so that even
direct API calls require a valid Bearer token.
"""

from __future__ import annotations

import httpx
from functools import lru_cache
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings, USER_ROLES

_bearer = HTTPBearer(auto_error=False)


class UserClaims(BaseModel):
    """Validated claims extracted from the Auth0 JWT."""
    sub: str
    email: str
    name: str = ""
    roles: list[str] = []       # app slugs this user may access


@lru_cache(maxsize=1)
def _get_jwks(domain: str) -> dict[str, Any]:
    """Fetch and cache Auth0 JWKS (public keys for JWT verification)."""
    url = f"https://{domain}/.well-known/jwks.json"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _verify_token(token: str) -> dict[str, Any]:
    """Verify the JWT signature and return the decoded payload."""
    settings = get_settings()
    domain = settings.auth0_domain

    jwks = _get_jwks(domain)
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed token: {exc}",
        ) from exc

    # Find the matching key by kid
    rsa_key: dict[str, str] = {}
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n":   key["n"],
                "e":   key["e"],
            }
            break

    if not rsa_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Unable to find matching public key")

    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            # audience validation is optional — enable if you configure an Auth0 API
            options={"verify_aud": bool(settings.auth0_audience)},
            audience=settings.auth0_audience or None,
            issuer=f"https://{domain}/",
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {exc}",
        ) from exc

    return payload


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserClaims:
    """FastAPI dependency — validates the Bearer token and returns user claims.

    Raises 401 if token is missing or invalid.
    Raises 403 if the user's email is not in USER_ROLES.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _verify_token(credentials.credentials)

    email = (payload.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token contains no email claim")

    allowed_slugs = USER_ROLES.get(email)
    if allowed_slugs is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied — your account is not authorised")

    return UserClaims(
        sub=payload.get("sub", ""),
        email=email,
        name=payload.get("name", email),
        roles=allowed_slugs,
    )


def require_app(slug: str):
    """Returns a dependency that checks the user has access to a specific app slug."""
    async def _check(user: UserClaims = Depends(require_auth)) -> UserClaims:
        if slug not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied — your account cannot access '{slug}'",
            )
        return user
    return _check
