"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from wodplanner.api.client import AuthenticationError
from wodplanner.app.dependencies import get_scheduler, get_session_service
from wodplanner.app.routers import appointments, auth, calendar, friends, queue, schedules, views

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: start the scheduler
    scheduler = get_scheduler()
    scheduler.start()
    logger.info("Application started, scheduler running")

    yield

    # Shutdown: stop scheduler
    scheduler.stop()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="WodPlanner API",
    description="Custom API for WodApp - schedule viewing and auto-signup",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(
    request: Request, exc: AuthenticationError
) -> Response:
    """Handle authentication errors by redirecting to login."""
    logger.warning(f"Authentication error: {exc}")

    # Try to delete the invalid session
    session_id = request.cookies.get("session_id")
    if session_id:
        session_service = get_session_service()
        session_service.delete(session_id)

    # Check if this is an HTMX request
    if request.headers.get("HX-Request"):
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = "/login?error=session_expired"
        response.delete_cookie(key="session_id")
        return response

    # Regular request - redirect
    response = RedirectResponse(url="/login?error=session_expired", status_code=303)
    response.delete_cookie(key="session_id")
    return response


# Include API routers (prefixed with /api)
app.include_router(auth.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(appointments.router, prefix="/api")
app.include_router(queue.router, prefix="/api")
app.include_router(friends.router, prefix="/api")
app.include_router(schedules.router, prefix="/api")

# Include views router (HTML pages)
app.include_router(views.router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "wodplanner"}
