"""HTML views for the web frontend."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from wodplanner.api.client import WodAppClient
from wodplanner.app.dependencies import (
    get_client_from_session_for_view,
    get_friends_service,
    get_one_rep_max_service,
    get_preferences_service,
    get_schedule_service,
    get_session_from_cookie,
    require_session_for_view,
)
from wodplanner.models.auth import AuthSession
from wodplanner.services.friends import FriendsService
from wodplanner.services.one_rep_max import OneRepMaxService, extract_1rm_exercises, has_1rm_exercise
from wodplanner.services.preferences import PreferencesService
from wodplanner.services.schedule import ScheduleService

# Class types that can be filtered
FILTERABLE_CLASS_TYPES = ["Open Gym", "CF101", "Teen Athlete", "HyCross", "CF Boxing", "Gymnastics", "Strength", "Small Group Strength Class"]

# Timezone for calculations
TZ = ZoneInfo("Europe/Amsterdam")


def _format_1rm_entries(entries):
    return [
        {
            "id": e.id,
            "exercise": e.exercise,
            "weight_kg": e.weight_kg,
            "recorded_at": e.recorded_at.strftime("%b %d, %Y"),
            "recorded_at_iso": e.recorded_at.isoformat(),
        }
        for e in entries
    ]


def _similarity_score(exercise: str, suggested: list[str]) -> int:
    ex_lower = exercise.lower()
    ex_words = set(ex_lower.split())
    best = 0
    for s in suggested:
        s_lower = s.lower()
        if ex_lower == s_lower:
            return 2
        s_words = set(s_lower.split())
        if s_lower in ex_lower or ex_lower in s_lower or ex_words & s_words:
            best = 1
    return best


def _build_exercises_chart_data(formatted_entries: list) -> str:
    data: dict[str, list] = {}
    for e in formatted_entries:
        ex = e["exercise"]
        if ex not in data:
            data[ex] = []
        data[ex].append({"date": e["recorded_at_iso"], "weight": e["weight_kg"], "label": e["recorded_at"]})
    for ex in data:
        data[ex].sort(key=lambda x: x["date"])
    return json.dumps(data).replace("</", "<\\/")


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
def home_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
):
    """Homepage showing upcoming reservations."""
    reservations, company_images = client.get_upcoming_reservations()

    # Group by date for display
    days: dict[str, list[dict]] = {}
    for r in reservations:
        day_key = r["date_start"].strftime("%Y-%m-%d")
        if day_key not in days:
            days[day_key] = []
        days[day_key].append({
            "id": r["id_appointment"],
            "name": r["name"],
            "time": r["date_start"].strftime("%H:%M"),
            "weekday": r["date_start"].strftime("%A"),
            "display_date": r["date_start"].strftime("%B %d"),
        })

    return render(
        request,
        "home.html",
        {
            "active_page": "home",
            "days": days,
            "gym_logo": company_images.get("logo", ""),
            **get_user_context(session),
        },
    )


@router.get("/calendar", response_class=HTMLResponse)
def calendar_page(
    request: Request,
    day: str | None = None,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
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
                members, _ = client.get_appointment_members(
                    appt.id_appointment, appt.date_start, appt.date_end
                )
                for member in members:
                    if member.id_appuser in friend_ids:
                        friend = friends_map.get(member.id_appuser)
                        friends_in_class.append({
                            "id": member.id_appuser,
                            "name": friend.name if friend else member.name,
                        })
            except Exception:
                pass

        # Check if workout contains a 1rm exercise
        schedule = schedule_service.find_for_appointment(appt.name, target_date, gym_id=session.gym_id)
        appt_has_1rm = schedule is not None and (
            has_1rm_exercise(schedule.strength_specialty)
            or has_1rm_exercise(schedule.warmup_mobility)
            or has_1rm_exercise(schedule.metcon)
        )

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
            "has_1rm": appt_has_1rm,
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
    schedule_service: ScheduleService = Depends(get_schedule_service),
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
                members, _ = client.get_appointment_members(
                    appt.id_appointment, appt.date_start, appt.date_end
                )
                for member in members:
                    if member.id_appuser in friend_ids:
                        friend = friends_map.get(member.id_appuser)
                        friends_in_class.append({
                            "id": member.id_appuser,
                            "name": friend.name if friend else member.name,
                        })
            except Exception:
                pass

        # Check if workout contains a 1rm exercise
        schedule = schedule_service.find_for_appointment(appt.name, target_date, gym_id=session.gym_id)
        appt_has_1rm = schedule is not None and (
            has_1rm_exercise(schedule.strength_specialty)
            or has_1rm_exercise(schedule.warmup_mobility)
            or has_1rm_exercise(schedule.metcon)
        )

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
            "has_1rm": appt_has_1rm,
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
    schedule_service: ScheduleService = Depends(get_schedule_service),
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
        schedule_service=schedule_service,
    )


@router.get("/1rm", response_class=HTMLResponse)
def one_rep_max_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    one_rep_max_service: OneRepMaxService = Depends(get_one_rep_max_service),
):
    """1RM tracking page."""
    raw = one_rep_max_service.get_all(session.user_id)
    past_exercises = one_rep_max_service.get_exercises(session.user_id)
    exercises = one_rep_max_service.get_exercise_list()
    entries = _format_1rm_entries(raw)

    return render(
        request,
        "one_rep_max.html",
        {
            "active_page": "1rm",
            "exercises": exercises,
            "past_exercises": past_exercises,
            "default_exercise": entries[0]["exercise"] if entries else "",
            "entries": entries,
            "exercises_data_json": _build_exercises_chart_data(entries),
            "today": date.today().isoformat(),
            **get_user_context(session),
        },
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
    schedule_service: ScheduleService = Depends(get_schedule_service),
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
        schedule_service=schedule_service,
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
    schedule_service: ScheduleService = Depends(get_schedule_service),
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
        schedule_service=schedule_service,
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
    schedule_service: ScheduleService = Depends(get_schedule_service),
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
        schedule_service=schedule_service,
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
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    schedule_service: ScheduleService = Depends(get_schedule_service),
):
    """Get workout schedule for an appointment (htmx modal)."""
    # Parse date from date_start (format: "YYYY-MM-DD HH:MM")
    schedule_date = date.fromisoformat(date_start.split(" ")[0])

    # Look up schedule by date and class name
    schedule = schedule_service.get_by_date_and_class(schedule_date, class_name, gym_id=session.gym_id)

    return render(
        request,
        "partials/schedule_modal.html",
        {
            "appointment_name": class_name,
            "schedule_date": schedule_date.strftime("%A, %B %d, %Y"),
            "schedule": schedule,
        },
    )


@router.get("/appointments/{appointment_id}/1rm", response_class=HTMLResponse)
def one_rep_max_modal_view(
    request: Request,
    appointment_id: int,
    date_start: str,
    class_name: str,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    schedule_service: ScheduleService = Depends(get_schedule_service),
    one_rep_max_service: OneRepMaxService = Depends(get_one_rep_max_service),
):
    """Get 1rm tracker modal for an appointment (htmx modal)."""
    schedule_date = date.fromisoformat(date_start.split(" ")[0])
    schedule = schedule_service.find_for_appointment(class_name, schedule_date, gym_id=session.gym_id)

    raw_suggested: list[str] = []
    if schedule:
        raw_suggested = extract_1rm_exercises(schedule.strength_specialty)
        raw_suggested += extract_1rm_exercises(schedule.warmup_mobility)
        raw_suggested += extract_1rm_exercises(schedule.metcon)

    # Map raw extracted names to canonical exercises via fuzzy match
    suggested_exercises: list[str] = []
    for s in raw_suggested:
        matched = one_rep_max_service.match_exercise(s) if not one_rep_max_service.validate_exercise(s) else s
        if matched and matched not in suggested_exercises:
            suggested_exercises.append(matched)

    exercises = one_rep_max_service.get_exercise_list()
    raw = one_rep_max_service.get_all(session.user_id)
    today = date.today().isoformat()

    formatted = [
        {
            "id": e.id,
            "exercise": e.exercise,
            "weight_kg": e.weight_kg,
            "recorded_at": e.recorded_at.strftime("%b %d, %Y"),
        }
        for e in raw
    ]
    if suggested_exercises:
        formatted.sort(key=lambda e: -_similarity_score(e["exercise"], suggested_exercises))

    return render(
        request,
        "partials/one_rep_max_modal.html",
        {
            "suggested_exercises": suggested_exercises,
            "exercises": exercises,
            "entries": formatted,
            "today": today,
        },
    )


@router.post("/one-rep-maxes/add", response_class=HTMLResponse)
def add_one_rep_max_view(
    request: Request,
    exercise: str = Form(...),
    weight_kg: float = Form(...),
    recorded_at: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    one_rep_max_service: OneRepMaxService = Depends(get_one_rep_max_service),
):
    """Add a 1rm entry (htmx)."""
    exercise = exercise.strip()
    if not one_rep_max_service.validate_exercise(exercise):
        raise HTTPException(status_code=422, detail=f"Unknown exercise: '{exercise}'.")
    if not (0 < weight_kg < 1000):
        raise HTTPException(status_code=400, detail="Weight must be between 0 and 1000 kg.")
    try:
        entry_date = date.fromisoformat(recorded_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format.")
    one_rep_max_service.add(
        user_id=session.user_id,
        exercise=exercise,
        weight_kg=weight_kg,
        recorded_at=entry_date,
    )

    raw = one_rep_max_service.get_all(session.user_id)
    entries = _format_1rm_entries(raw)
    return render(
        request,
        "partials/one_rep_max_history.html",
        {
            "entries": entries,
            "exercises_data_json": _build_exercises_chart_data(entries),
        },
    )


@router.delete("/one-rep-maxes/{entry_id}/delete", response_class=HTMLResponse)
def delete_one_rep_max_view(
    request: Request,
    entry_id: int,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,
    one_rep_max_service: OneRepMaxService = Depends(get_one_rep_max_service),
):
    """Delete a 1rm entry (htmx)."""
    one_rep_max_service.delete(session.user_id, entry_id)

    raw = one_rep_max_service.get_all(session.user_id)
    entries = _format_1rm_entries(raw)
    return render(
        request,
        "partials/one_rep_max_history.html",
        {
            "entries": entries,
            "exercises_data_json": _build_exercises_chart_data(entries),
        },
    )
