"""HTML views for the web frontend."""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from wodplanner.api.client import WodAppClient
from wodplanner.app.dependencies import (
    get_client_from_session_for_view,
    get_friends_service,
    get_preferences_service,
    get_schedule_service,
    get_scheduler,
    get_session_from_cookie,
    require_session_for_view,
)
from wodplanner.models.auth import AuthSession
from wodplanner.models.queue import QueuedSignup, QueueStatus
from wodplanner.services.friends import FriendsService
from wodplanner.services.preferences import PreferencesService
from wodplanner.services.schedule import ScheduleService
from wodplanner.services.scheduler import SignupScheduler

# Class types that can be filtered
FILTERABLE_CLASS_TYPES = ["Open Gym", "CF101", "Teen Athlete", "HyCross"]

# Timezone for calculations
TZ = ZoneInfo("Europe/Amsterdam")


def is_signup_open(appt_name: str, appt_start: datetime) -> bool:
    """Check if signup is currently open for an appointment.

    Regular classes: open 7 days before class start
    CF101 classes: open 14 weeks before class start
    """
    now = datetime.now(TZ)
    appt_start_tz = appt_start.replace(tzinfo=TZ) if appt_start.tzinfo is None else appt_start

    if "CF101" in appt_name or "101" in appt_name:
        # 14 weeks = 98 days
        signup_opens = appt_start_tz - timedelta(weeks=14)
    else:
        # 7 days
        signup_opens = appt_start_tz - timedelta(days=7)

    return now >= signup_opens

router = APIRouter(tags=["views"])

# Setup templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=templates_dir)


def render(request: Request, name: str, context: dict):
    """Render a template with context."""
    return templates.TemplateResponse(request=request, name=name, context=context)


def get_user_context(session: AuthSession) -> dict:
    """Get common user context for templates."""
    return {
        "user": {
            "firstname": session.firstname,
            "username": session.username,
        }
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: str | None = None,
    session: Annotated[AuthSession | None, Depends(get_session_from_cookie)] = None,
):
    """Login page."""
    # Redirect to home if already authenticated
    if session is not None:
        return RedirectResponse(url="/", status_code=303)

    return render(request, "login.html", {"error": error})


