"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Form, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from wodplanner.api.client import AuthenticationError, WodAppClient, WodAppError
from wodplanner.app.config import settings
from wodplanner.app.dependencies import require_session
from wodplanner.models.auth import AuthSession
from wodplanner.services import session as cookie_session

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
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    """
    Authenticate user and create browser session.

    Sets signed session cookie on success and redirects to home.
    Redirects to /login?error=... on failure.
    """
    try:
        client = WodAppClient()
        auth_session = client.login(username, password)
        client.close()

        session_value = cookie_session.encode(auth_session, settings.secret_key)

        redirect = RedirectResponse(url="/", status_code=303)
        redirect.set_cookie(
            key="session",
            value=session_value,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.session_expire_days * 24 * 60 * 60,
        )
        return redirect

    except AuthenticationError:
        return RedirectResponse(
            url="/login?error=Invalid credentials",
            status_code=303,
        )
    except WodAppError as e:
        return RedirectResponse(
            url=f"/login?error=Login failed: {e}",
            status_code=303,
        )


@router.post("/logout")
def logout() -> RedirectResponse:
    """Log out user by clearing session cookie."""
    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie(key="session")
    return redirect
