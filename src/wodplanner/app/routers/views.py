"""HTML views for the web frontend."""

import hashlib
import io
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated

import markdown
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi import File as FastAPIFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from PIL import Image

from wodplanner.api.client import WodAppClient
from wodplanner.app.config import settings
from wodplanner.app.dependencies import (
    get_benchmark_service,
    get_client_from_session_for_view,
    get_friends_service,
    get_one_rep_max_service,
    get_preferences_service,
    get_schedule_service,
    get_session_from_cookie,
    get_subscription_service,
    get_subscription_tracker_service,
    require_session_for_view,
)
from wodplanner.models.auth import AuthSession
from wodplanner.services.benchmark import BenchmarkService, find_benchmark_in_schedule
from wodplanner.services.day_card import _find_benchmark, _has_1rm, build_day_cards
from wodplanner.services.friend_presence import find_friends_in_appointments
from wodplanner.services.friends import FriendsService
from wodplanner.services.one_rep_max import (
    OneRepMaxService,
    extract_1rm_exercises,
)
from wodplanner.services.preferences import PreferencesService
from wodplanner.services.schedule import ScheduleService
from wodplanner.services.schedule_lookup import match_schedule, match_schedules_for_date
from wodplanner.services.subscription import SubscribeAction, SubscriptionService
from wodplanner.services.subscription_tracker import SubscriptionTrackerService
from wodplanner.utils.dates import parse_api_datetime, parse_iso_date

logger = logging.getLogger(__name__)

# Class types that can be filtered
FILTERABLE_CLASS_TYPES = ["Open Gym", "CF101", "Teen Athlete", "HyCross", "CF Boxing", "Gymnastics", "Strength", "Small Group Strength Class"]


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


def _format_benchmark_entries(entries):
    return [
        {
            "id": e.id,
            "benchmark_name": e.benchmark_name,
            "time_seconds": e.time_seconds,
            "formatted_time": f"{e.time_seconds // 60}:{e.time_seconds % 60:02d}",
            "is_rx": e.is_rx,
            "recorded_at": e.recorded_at,
        }
        for e in entries
    ]


def _relative_time(dt: datetime) -> str:
    now = dt.tzinfo and datetime.now(dt.tzinfo) or datetime.now()
    diff = now - dt
    if diff.days < 0:
        return "just now"
    if diff.days == 0:
        hours = diff.seconds // 3600
        if hours == 0:
            minutes = diff.seconds // 60
            return "just now" if minutes < 1 else f"{minutes}m ago"
        return f"{hours}h ago"
    if diff.days == 1:
        return "yesterday"
    if diff.days < 30:
        return f"{diff.days}d ago"
    if diff.days < 365:
        months = diff.days // 30
        return f"{months}mo ago"
    years = diff.days // 365
    return f"{years}y ago"


_UPLOAD_DIR = settings.upload_dir / "avatars"
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


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


def _build_benchmark_chart_data(formatted_entries: list) -> str:
    data: dict[str, list] = {}
    for e in formatted_entries:
        name = e["benchmark_name"]
        if name not in data:
            data[name] = []
        data[name].append({
            "date": e["recorded_at"],
            "time": e["time_seconds"],
            "label": e["recorded_at"],
            "time_display": e["formatted_time"],
            "is_rx": e["is_rx"],
        })
    for name in data:
        data[name].sort(key=lambda x: x["date"])
    return json.dumps(data).replace("</", "<\\/")


def _ordered_by_recency(
    formatted_entries: list[dict], key: str
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for e in formatted_entries:
        name = e[key]
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


router = APIRouter(tags=["views"])

# Setup templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=templates_dir)

_css_path = templates_dir.parent / "static" / "css" / "style.css"
try:
    templates.env.globals["css_version"] = hashlib.md5(_css_path.read_bytes()).hexdigest()[:8]
except Exception:
    templates.env.globals["css_version"] = "1"

try:
    templates.env.globals["app_version"] = settings.app_version
except Exception:
    templates.env.globals["app_version"] = "unknown"


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


@router.get("/changelog", response_class=HTMLResponse)
def changelog_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
):
    """Render the CHANGELOG.md as an HTML page."""
    repo_root = Path(__file__).parent.parent.parent.parent.parent
    changelog_path = repo_root / "CHANGELOG.md"
    try:
        raw = changelog_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = "# Changelog\n\nChangelog file not found."
    html_content = markdown.markdown(
        raw,
        extensions=["fenced_code", "codehilite"],
    )
    return render(request, "changelog.html", {"changelog_html": html_content, **get_user_context(session)})


