"""FastAPI application entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from wodplanner.api.client import AuthenticationError
from wodplanner.app.routers import appointments, auth, calendar, friends, schedules, views

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("wodplanner.api.client").setLevel(logging.DEBUG)


app = FastAPI(
    title="WodPlanner API",
    description="Custom API for WodApp - schedule viewing and signup",
    version="0.1.0",
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
