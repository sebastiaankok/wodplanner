"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Form, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from wodplanner.api.client import AuthenticationError, WodAppClient, WodAppError
from wodplanner.app.config import settings
from wodplanner.app.dependencies import (
    get_session_service,
    require_session,
)
from wodplanner.models.auth import AuthSession
from wodplanner.services.session import SessionService

router = APIRouter(prefix="/auth", tags=["auth"])


class UserResponse(BaseModel):
    """Current user info."""

    user_id: int
    username: str
    firstname: str
    gym_id: int
    gym_name: str


@router.get("/me", response_model=UserResponse)
def get_current_user(
    session: Annotated[AuthSession, Depends(require_session)],
) -> UserResponse:
    """Get the current authenticated user."""
    return UserResponse(
        user_id=session.user_id,
        username=session.username,
        firstname=session.firstname,
        gym_id=session.gym_id,
        gym_name=session.gym_name,
    )


@router.post("/login")
def login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    session_service: SessionService = Depends(get_session_service),
) -> RedirectResponse:
    """
    Authenticate user and create browser session.

    Sets session_id cookie on success and redirects to home.
    Redirects to /login?error=... on failure.
    """
    try:
        # Create client and authenticate
        client = WodAppClient()
        auth_session = client.login(username, password)
        client.close()

        # Create browser session
        session_id = session_service.create(
            auth_session,
            expire_days=settings.session_expire_days,
        )

        # Redirect to home with session cookie
        redirect = RedirectResponse(url="/", status_code=303)
        redirect.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.session_expire_days * 24 * 60 * 60,
        )
        return redirect

    except AuthenticationError as e:
        return RedirectResponse(
            url=f"/login?error=Invalid credentials",
            status_code=303,
        )
    except WodAppError as e:
        return RedirectResponse(
            url=f"/login?error=Login failed: {e}",
            status_code=303,
        )


@router.post("/logout")
def logout(
    session_id: Annotated[str | None, Cookie()] = None,
    session_service: SessionService = Depends(get_session_service),
) -> RedirectResponse:
    """
    Log out user by clearing session.

    Deletes session from database and clears cookie.
    """
    # Delete session from database if it exists
    if session_id:
        session_service.delete(session_id)

    # Clear cookie and redirect to login
    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie(key="session_id")
    return redirect