@router.get("/", response_class=HTMLResponse)
def home_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    tracker: SubscriptionTrackerService = Depends(get_subscription_tracker_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
):
    """Homepage showing upcoming reservations and weekly stats."""
    reservations, company_images = client.get_upcoming_reservations()

    benchmark_names = benchmark_service.get_benchmark_list()

    # Group by date for display
    days: dict[str, list[dict]] = {}
    date_schedule_cache: dict = {}

    for r in reservations:
        day_key = r.date_start.strftime("%Y-%m-%d")
        schedule_date = r.date_start.date()

        if schedule_date not in date_schedule_cache:
            date_schedule_cache[schedule_date] = match_schedules_for_date(
                schedule_date, session.gym_id, schedule_service
            )

        schedule_by_type = date_schedule_cache[schedule_date]
        has_1rm = _has_1rm(r.name, schedule_by_type)
        benchmark_name = _find_benchmark(r.name, schedule_by_type, benchmark_names)

        if day_key not in days:
            days[day_key] = []
        days[day_key].append({
            "id": r.id_appointment,
            "name": r.name,
            "time": r.date_start.strftime("%H:%M"),
            "weekday": r.date_start.strftime("%A"),
            "display_date": r.date_start.strftime("%b %d").replace(" 0", " "),
            "date_start": r.date_start.strftime("%Y-%m-%d %H:%M"),
            "date_end": r.date_end.strftime("%Y-%m-%d %H:%M") if r.date_end else r.date_start.strftime("%Y-%m-%d %H:%M"),
            "has_1rm": has_1rm,
            "has_benchmark": benchmark_name is not None,
            "benchmark_name": benchmark_name,
        })

    # Weekly stats (skip if tracking disabled)
    user_id = session.user_id
    has_data = False
    chart_data: dict[str, list] = {"weeks": [], "past": [], "future": []}
    week_stats = {"past": 0, "future": 0}
    average = 0.0
    weeks_tracked = 0

    if not prefs_service.is_tracking_disabled(user_id):
        has_data = tracker.has_any_events(user_id)
        if has_data:
            weekly = tracker.get_weekly_counts(user_id)
            chart_data = {
                "weeks": [w["week_start"] for w in weekly],
                "past": [w["past"] for w in weekly],
                "future": [w["future"] for w in weekly],
            }
            week_stats = tracker.get_current_week_stats(user_id)
            average = round(tracker.get_average_per_week(user_id), 1)
            weeks_tracked = tracker.get_weeks_tracked(user_id)

    return render(
        request,
        "home.html",
        {
            "active_page": "home",
            "days": days,
            "gym_logo": company_images.get("logo", ""),
            "has_chart_data": has_data,
            "chart_data": json.dumps(chart_data).replace("</", "<\\/"),
            "week_stats": week_stats,
            "average": average,
            "weeks_tracked": weeks_tracked,
            **get_user_context(session),
        },
    )


_TOOLTIP_SEQUENCE = ["filter", "today", "date_picker", "friends", "schedule"]
_HEADER_TOOLTIPS = {"filter", "today", "date_picker"}


def _get_tooltip_context(dismissed: set, appt_data: list) -> dict:
    active = next((t for t in _TOOLTIP_SEQUENCE if t not in dismissed), None)
    any_has_1rm = any(a.has_1rm for a in appt_data)
    any_has_benchmark = any(a.has_benchmark for a in appt_data)
    show_1rm = "1rm" not in dismissed and any_has_1rm
    show_benchmark = "benchmark" not in dismissed and any_has_benchmark
    return {
        "active_tooltip": active,
        "show_1rm_tooltip": show_1rm,
        "show_benchmark_tooltip": show_benchmark,
        "show_backdrop": active in _HEADER_TOOLTIPS,
    }


