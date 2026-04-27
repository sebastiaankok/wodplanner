"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Callable, cast

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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
    google_sync,
    schedules,
    views,
)

# Import services so their migrations register at import time
from wodplanner.services import friends as _friends_svc  # noqa: F401
from wodplanner.services import google_accounts as _google_accounts_svc  # noqa: F401
from wodplanner.services import one_rep_max as _orm_svc  # noqa: F401
from wodplanner.services import preferences as _prefs_svc  # noqa: F401
from wodplanner.services import schedule as _schedule_svc  # noqa: F401
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


_PERIODIC_SYNC_INTERVAL_SECONDS = 30 * 60  # 30 minutes
_user_sync_locks: dict[int, asyncio.Lock] = {}


def _get_user_sync_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_sync_locks:
        _user_sync_locks[user_id] = asyncio.Lock()
    return _user_sync_locks[user_id]


async def _periodic_sync_all(db_path: Path) -> None:
    """Background task: sync all users with sync_enabled every 30 minutes."""
    from wodplanner.api.client import WodAppClient
    from wodplanner.models.auth import AuthSession
    from wodplanner.services import calendar_sync, crypto
    from wodplanner.services.google_accounts import GoogleAccountsService

    db = GoogleAccountsService(db_path)
    enc_key = crypto.get_enc_key(settings.google_token_enc_key, settings.secret_key)

    user_ids = db.get_all_sync_enabled_user_ids()
    logger.info("Periodic sync: %d user(s) with sync enabled", len(user_ids))

    for user_id in user_ids:
        lock = _get_user_sync_lock(user_id)
        if lock.locked():
            logger.debug("Periodic sync: user %d already syncing, skipping", user_id)
            continue
        async with lock:
            account = db.get_account(user_id)
            if not account:
                continue
            session_enc = db.get_wodapp_session_enc(user_id)
            if not session_enc:
                continue
            try:
                session_json = crypto.decrypt(session_enc, enc_key)
                wodapp_session = AuthSession.model_validate_json(session_json)
                client = WodAppClient.from_session(wodapp_session)
                await asyncio.to_thread(
                    calendar_sync.sync_user,
                    account=account,
                    db=db,
                    client=client,
                    enc_key=enc_key,
                    first_name=wodapp_session.firstname,
                    gym_name=wodapp_session.gym_name,
                )
            except Exception:
                logger.exception("Periodic sync failed for user %d", user_id)


async def _periodic_sync_task(db_path: Path) -> None:
    """Runs _periodic_sync_all on a fixed interval for the process lifetime."""
    while True:
        await asyncio.sleep(_PERIODIC_SYNC_INTERVAL_SECONDS)
        try:
            await _periodic_sync_all(db_path)
        except Exception:
            logger.exception("Periodic sync task error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run pending schema migrations and start background sync at startup."""
    db_path = _get_db_path()
    ran = ensure_migrations(db_path)
    if ran:
        logger.info("Applied %d migration(s) on %s: %s", len(ran), db_path, ran)
    else:
        logger.debug("No pending migrations on %s", db_path)

    sync_task = asyncio.create_task(_periodic_sync_task(db_path))
    yield
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="WodPlanner API",
    description="Custom API for WodApp - schedule viewing and signup",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.add_middleware(CloudflareIPMiddleware)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

# Include Google Calendar routes (no /api prefix — OAuth callbacks and view routes)
app.include_router(google_sync.router)

# Include views router (HTML pages)
app.include_router(views.router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "wodplanner"}
