"""Pez Portal — FastAPI entry point."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

import asyncio

from app.config import get_settings, APP_REGISTRY, USER_ROLES
from app.daily_cache import account_cache, activation_cache
from app.report_tokens import redeem_token, purge_expired
from app.routers.admin.routes import router as admin_router
from app.routers.truage_activation.routes import router as truage_activation_router, run_daily as run_activation_daily
from app.routers.truage_account.routes import router as truage_account_router, run_daily as run_account_daily
from app.routers.stock.routes import router as stock_router

_STATIC_DIR = Path(__file__).parent / "static"


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout,
                        level=getattr(logging, log_level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if log_level == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    _configure_logging(settings.log_level)
    logger = structlog.get_logger()
    logger.info("Pez Portal starting", version=settings.app_version)
    yield
    logger.info("Pez Portal shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Pez Portal",
        description="Internal app portal — role-based access to reporting tools.",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://nacsportal.up.railway.app",
            "https://990benchmark.up.railway.app",
            "http://localhost:8080",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "version": settings.app_version}

    @app.get("/api/daily-status", include_in_schema=False)
    async def daily_status() -> JSONResponse:
        return JSONResponse({
            "truage_account":    account_cache.to_status(),
            "truage_activation": activation_cache.to_status(),
        })

    @app.post("/api/cron/run-daily", include_in_schema=False)
    async def cron_run_daily(request: Request, token: str = "") -> JSONResponse:
        if not settings.cron_secret:
            return JSONResponse({"error": "CRON_SECRET not configured"}, status_code=503)
        # Accept secret via ?token= query param (Railway cron) or Authorization header
        auth_header = request.headers.get("Authorization", "")
        if token != settings.cron_secret and auth_header != f"Bearer {settings.cron_secret}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        # Fire background tasks — each triggers upstream refresh then waits ~75s
        # before caching. Return immediately so the cron caller doesn't time out.
        purge_expired()
        asyncio.create_task(run_account_daily())
        asyncio.create_task(run_activation_daily())
        return JSONResponse({"status": "triggered"})

    @app.get("/report/{token}", include_in_schema=False)
    async def public_report(token: str) -> Response:
        """Unauthenticated magic-link report viewer. Token valid for 24 hours."""
        slug = redeem_token(token)
        if not slug:
            return HTMLResponse("""
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;background:#F5F0E8;}
.box{background:#fff;border:1px solid #DDD8CE;border-left:6px solid #C0392B;
border-radius:10px;padding:2.5rem;max-width:480px;text-align:center;}
h2{color:#1A2332;margin:0 0 0.75rem;}p{color:#7A7060;font-size:0.9rem;line-height:1.6;}</style>
</head><body><div class="box">
<h2>Link Expired</h2>
<p>This report link has expired or is invalid.<br>
A fresh link arrives with each daily email at 6 AM CT.</p>
</div></body></html>""", status_code=410)

        cache = account_cache if slug == "truage_account" else activation_cache
        if not cache.available:
            return HTMLResponse("""
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;background:#F5F0E8;}
.box{background:#fff;border:1px solid #DDD8CE;border-left:6px solid #e6b800;
border-radius:10px;padding:2.5rem;max-width:480px;text-align:center;}
h2{color:#1A2332;margin:0 0 0.75rem;}p{color:#7A7060;font-size:0.9rem;line-height:1.6;}</style>
</head><body><div class="box">
<h2>Report Not Yet Available</h2>
<p>Today's report is still generating. Try again in a few minutes.</p>
</div></body></html>""", status_code=503)

        return Response(content=cache.html, media_type="text/html; charset=utf-8")

    @app.get("/", include_in_schema=False)
    async def portal() -> Response:
        portal_path = _STATIC_DIR / "portal.html"
        if portal_path.exists():
            return Response(content=portal_path.read_bytes(),
                            media_type="text/html; charset=utf-8")
        return HTMLResponse("<h1>Portal loading...</h1>")

    @app.get("/api/me")
    async def me(request: Request) -> JSONResponse:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        from app.auth import _verify_token, USER_ROLES as roles
        try:
            payload = _verify_token(auth_header[7:])
        except Exception as exc:
            return JSONResponse(status_code=401, content={"detail": str(exc)})
        email = (payload.get("email") or "").lower()
        allowed_slugs = roles.get(email, [])
        if not allowed_slugs:
            return JSONResponse(status_code=403, content={"detail": "Access denied"})
        visible_apps = [a for a in APP_REGISTRY if a["slug"] in allowed_slugs]
        return JSONResponse({
            "email": email,
            "name": payload.get("name", email),
            "apps": visible_apps,
            "roles": allowed_slugs,
        })

    app.include_router(admin_router)
    app.include_router(truage_activation_router)
    app.include_router(truage_account_router)
    app.include_router(stock_router)

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/{path:path}", include_in_schema=False)
    async def catch_all(path: str) -> RedirectResponse:
        return RedirectResponse(url="/")

    return app


app = create_app()