def _fetch_calendar_data(
    session: AuthSession,
    target_date: date,
    client: WodAppClient,
    friends_service: FriendsService,
    schedule_service: ScheduleService,
    benchmark_service: BenchmarkService,
    hidden_types: set[str],
) -> list:
    """Fetch appointment data and build DayCard objects for calendar rendering."""
    appointments = client.get_day_schedule(target_date)

    friends = friends_service.get_all(session.user_id)
    friends_by_appt = find_friends_in_appointments(appointments, friends, client) or {}

    visible = [
        a for a in appointments
        if a.name not in hidden_types
        or (friends_by_appt.get(a.id_appointment) or [])
    ]

    schedule_map = match_schedules_for_date(
        target_date, gym_id=session.gym_id, schedule_service=schedule_service
    )

    benchmark_names = benchmark_service.get_benchmark_list()

    return build_day_cards(
        appointments=visible,
        friends_by_appt_id=friends_by_appt,
        schedule_by_class_type=schedule_map,
        now=datetime.now(),
        benchmark_names=benchmark_names,
        calendar_date=target_date,
    )


@router.get("/calendar", response_class=HTMLResponse)
def calendar_page(
    request: Request,
    day: str | None = None,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
):
    """Main calendar page."""
    target_date = parse_iso_date(day) if day else date.today()
    prev_date = (target_date - timedelta(days=1)).isoformat()
    next_date = (target_date + timedelta(days=1)).isoformat()

    hidden_types = prefs_service.get_hidden_class_types(session.user_id)
    dismissed = set(prefs_service.get_dismissed_tooltips(session.user_id))
    appt_data = _fetch_calendar_data(session, target_date, client, friends_service, schedule_service, benchmark_service, set(hidden_types))

    reservations, _ = client.get_upcoming_reservations()
    reservation_dates = sorted({r.date_start.strftime("%Y-%m-%d") for r in reservations})

    weekday = target_date.strftime("%A")
    filters = [{"name": t, "hidden": t in hidden_types} for t in FILTERABLE_CLASS_TYPES]

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
            "reservation_dates": reservation_dates,
            **_get_tooltip_context(dismissed, appt_data),
            **get_user_context(session),
        },
    )


@router.get("/calendar/{day}", response_class=HTMLResponse)
def calendar_day_partial(
    request: Request,
    day: str,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
):
    """Calendar day partial for htmx updates."""
    target_date = parse_iso_date(day)
    prev_date = (target_date - timedelta(days=1)).isoformat()
    next_date = (target_date + timedelta(days=1)).isoformat()

    hidden_types = prefs_service.get_hidden_class_types(session.user_id)
    dismissed = set(prefs_service.get_dismissed_tooltips(session.user_id))
    appt_data = _fetch_calendar_data(session, target_date, client, friends_service, schedule_service, benchmark_service, set(hidden_types))

    reservations, _ = client.get_upcoming_reservations()
    reservation_dates = sorted({r.date_start.strftime("%Y-%m-%d") for r in reservations})

    weekday = target_date.strftime("%A")
    filters = [{"name": t, "hidden": t in hidden_types} for t in FILTERABLE_CLASS_TYPES]

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
            "reservation_dates": reservation_dates,
            **_get_tooltip_context(dismissed, appt_data),
        },
    )


@router.post("/filters/toggle/{class_type}", response_class=HTMLResponse)
def toggle_filter(
    request: Request,
    class_type: str,
    current_date: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
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
        benchmark_service=benchmark_service,
    )