@router.get("/", response_class=HTMLResponse)
def calendar_page(
    request: Request,
    day: str | None = None,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Main calendar page."""
    target_date = date.fromisoformat(day) if day else date.today()
    prev_date = (target_date - timedelta(days=1)).isoformat()
    next_date = (target_date + timedelta(days=1)).isoformat()

    appointments = client.get_day_schedule(target_date)
    friend_ids = friends_service.get_appuser_ids(session.user_id)
    friends_map = {f.appuser_id: f for f in friends_service.get_all(session.user_id)}
    hidden_types = prefs_service.get_hidden_class_types(session.user_id)

    # Build appointment data with friends
    appt_data = []
    for appt in appointments:
        # Filter hidden class types
        if appt.name in hidden_types:
            continue

        friends_in_class = []
        if friend_ids:
            try:
                details = client.get_appointment_details(
                    appt.id_appointment, appt.date_start, appt.date_end
                )
                for member in details.subscriptions.members:
                    if member.id_appuser in friend_ids:
                        friend = friends_map.get(member.id_appuser)
                        friends_in_class.append({
                            "id": member.id_appuser,
                            "name": friend.name if friend else member.name,
                        })
            except Exception:
                pass

        # Construct actual datetime for this instance (template date may be historical)
        actual_start = datetime.combine(target_date, appt.date_start.time())
        actual_end = datetime.combine(target_date, appt.date_end.time())
        now = datetime.now()

        appt_data.append({
            "id": appt.id_appointment,
            "name": appt.name,
            "date_start": target_date.isoformat(),
            "date_end": target_date.isoformat(),
            "time_start": appt.date_start.strftime("%H:%M"),
            "time_end": appt.date_end.strftime("%H:%M"),
            "spots_taken": appt.total_subscriptions,
            "spots_total": appt.max_subscriptions,
            "status": appt.status,
            "friends": friends_in_class,
            "signup_open": is_signup_open(appt.name, actual_start),
            "is_past": actual_start < now,
        })

    weekday = target_date.strftime("%A")

    # Build filter state
    filters = [
        {"name": t, "hidden": t in hidden_types}
        for t in FILTERABLE_CLASS_TYPES
    ]

    return render(
        request,
        "calendar.html",
        {
            "active_page": "calendar",
            "appointments": appt_data,
            "display_date": target_date.strftime("%B %d, %Y"),
            "weekday": weekday,
            "prev_date": prev_date,
            "next_date": next_date,
            "today": date.today().isoformat(),
            "current_date": target_date.isoformat(),
            "filters": filters,
            **get_user_context(session),
        },
    )


@router.get("/calendar/{day}", response_class=HTMLResponse)
def calendar_day_partial(
    request: Request,
    day: str,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Calendar day partial for htmx updates."""
    target_date = date.fromisoformat(day)
    prev_date = (target_date - timedelta(days=1)).isoformat()
    next_date = (target_date + timedelta(days=1)).isoformat()

    appointments = client.get_day_schedule(target_date)
    friend_ids = friends_service.get_appuser_ids(session.user_id)
    friends_map = {f.appuser_id: f for f in friends_service.get_all(session.user_id)}
    hidden_types = prefs_service.get_hidden_class_types(session.user_id)

    appt_data = []
    for appt in appointments:
        # Filter hidden class types
        if appt.name in hidden_types:
            continue

        friends_in_class = []
        if friend_ids:
            try:
                details = client.get_appointment_details(
                    appt.id_appointment, appt.date_start, appt.date_end
                )
                for member in details.subscriptions.members:
                    if member.id_appuser in friend_ids:
                        friend = friends_map.get(member.id_appuser)
                        friends_in_class.append({
                            "id": member.id_appuser,
                            "name": friend.name if friend else member.name,
                        })
            except Exception:
                pass

        # Construct actual datetime for this instance (template date may be historical)
        actual_start = datetime.combine(target_date, appt.date_start.time())
        actual_end = datetime.combine(target_date, appt.date_end.time())
        now = datetime.now()

        appt_data.append({
            "id": appt.id_appointment,
            "name": appt.name,
            "date_start": target_date.isoformat(),
            "date_end": target_date.isoformat(),
            "time_start": appt.date_start.strftime("%H:%M"),
            "time_end": appt.date_end.strftime("%H:%M"),
            "spots_taken": appt.total_subscriptions,
            "spots_total": appt.max_subscriptions,
            "status": appt.status,
            "friends": friends_in_class,
            "signup_open": is_signup_open(appt.name, actual_start),
            "is_past": actual_start < now,
        })

    weekday = target_date.strftime("%A")

    # Build filter state
    filters = [
        {"name": t, "hidden": t in hidden_types}
        for t in FILTERABLE_CLASS_TYPES
    ]

    return render(
        request,
        "partials/calendar_day.html",
        {
            "appointments": appt_data,
            "display_date": target_date.strftime("%B %d, %Y"),
            "weekday": weekday,
            "prev_date": prev_date,
            "next_date": next_date,
            "today": date.today().isoformat(),
            "current_date": target_date.isoformat(),
            "filters": filters,
        },
    )


@router.post("/filters/toggle/{class_type}", response_class=HTMLResponse)
def toggle_filter(
    request: Request,
    class_type: str,
    current_date: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Toggle a class type filter."""
    prefs_service.toggle_hidden_class_type(session.user_id, class_type)
    return calendar_day_partial(
        request=request,
        day=current_date,
        session=session,
        client=client,
        friends_service=friends_service,
        prefs_service=prefs_service,
    )


@router.get("/friends", response_class=HTMLResponse)
def friends_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    friends_service: FriendsService = Depends(get_friends_service),
):
    """Friends management page."""
    friends = friends_service.get_all(session.user_id)
    friends_data = [
        {
            "id": f.id,
            "appuser_id": f.appuser_id,
            "name": f.name,
            "added_at": f.added_at.isoformat() if f.added_at else "",
        }
        for f in friends
    ]

    return render(
        request,
        "friends.html",
        {
            "active_page": "friends",
            "friends": friends_data,
            **get_user_context(session),
        },
    )


@router.post("/friends/add", response_class=HTMLResponse)
def add_friend_view(
    request: Request,
    appuser_id: int = Form(...),
    name: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    friends_service: FriendsService = Depends(get_friends_service),
):
    """Add a friend (htmx form submission)."""
    friends_service.add(session.user_id, appuser_id, name)
    friends = friends_service.get_all(session.user_id)
    friends_data = [
        {
            "id": f.id,
            "appuser_id": f.appuser_id,
            "name": f.name,
            "added_at": f.added_at.isoformat() if f.added_at else "",
        }
        for f in friends
    ]

    return render(request, "partials/friends_list.html", {"friends": friends_data})


@router.delete("/friends/{friend_id}/delete", response_class=HTMLResponse)
def delete_friend_view(
    request: Request,
    friend_id: int,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    friends_service: FriendsService = Depends(get_friends_service),
):
    """Delete a friend (htmx)."""
    friends_service.delete(session.user_id, friend_id)
    friends = friends_service.get_all(session.user_id)
    friends_data = [
        {
            "id": f.id,
            "appuser_id": f.appuser_id,
            "name": f.name,
            "added_at": f.added_at.isoformat() if f.added_at else "",
        }
        for f in friends
    ]

    return render(request, "partials/friends_list.html", {"friends": friends_data})


@router.get("/queue", response_class=HTMLResponse)
def queue_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    scheduler: SignupScheduler = Depends(get_scheduler),
):
    """Queue management page."""
    queue_items = scheduler.queue_service.get_all_for_user(session.user_id, include_completed=True)
    queue_data = [
        {
            "id": item.id,
            "appointment_id": item.appointment_id,
            "appointment_name": item.appointment_name,
            "date": item.date_start.date().isoformat(),
            "time_start": item.date_start.strftime("%H:%M"),
            "time_end": item.date_end.strftime("%H:%M"),
            "signup_opens_at": item.signup_opens_at.isoformat() if item.signup_opens_at else "",
            "status": item.status,
            "result_message": item.result_message,
        }
        for item in queue_items
    ]

    return render(
        request,
        "queue.html",
        {
            "active_page": "queue",
            "queue_items": queue_data,
            **get_user_context(session),
        },
    )


@router.post("/queue/add", response_class=HTMLResponse)
def add_to_queue_view(
    request: Request,
    appointment_id: int = Form(...),
    date_start: str = Form(...),
    date_end: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    scheduler: SignupScheduler = Depends(get_scheduler),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Add to queue from calendar (htmx)."""
    start = datetime.strptime(date_start, "%Y-%m-%d %H:%M")
    end = datetime.strptime(date_end, "%Y-%m-%d %H:%M")

    # Get appointment details
    details = client.get_appointment_details(appointment_id, start, end)

    # Parse signup open date
    signup_opens_at = datetime.strptime(
        details.subscription_open_date, "%d-%m-%Y %H:%M"
    )

    signup = QueuedSignup(
        appointment_id=appointment_id,
        appointment_name=details.name,
        date_start=start,
        date_end=end,
        signup_opens_at=signup_opens_at,
        status=QueueStatus.PENDING,
        user_token=session.token,
        user_id=session.user_id,
    )

    scheduler.add_signup(signup)

    # Return updated calendar
    return calendar_day_partial(
        request=request,
        day=start.date().isoformat(),
        session=session,
        client=client,
        friends_service=friends_service,
        prefs_service=prefs_service,
    )


@router.delete("/queue/{queue_id}/cancel", response_class=HTMLResponse)
def cancel_queue_view(
    request: Request,
    queue_id: int,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    scheduler: SignupScheduler = Depends(get_scheduler),
):
    """Cancel a queued signup (htmx)."""
    item = scheduler.queue_service.get(queue_id)
    if item and item.user_id == session.user_id:
        scheduler.cancel_signup(queue_id)

    queue_items = scheduler.queue_service.get_all_for_user(session.user_id, include_completed=True)
    queue_data = [
        {
            "id": item.id,
            "appointment_id": item.appointment_id,
            "appointment_name": item.appointment_name,
            "date": item.date_start.date().isoformat(),
            "time_start": item.date_start.strftime("%H:%M"),
            "time_end": item.date_end.strftime("%H:%M"),
            "signup_opens_at": item.signup_opens_at.isoformat() if item.signup_opens_at else "",
            "status": item.status,
            "result_message": item.result_message,
        }
        for item in queue_items
    ]

    return render(request, "partials/queue_list.html", {"queue_items": queue_data})


@router.post("/appointments/{appointment_id}/subscribe", response_class=HTMLResponse)
def subscribe_view(
    request: Request,
    appointment_id: int,
    date_start: str = Form(...),
    date_end: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Subscribe to appointment from calendar (htmx)."""
    start = datetime.strptime(date_start, "%Y-%m-%d %H:%M")
    end = datetime.strptime(date_end, "%Y-%m-%d %H:%M")

    client.subscribe(appointment_id, start, end)

    # Return updated calendar
    return calendar_day_partial(
        request=request,
        day=start.date().isoformat(),
        session=session,
        client=client,
        friends_service=friends_service,
        prefs_service=prefs_service,
    )


@router.post("/appointments/{appointment_id}/waitinglist", response_class=HTMLResponse)
def waitinglist_view(
    request: Request,
    appointment_id: int,
    date_start: str = Form(...),
    date_end: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Join waiting list from calendar (htmx)."""
    start = datetime.strptime(date_start, "%Y-%m-%d %H:%M")
    end = datetime.strptime(date_end, "%Y-%m-%d %H:%M")

    client.subscribe_waitinglist(appointment_id, start, end)

    # Return updated calendar
    return calendar_day_partial(
        request=request,
        day=start.date().isoformat(),
        session=session,
        client=client,
        friends_service=friends_service,
        prefs_service=prefs_service,
    )


@router.post("/appointments/{appointment_id}/unsubscribe", response_class=HTMLResponse)
def unsubscribe_view(
    request: Request,
    appointment_id: int,
    date_start: str = Form(...),
    date_end: str = Form(...),
    is_waitinglist: str = Form("false"),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Unsubscribe from appointment (htmx)."""
    start = datetime.strptime(date_start, "%Y-%m-%d %H:%M")
    end = datetime.strptime(date_end, "%Y-%m-%d %H:%M")

    if is_waitinglist == "true":
        client.unsubscribe_waitinglist(appointment_id, start, end)
    else:
        client.unsubscribe(appointment_id, start, end)

    # Return updated calendar
    return calendar_day_partial(
        request=request,
        day=start.date().isoformat(),
        session=session,
        client=client,
        friends_service=friends_service,
        prefs_service=prefs_service,
    )


@router.get("/appointments/{appointment_id}/people", response_class=HTMLResponse)
def people_modal_view(
    request: Request,
    appointment_id: int,
    date_start: str,
    date_end: str,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
):
    """Get participants for an appointment (htmx modal)."""
    start = datetime.strptime(date_start, "%Y-%m-%d %H:%M")
    end = datetime.strptime(date_end, "%Y-%m-%d %H:%M")

    details = client.get_appointment_details(appointment_id, start, end)
    friend_ids = friends_service.get_appuser_ids(session.user_id)
    current_user_id = session.user_id

    participants = []
    for member in details.subscriptions.members:
        participants.append({
            "id": member.id_appuser,
            "name": member.name,
            "is_friend": member.id_appuser in friend_ids,
            "is_self": member.id_appuser == current_user_id,
        })

    # Sort: self first, then friends, then alphabetically
    participants.sort(key=lambda p: (not p["is_self"], not p["is_friend"], p["name"].lower()))

    return render(
        request,
        "partials/people_modal.html",
        {
            "appointment_id": appointment_id,
            "appointment_name": details.name,
            "date_start": date_start,
            "date_end": date_end,
            "participants": participants,
            "total_spots": details.max_subscriptions,
            "taken_spots": len(details.subscriptions.members),
        },
    )


@router.post("/friends/add-from-people", response_class=HTMLResponse)
def add_friend_from_people(
    request: Request,
    appuser_id: int = Form(...),
    name: str = Form(...),
    appointment_id: int = Form(...),
    date_start: str = Form(...),
    date_end: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
):
    """Add a friend from the people modal."""
    friends_service.add(session.user_id, appuser_id, name)

    # Return updated modal
    return people_modal_view(
        request=request,
        appointment_id=appointment_id,
        date_start=date_start,
        date_end=date_end,
        session=session,
        client=client,
        friends_service=friends_service,
    )


@router.get("/appointments/{appointment_id}/schedule", response_class=HTMLResponse)
def schedule_modal_view(
    request: Request,
    appointment_id: int,
    date_start: str,
    class_name: str,
    schedule_service: ScheduleService = Depends(get_schedule_service),
):
    """Get workout schedule for an appointment (htmx modal)."""
    # Parse date from date_start (format: "YYYY-MM-DD HH:MM")
    schedule_date = date.fromisoformat(date_start.split(" ")[0])

    # Look up schedule by date and class name
    schedule = schedule_service.get_by_date_and_class(schedule_date, class_name)

    return render(
        request,
        "partials/schedule_modal.html",
        {
            "appointment_name": class_name,
            "schedule_date": schedule_date.strftime("%A, %B %d, %Y"),
            "schedule": schedule,
        },
    )
