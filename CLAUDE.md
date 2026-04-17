# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WodPlanner is a custom frontend for WodApp (app.wodapp.nl), a CrossFit class scheduling app. It wraps the reverse-engineered `ws.paynplan.nl` API to provide:
- **Auto-signup queue**: Schedule signups for classes that open 7 days in advance
- **Friends tracking**: See which friends are signed up for classes
- **Browser-based authentication**: Users log in with their WodApp credentials

## Commands

```bash
# Install (with API server support)
pip install -e ".[api]"

# Run server
uvicorn wodplanner.app.main:app --reload

# Run tests
pytest

# Import workout schedule from PDF (--dry-run to preview)
import-schedule schedule.pdf --year 2026
import-schedule schedule.pdf --year 2026 --dry-run
```

## Architecture

```
src/wodplanner/
├── api/client.py          # WodApp API client (ws.paynplan.nl)
├── app/                   # FastAPI application
│   ├── main.py            # App entry point with lifespan (starts scheduler)
│   ├── config.py          # Settings (session expiry, cookie config)
│   ├── dependencies.py    # Session-based auth dependencies
│   ├── routers/           # API endpoints (prefixed /api) and views
│   └── templates/         # Jinja2 HTML templates with HTMX
├── cli/import_schedule.py # PDF parser for workout schedules
├── models/                # Pydantic models
└── services/
    ├── session.py         # Browser session storage (SQLite)
    ├── scheduler.py       # APScheduler-based auto-signup executor
    ├── queue.py           # SQLite queue persistence
    ├── schedule.py        # Workout schedule storage + class name mapping
    └── friends.py         # Friends list persistence
```

### Key Patterns

**Authentication**: Browser-based sessions stored in SQLite. Users log in at `/login`, session ID stored in HTTP-only cookie. `WodAppClient.from_session()` creates per-request clients from stored session data. No env vars needed for web users.

**Auth Dependencies**:
- `get_session_from_cookie()` - Returns AuthSession or None
- `require_session()` - Raises 401 for API routes
- `require_session_for_view()` - Redirects to /login for HTML views (HTMX-aware with HX-Redirect)
- `get_client_from_session()` - Creates WodAppClient from session

**API Client**: All WodApp API calls go through `WodAppClient`. It handles auth, maintains session state, and returns Pydantic models. All requests are POST with form-encoded `data[key]=value` params.

**Auto-Signup Flow**:
1. User queues a class via POST /api/queue (stores user's token + user_id)
2. `QueueService` persists to SQLite with credentials
3. `SignupScheduler` schedules APScheduler job for `signup_opens_at + 2s`
4. Job creates client from stored token via `WodAppClient.from_session()`
5. Job executes `client.subscribe()`, falls back to waitlist if full

**Frontend**: Server-rendered HTML with HTMX. Views router serves pages, API routers handle data. Templates use partials for HTMX swaps. Login page is standalone (no base.html navbar). Single CSS file: `app/static/css/style.css`. Mobile breakpoint: `640px`.

**OOB swap gotcha**: `calendar.html` and `partials/calendar_day.html` both contain the date-nav and filters HTML. `calendar_day.html` replaces them via `hx-swap-oob="true"` on every navigation/filter change. Any change to date-nav or filters HTML must be made in **both files**.

**Schedule Import**: The `import-schedule` CLI parses CrossFit Purmerend PDF schedules (Dutch format) using pdfplumber. Extracts workout details per class type: warmup/mobility, strength/specialty, and metcon. Stored in `schedules` table with `(date, class_type)` unique constraint. Class names are normalized via `CLASS_NAME_MAPPING` in `services/schedule.py` to match API appointment names (e.g., "CF101" → "CrossFit 101").

## External API

Backend: `https://ws.paynplan.nl/` - See API.md for full documentation. Key endpoints:
- `service=user, method=login` - Returns token for auth
- `service=agenda, method=day` - Day schedule
- `service=agenda, method=appointment` - Details with participant list
- `service=agenda, method=subscribeAppointment` - Sign up

## Database

SQLite (`wodplanner.db`) with tables: `signup_queue`, `friends`, `preferences`, `schedules`, `sessions`. Schema auto-created on first run.

**sessions table**: `session_id` (cookie value), `token`, `user_id`, `username`, `firstname`, `gym_id`, `gym_name`, `agenda_id`, `created_at`, `expires_at`

**signup_queue**: Includes `user_token` and `user_id` columns for scheduled jobs to authenticate.

## Configuration

Environment variables (all optional for web usage):
- `SESSION_EXPIRE_DAYS` - Session lifetime (default: 7)
- `COOKIE_SECURE` - Set true for HTTPS in production (default: false)
- `WODAPP_USERNAME` / `WODAPP_PASSWORD` - Only needed for CLI tools, not web
