"""FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, version
from .api import auth, dashboard, integrations, tasks, users
from .bootstrap import ensure_admin
from .db import run_migrations
from .services.poller import poller

STATIC_DIR = Path(__file__).parent / "web" / "static"
CSRF_HEADER = "x-xmender"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

log = logging.getLogger(__name__)

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


def create_app(*, start_poller: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        run_migrations()
        ensure_admin()
        version.build_info()  # pin the commit that is running now
        if start_poller:
            poller.start()
        yield
        await poller.stop()

    app = FastAPI(title="xMender", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Cookies are SameSite=Strict; the custom header additionally blocks
        # cross-site form posts, since browsers cannot add it without CORS.
        if request.url.path.startswith("/api/") and request.method in UNSAFE:
            if request.headers.get(CSRF_HEADER) != "1":
                return JSONResponse({"detail": "Missing request header."}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        elif request.url.path.startswith("/static/"):
            # Revalidate (ETag) so a changed app.js/style.css is picked up without a hard reload.
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    for r in (auth.router, users.router, integrations.router, tasks.router, dashboard.router):
        app.include_router(r)

    # Public: the page footer shows it on the login and /docs pages too.
    @app.get("/api/version", include_in_schema=False)
    def build():
        return {"version": __version__, **version.build_info()}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    # Public user docs (no login): the same content the in-app Docs modal shows.
    @app.get("/docs", include_in_schema=False)
    def docs():
        return FileResponse(STATIC_DIR / "docs.html", headers={"Cache-Control": "no-cache"})

    # PWA: both live at the root so the manifest and service worker scope cover the whole site.
    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(
            STATIC_DIR / "manifest.webmanifest",
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    return app
