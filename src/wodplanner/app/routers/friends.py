"""Friends management endpoints."""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from wodplanner.app.dependencies import get_friends_service, require_session
from wodplanner.models.auth import AuthSession
from wodplanner.services.friends import FriendsService

router = APIRouter(prefix="/friends", tags=["friends"])


class FriendResponse(BaseModel):
    """Response model for a friend."""

    id: int
    appuser_id: int
    name: str
    added_at: str


class AddFriendRequest(BaseModel):
    """Request to add a friend."""

    appuser_id: int
    name: str


@router.get("", response_model=list[FriendResponse])
def list_friends(
    session: AuthSession = Depends(require_session),
    friends_service: FriendsService = Depends(get_friends_service),
) -> list[FriendResponse]:
    """List all friends."""
    friends = friends_service.get_all(session.user_id)
    return [
        FriendResponse(
            id=cast(int, f.id),
            appuser_id=f.appuser_id,
            name=f.name,
            added_at=f.added_at.isoformat() if f.added_at else "",
        )
        for f in friends
    ]


@router.post("", response_model=FriendResponse)
def add_friend(
    request: AddFriendRequest,
    session: AuthSession = Depends(require_session),
    friends_service: FriendsService = Depends(get_friends_service),
) -> FriendResponse:
    """Add a friend by their WodApp user ID."""
    friend = friends_service.add(session.user_id, request.appuser_id, request.name)
    return FriendResponse(
        id=cast(int, friend.id),
        appuser_id=friend.appuser_id,
        name=friend.name,
        added_at=friend.added_at.isoformat() if friend.added_at else "",
    )


@router.get("/{friend_id}", response_model=FriendResponse)
def get_friend(
    friend_id: int,
    session: AuthSession = Depends(require_session),
    friends_service: FriendsService = Depends(get_friends_service),
) -> FriendResponse:
    """Get a friend by ID."""
    friend = friends_service.get(session.user_id, friend_id)
    if not friend:
        raise HTTPException(status_code=404, detail="Friend not found")
    return FriendResponse(
        id=cast(int, friend.id),
        appuser_id=friend.appuser_id,
        name=friend.name,
        added_at=friend.added_at.isoformat() if friend.added_at else "",
    )


@router.delete("/{friend_id}")
def delete_friend(
    friend_id: int,
    session: AuthSession = Depends(require_session),
    friends_service: FriendsService = Depends(get_friends_service),
) -> dict:
    """Remove a friend."""
    if not friends_service.delete(session.user_id, friend_id):
        raise HTTPException(status_code=404, detail="Friend not found")
    return {"success": True, "message": "Friend removed"}
