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

from app.config import get_settings, APP_REGISTRY, USER_ROLES
from app.routers.admin.routes import router as admin_router
from app.routers.truage_activation.routes import router as truage_activation_router
from app.routers.truage_account.routes import router as truage_account_router
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