@router.post("/tooltips/dismiss/{tooltip_id}", response_class=HTMLResponse)
def dismiss_tooltip(
    tooltip_id: str,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Dismiss a tooltip and persist the state."""
    prefs_service.dismiss_tooltip(session.user_id, tooltip_id)
    return HTMLResponse("")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Settings page."""
    hidden_types = prefs_service.get_hidden_class_types(session.user_id)
    filters = [{"name": t, "hidden": t in hidden_types} for t in FILTERABLE_CLASS_TYPES]
    tracking_disabled = prefs_service.is_tracking_disabled(session.user_id)
    return render(
        request,
        "settings.html",
        {
            "active_page": "",
            "filters": filters,
            "tracking_disabled": tracking_disabled,
            **get_user_context(session),
        },
    )


@router.post("/settings/reset-tutorial", response_class=HTMLResponse)
def reset_tutorial(
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Reset all dismissed tooltips."""
    prefs_service.reset_tooltips(session.user_id)
    return HTMLResponse('<p class="success-msg">Tutorial will show again on your next visit.</p>')


@router.post("/settings/toggle-filter/{class_type}", response_class=HTMLResponse)
def settings_toggle_filter(
    request: Request,
    class_type: str,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Toggle a class type filter from the settings page."""
    prefs_service.toggle_hidden_class_type(session.user_id, class_type)
    hidden_types = prefs_service.get_hidden_class_types(session.user_id)
    filters = [{"name": t, "hidden": t in hidden_types} for t in FILTERABLE_CLASS_TYPES]
    return render(request, "partials/settings_filters.html", {"filters": filters})


@router.post("/settings/toggle-tracking", response_class=HTMLResponse)
def toggle_tracking(
    request: Request,
    enable: str = Form("true"),
    delete_data: str = Form("false"),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    prefs_service: PreferencesService = Depends(get_preferences_service),
    tracker: SubscriptionTrackerService = Depends(get_subscription_tracker_service),
):
    """Enable or disable session tracking."""
    disabled = enable != "true"
    prefs_service.set_tracking_disabled(session.user_id, disabled)

    if delete_data == "true":
        tracker.delete_all_for_user(session.user_id)

    return HTMLResponse("")


@router.post("/settings/delete-tracking-data", response_class=HTMLResponse)
def delete_tracking_data(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    tracker: SubscriptionTrackerService = Depends(get_subscription_tracker_service),
):
    """Delete all tracking data for the current user."""
    tracker.delete_all_for_user(session.user_id)
    return HTMLResponse('<p class="success-msg">Tracking data deleted.</p>')


@router.get("/1rm", response_class=HTMLResponse)
def one_rep_max_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    one_rep_max_service: OneRepMaxService = Depends(get_one_rep_max_service),
):
    """1RM tracking page."""
    raw = one_rep_max_service.get_all(session.user_id)
    past_exercises = one_rep_max_service.get_exercises(session.user_id)
    exercises = one_rep_max_service.get_exercise_list()
    entries = _format_1rm_entries(raw)
    exercises_by_recency = _ordered_by_recency(entries, "exercise")

    return render(
        request,
        "one_rep_max.html",
        {
            "active_page": "1rm",
            "exercises": exercises,
            "past_exercises": past_exercises,
            "default_exercise": entries[0]["exercise"] if entries else "",
            "entries": entries,
            "exercises_by_recency": exercises_by_recency,
            "exercises_data_json": _build_exercises_chart_data(entries),
            "today": date.today().isoformat(),
            **get_user_context(session),
        },
    )


@router.get("/benchmark", response_class=HTMLResponse)
def benchmark_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
):
    """Benchmark tracking page."""
    raw = benchmark_service.get_all_results(session.user_id)
    entries = _format_benchmark_entries(raw)
    benchmarks_by_recency = _ordered_by_recency(entries, "benchmark_name")
    benchmark_list = benchmark_service.get_benchmark_list()

    return render(
        request,
        "benchmark.html",
        {
            "active_page": "benchmark",
            "benchmark_list": benchmark_list,
            "entries": entries,
            "benchmarks_by_recency": benchmarks_by_recency,
            "benchmark_data_json": _build_benchmark_chart_data(entries),
            "today": date.today().isoformat(),
            **get_user_context(session),
        },
    )


