"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Callable, cast

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

# Configure logging — use uvicorn's formatter for consistent style
from uvicorn.logging import DefaultFormatter  # noqa: E402

from wodplanner.api.client import AuthenticationError, WodAppError
from wodplanner.app.config import settings
from wodplanner.app.dependencies import _get_db_path
from wodplanner.app.routers import (
    appointments,
    auth,
    calendar,
    friends,
    schedules,
    views,
)

# Import services so their migrations register at import time
from wodplanner.services import friends as _friends_svc  # noqa: F401
from wodplanner.services import one_rep_max as _orm_svc  # noqa: F401
from wodplanner.services import preferences as _prefs_svc  # noqa: F401
from wodplanner.services import schedule as _schedule_svc  # noqa: F401
from wodplanner.services import session as cookie_session
from wodplanner.services.migrations import ensure_migrations

numeric_level = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.basicConfig(level=numeric_level)
for _handler in logging.root.handlers:
    _handler.setFormatter(DefaultFormatter("%(levelprefix)s %(name)s - %(message)s"))
logger = logging.getLogger(__name__)
logging.getLogger("wodplanner.api.client").setLevel(numeric_level)
logging.getLogger("wodplanner.services.api_cache").setLevel(numeric_level)
logging.getLogger("httpx").setLevel(logging.WARNING)


class _StripZeroPort(logging.Filter):
    """Remove ':0' fake port from uvicorn access log client_addr."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and isinstance(record.args, tuple) and len(record.args) >= 1:
            addr = record.args[0]
            if isinstance(addr, str) and addr.endswith(":0"):
                record.args = (addr[:-2],) + record.args[1:]
        return True


logging.getLogger("uvicorn.access").addFilter(_StripZeroPort())


class CloudflareIPMiddleware(BaseHTTPMiddleware):
    """Use CF-Connecting-IP as client address when behind Cloudflare tunnel."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            request.scope["client"] = (cf_ip, 0)
        return cast(Response, await call_next(request))


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set strict security headers on every response.

    CSP allows known CDNs and inline scripts/styles (required by HTMX/Chart.js).
    HSTS is production-only since dev runs on HTTP.
    """

    _csp = (
        "default-src 'self'; "
        "script-src 'self' https://unpkg.com https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "img-src 'self' https: data:; "
        "font-src 'self'; "
        "frame-src 'none'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'self'"
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = cast(Response, await call_next(request))
        response.headers["Content-Security-Policy"] = self._csp
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


class SessionUpgradeMiddleware(BaseHTTPMiddleware):
    """Transparently upgrade old signed-only cookies to encrypted Fernet format."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = cast(Response, await call_next(request))

        cookie = request.cookies.get("session")
        if cookie:
            max_age = (
                settings.session_expire_days * 24 * 60 * 60
                if settings.session_expire_days
                else None
            )
            _, upgraded = cookie_session.decode_and_upgrade(
                cookie, settings.secret_key, max_age
            )
            if upgraded is not None:
                cookie_max_age = (
                    settings.session_expire_days * 24 * 60 * 60
                    if settings.session_expire_days
                    else 400 * 24 * 60 * 60
                )
                response.set_cookie(
                    key="session",
                    value=upgraded,
                    httponly=True,
                    secure=settings.cookie_secure if settings.cookie_secure is not None else False,
                    samesite="lax",
                    max_age=cookie_max_age,
                )

        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run pending schema migrations at startup."""
    db_path = _get_db_path()
    ran = ensure_migrations(db_path)
    if ran:
        logger.info("Applied %d migration(s) on %s: %s", len(ran), db_path, ran)
    else:
        logger.debug("No pending migrations on %s", db_path)
    yield


app = FastAPI(
    title="WodPlanner API",
    description="Custom API for WodApp - schedule viewing and signup",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> str:
    return "User-agent: *\nDisallow: /\n"

app.add_middleware(CloudflareIPMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionUpgradeMiddleware)

@app.exception_handler(WodAppError)
async def wodapp_error_handler(request: Request, exc: WodAppError) -> Response:
    """Handle WodApp API errors with a user-friendly page."""
    if request.headers.get("HX-Request"):
        return HTMLResponse(
            content=f'<div style="padding:1rem;background:#fee2e2;color:#dc2626;border-radius:0.375rem;margin:1rem 0">{exc}</div>',
            status_code=200,
        )
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Service Unavailable</title>
<style>
body{{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f1f5f9}}
.card{{background:white;border-radius:0.5rem;box-shadow:0 4px 6px rgba(0,0,0,.1);padding:2rem;max-width:400px;text-align:center}}
h1{{font-size:1.25rem;color:#1e293b;margin:0 0 0.5rem}}
p{{color:#64748b;font-size:0.875rem;margin:0 0 1.5rem}}
a{{color:#2563eb;text-decoration:none;font-size:0.875rem}}
</style></head>
<body><div class="card">
<h1>Service Unavailable</h1>
<p>{exc}</p>
<a href="/">← Go back</a>
</div></body></html>""",
        status_code=503,
    )


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(
    request: Request, exc: AuthenticationError
) -> Response:
    """Handle authentication errors by redirecting to login."""
    logger.warning(f"Authentication error: {exc}")

    if request.headers.get("HX-Request"):
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = "/login?error=session_expired"
        response.delete_cookie(key="session")
        return response

    response = RedirectResponse(url="/login?error=session_expired", status_code=303)
    response.delete_cookie(key="session")
    return response


# Include API routers (prefixed with /api)
app.include_router(auth.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(appointments.router, prefix="/api")
app.include_router(friends.router, prefix="/api")
app.include_router(schedules.router, prefix="/api")

# Include views router (HTML pages)
app.include_router(views.router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "wodplanner"}