@router.get("/friends", response_class=HTMLResponse)
def friends_page(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Friends management page."""
    friends = friends_service.get_all(session.user_id)
    friend_user_ids = [f.appuser_id for f in friends]
    avatar_map = prefs_service.get_avatar_filenames(friend_user_ids)
    my_avatar = prefs_service.get_avatar_filename(session.user_id)

    friends_data = [
        {
            "id": f.id,
            "appuser_id": f.appuser_id,
            "name": f.name,
            "added_at": f.added_at.isoformat() if f.added_at else "",
            "added_ago": _relative_time(f.added_at) if f.added_at else "",
            "avatar": avatar_map.get(f.appuser_id),
        }
        for f in friends
    ]

    return render(
        request,
        "friends.html",
        {
            "active_page": "friends",
            "friends": friends_data,
            "friend_count": len(friends_data),
            "my_avatar": my_avatar,
            **get_user_context(session),
        },
    )


@router.post("/friends/add", response_class=HTMLResponse)
def add_friend_view(
    request: Request,
    appuser_id: int = Form(...),
    name: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Add a friend (htmx form submission)."""
    friends_service.add(session.user_id, appuser_id, name)
    friends = friends_service.get_all(session.user_id)
    friend_user_ids = [f.appuser_id for f in friends]
    avatar_map = prefs_service.get_avatar_filenames(friend_user_ids)

    friends_data = [
        {
            "id": f.id,
            "appuser_id": f.appuser_id,
            "name": f.name,
            "added_at": f.added_at.isoformat() if f.added_at else "",
            "added_ago": _relative_time(f.added_at) if f.added_at else "",
            "avatar": avatar_map.get(f.appuser_id),
        }
        for f in friends
    ]

    return render(request, "partials/friends_list.html", {"friends": friends_data})


@router.delete("/friends/{friend_id}/delete", response_class=HTMLResponse)
def delete_friend_view(
    request: Request,
    friend_id: int,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Delete a friend (htmx)."""
    friends_service.delete(session.user_id, friend_id)
    friends = friends_service.get_all(session.user_id)
    friend_user_ids = [f.appuser_id for f in friends]
    avatar_map = prefs_service.get_avatar_filenames(friend_user_ids)

    friends_data = [
        {
            "id": f.id,
            "appuser_id": f.appuser_id,
            "name": f.name,
            "added_at": f.added_at.isoformat() if f.added_at else "",
            "added_ago": _relative_time(f.added_at) if f.added_at else "",
            "avatar": avatar_map.get(f.appuser_id),
        }
        for f in friends
    ]

    return render(request, "partials/friends_list.html", {"friends": friends_data})


@router.post("/avatar/upload", response_class=RedirectResponse)
def upload_avatar(
    request: Request,
    avatar: UploadFile = FastAPIFile(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    ext = Path(avatar.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file type")

    contents = avatar.file.read(_MAX_UPLOAD_SIZE + 1)
    if len(contents) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")

    try:
        img = Image.open(io.BytesIO(contents))
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")

    # format is set by Image.open; still accessible after verify()
    fmt = img.format
    if fmt == "JPEG":
        ext = ".jpg"
    elif fmt == "PNG":
        ext = ".png"
    elif fmt == "GIF":
        ext = ".gif"
    elif fmt == "WEBP":
        ext = ".webp"
    else:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    filename = f"avatar_{session.user_id}{ext}"
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def _remove_old(user_id: int) -> None:
        for old_ext in _ALLOWED_EXTENSIONS:
            old_path = _UPLOAD_DIR / f"avatar_{user_id}{old_ext}"
            if old_path.exists():
                old_path.unlink()
                return
    _remove_old(session.user_id)
    if session.appuser_id and session.appuser_id != session.user_id:
        _remove_old(session.appuser_id)

    filepath = _UPLOAD_DIR / filename
    # Re-encode to strip EXIF/metadata and any embedded payloads
    img = Image.open(io.BytesIO(contents))
    img.save(filepath, format=fmt)

    prefs_service.set_avatar_filename(session.user_id, filename)
    if session.appuser_id and session.appuser_id != session.user_id:
        prefs_service.set_avatar_filename(session.appuser_id, filename)
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/appointments/{appointment_id}/subscribe", response_class=HTMLResponse)
def subscribe_view(
    request: Request,
    appointment_id: int,
    date_start: str = Form(...),
    date_end: str = Form(...),
    class_name: str = Form(""),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
    tracker: SubscriptionTrackerService = Depends(get_subscription_tracker_service),
):
    """Subscribe to appointment from calendar (htmx)."""
    start = parse_api_datetime(date_start)
    end = parse_api_datetime(date_end)

    result = subscription_service.act(
        appointment_id=appointment_id,
        start=start,
        end=end,
        action=SubscribeAction.SUBSCRIBE,
    )

    if result.subscribedWithSuccess and not prefs_service.is_tracking_disabled(session.user_id):
        tracker.record_subscribe(
            user_id=session.user_id,
            appointment_id=appointment_id,
            class_name=class_name,
            class_date=start.date(),
            class_end=end,
        )

    # Return updated calendar
    return calendar_day_partial(
        request=request,
        day=start.date().isoformat(),
        session=session,
        client=client,
        friends_service=friends_service,
        prefs_service=prefs_service,
        schedule_service=schedule_service,
        benchmark_service=benchmark_service,
    )


@router.post("/appointments/{appointment_id}/waitinglist", response_class=HTMLResponse)
def waitinglist_view(
    request: Request,
    appointment_id: int,
    date_start: str = Form(...),
    date_end: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
):
    """Join waiting list from calendar (htmx)."""
    start = parse_api_datetime(date_start)
    end = parse_api_datetime(date_end)

    subscription_service.act(
        appointment_id=appointment_id,
        start=start,
        end=end,
        action=SubscribeAction.WAITLIST,
    )

    # Return updated calendar
    return calendar_day_partial(
        request=request,
        day=start.date().isoformat(),
        session=session,
        client=client,
        friends_service=friends_service,
        prefs_service=prefs_service,
        schedule_service=schedule_service,
        benchmark_service=benchmark_service,
    )


@router.post("/appointments/{appointment_id}/unsubscribe", response_class=HTMLResponse)
def unsubscribe_view(
    request: Request,
    appointment_id: int,
    date_start: str = Form(...),
    date_end: str = Form(...),
    is_waitinglist: str = Form("false"),
    class_name: str = Form(""),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
    tracker: SubscriptionTrackerService = Depends(get_subscription_tracker_service),
):
    """Unsubscribe from appointment (htmx)."""
    start = parse_api_datetime(date_start)
    end = parse_api_datetime(date_end)

    action = (
        SubscribeAction.UNSUBSCRIBE_WAITLIST
        if is_waitinglist == "true"
        else SubscribeAction.UNSUBSCRIBE
    )

    result = subscription_service.act(
        appointment_id=appointment_id,
        start=start,
        end=end,
        action=action,
    )

    if result.subscribedWithSuccess and is_waitinglist != "true" and not prefs_service.is_tracking_disabled(session.user_id):
        tracker.record_unsubscribe(
            user_id=session.user_id,
            appointment_id=appointment_id,
            class_name=class_name,
            class_date=start.date(),
            class_end=end,
        )

    # Return updated calendar
    return calendar_day_partial(
        request=request,
        day=start.date().isoformat(),
        session=session,
        client=client,
        friends_service=friends_service,
        prefs_service=prefs_service,
        schedule_service=schedule_service,
        benchmark_service=benchmark_service,
    )


@router.get("/appointments/{appointment_id}/people", response_class=HTMLResponse)
def people_modal_view(
    request: Request,
    appointment_id: int,
    date_start: str,
    date_end: str,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
):
    """Get participants for an appointment (htmx modal)."""
    start = parse_api_datetime(date_start)
    end = parse_api_datetime(date_end)

    details = client.get_appointment_details(appointment_id, start, end)
    friend_ids = friends_service.get_appuser_ids(session.user_id)
    members = details.subscriptions.members

    # Resolve current user's id_appuser: prefer session, then stored pref, then
    # one-time name-match discovery (only when exactly one member matches, to
    # avoid wrong self-assignment on name collision).
    current_appuser_id = session.appuser_id or prefs_service.get_my_appuser_id(session.user_id)
    if not current_appuser_id:
        name_matches = [m for m in members if m.name == session.firstname]
        if len(name_matches) == 1:
            current_appuser_id = name_matches[0].id_appuser
            prefs_service.set_my_appuser_id(session.user_id, current_appuser_id)

    participants = []
    all_user_ids = [m.id_appuser for m in members]
    avatar_map = prefs_service.get_avatar_filenames(all_user_ids)
    # Current user's avatar is stored under session.user_id, not appuser_id
    if current_appuser_id and current_appuser_id not in avatar_map:
        my_avatar = prefs_service.get_avatar_filename(session.user_id)
        if my_avatar:
            avatar_map[current_appuser_id] = my_avatar
    for member in members:
        participants.append({
            "id": member.id_appuser,
            "name": member.name,
            "is_friend": member.id_appuser in friend_ids,
            "is_self": member.id_appuser == current_appuser_id,
            "avatar": avatar_map.get(member.id_appuser),
        })

    # Sort: self first, then friends, then alphabetically
    participants.sort(key=lambda p: (not p["is_self"], not p["is_friend"], str(p["name"]).lower()))

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
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    friends_service: FriendsService = Depends(get_friends_service),
    prefs_service: PreferencesService = Depends(get_preferences_service),
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
        prefs_service=prefs_service,
    )


@router.get("/appointments/{appointment_id}/schedule", response_class=HTMLResponse)
def schedule_modal_view(
    request: Request,
    appointment_id: int,
    date_start: str,
    class_name: str,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    schedule_service: ScheduleService = Depends(get_schedule_service),
):
    """Get workout schedule for an appointment (htmx modal)."""
    # Parse date from date_start (format: "YYYY-MM-DD HH:MM")
    schedule_date = parse_iso_date(date_start.split(" ")[0])

    # Look up schedule by date and class name
    schedule = match_schedule(class_name, schedule_date, gym_id=session.gym_id, schedule_service=schedule_service)

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
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    schedule_service: ScheduleService = Depends(get_schedule_service),
    one_rep_max_service: OneRepMaxService = Depends(get_one_rep_max_service),
):
    """Get 1rm tracker modal for an appointment (htmx modal)."""
    schedule_date = parse_iso_date(date_start.split(" ")[0])
    schedule = match_schedule(class_name, schedule_date, gym_id=session.gym_id, schedule_service=schedule_service)

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

    formatted = _format_1rm_entries(raw)

    default_exercise = suggested_exercises[0] if suggested_exercises else (formatted[0]["exercise"] if formatted else "")

    return render(
        request,
        "partials/one_rep_max_modal.html",
        {
            "suggested_exercises": suggested_exercises,
            "exercises": exercises,
            "entries": formatted,
            "default_exercise": default_exercise,
            "today": today,
            "show_date": False,
            "preset_date": schedule_date.isoformat(),
            "exercises_data_json": _build_exercises_chart_data(formatted),
        },
    )


@router.post("/one-rep-maxes/add", response_class=HTMLResponse)
def add_one_rep_max_view(
    request: Request,
    exercise: str = Form(...),
    weight_kg: float = Form(...),
    recorded_at: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    one_rep_max_service: OneRepMaxService = Depends(get_one_rep_max_service),
):
    """Add a 1rm entry (htmx)."""
    exercise = exercise.strip()
    if not one_rep_max_service.validate_exercise(exercise):
        raise HTTPException(status_code=422, detail=f"Unknown exercise: '{exercise}'.")
    if not (0 < weight_kg < 1000):
        raise HTTPException(status_code=400, detail="Weight must be between 0 and 1000 kg.")
    try:
        entry_date = parse_iso_date(recorded_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format.")

    prev_max = one_rep_max_service.get_max_for_exercise(session.user_id, exercise)
    is_pr = prev_max is not None and weight_kg > prev_max

    one_rep_max_service.add(
        user_id=session.user_id,
        exercise=exercise,
        weight_kg=weight_kg,
        recorded_at=entry_date,
    )

    raw = one_rep_max_service.get_all(session.user_id)
    entries = _format_1rm_entries(raw)
    resp = render(
        request,
        "partials/one_rep_max_history.html",
        {
            "entries": entries,
            "exercises_data_json": _build_exercises_chart_data(entries),
        },
    )
    if is_pr:
        resp.headers["HX-Trigger"] = "pr-celebration"
    return resp


@router.delete("/one-rep-maxes/{entry_id}/delete", response_class=HTMLResponse)
def delete_one_rep_max_view(
    request: Request,
    entry_id: int,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
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


@router.get("/appointments/{appointment_id}/benchmark", response_class=HTMLResponse)
def benchmark_modal_view(
    request: Request,
    appointment_id: int,
    date_start: str,
    class_name: str,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    schedule_service: ScheduleService = Depends(get_schedule_service),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
):
    """Get benchmark result modal for an appointment (htmx modal)."""
    schedule_date = parse_iso_date(date_start.split(" ")[0])
    schedule = match_schedule(class_name, schedule_date, gym_id=session.gym_id, schedule_service=schedule_service)

    benchmark_names = benchmark_service.get_benchmark_list()
    lower_class = class_name.lower()
    benchmark_name = next((n for n in benchmark_names if n.lower() == lower_class), None)

    if not benchmark_name and schedule:
        texts = [
            getattr(schedule, "warmup_mobility", None),
            getattr(schedule, "strength_specialty", None),
            getattr(schedule, "metcon", None),
            getattr(schedule, "raw_content", None),
        ]
        benchmark_name = find_benchmark_in_schedule(texts, benchmark_names)

    if not benchmark_name:
        raise HTTPException(status_code=404, detail="No benchmark WOD detected for this appointment")

    raw = benchmark_service.get_results_for_benchmark(session.user_id, benchmark_name)
    entries = _format_benchmark_entries(raw)

    return render(
        request,
        "partials/benchmark_modal.html",
        {
            "benchmark_name": benchmark_name,
            "entries": entries,
            "preset_date": schedule_date.isoformat(),
        },
    )


@router.post("/benchmark-results/add", response_class=HTMLResponse)
def add_benchmark_result_view(
    request: Request,
    benchmark_name: str = Form(...),
    minutes: int = Form(...),
    seconds: int = Form(...),
    is_rx: str = Form("true"),
    recorded_at: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
):
    """Add a benchmark result (htmx)."""
    total_seconds = minutes * 60 + seconds
    if total_seconds <= 0:
        raise HTTPException(status_code=400, detail="Time must be greater than 0.")

    benchmark_service.add_result(
        user_id=session.user_id,
        benchmark_name=benchmark_name.strip(),
        time_seconds=total_seconds,
        is_rx=is_rx == "true",
        recorded_at=recorded_at,
    )

    raw = benchmark_service.get_all_results(session.user_id)
    entries = _format_benchmark_entries(raw)
    return render(
        request,
        "partials/benchmark_history.html",
        {
            "entries": entries,
            "benchmark_data_json": _build_benchmark_chart_data(entries),
        },
    )


@router.delete("/benchmark-results/{result_id}/delete", response_class=HTMLResponse)
def delete_benchmark_result_view(
    request: Request,
    result_id: int,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
):
    """Delete a benchmark result (htmx)."""
    benchmark_service.delete_result(session.user_id, result_id)

    raw = benchmark_service.get_all_results(session.user_id)
    entries = _format_benchmark_entries(raw)
    return render(
        request,
        "partials/benchmark_history.html",
        {
            "entries": entries,
            "benchmark_data_json": _build_benchmark_chart_data(entries),
        },
    )
