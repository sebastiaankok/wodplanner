# API Reference

## External API

Backend: `https://ws.paynplan.nl/` — see API.md for full docs. Key endpoints:
- `service=user, method=login` — returns token for auth
- `service=agenda, method=day` — day schedule
- `service=agenda, method=appointment` — details with participant list
- `service=agenda, method=subscribeAppointment` — sign up

## API Client

All WodApp API calls go through `WodAppClient`. Handles auth, maintains session state, returns Pydantic models. All requests are POST with form-encoded `data[key]=value` params.

## Auth Dependencies

- `get_session_from_cookie()` — returns AuthSession or None
- `require_session()` — raises 401 for API routes
- `require_session_for_view()` — redirects to /login for HTML views (HTMX-aware with HX-Redirect)
- `get_client_from_session()` — creates WodAppClient from session

Browser-based sessions stored in SQLite. Users log in at `/login`, session ID stored in HTTP-only cookie. `WodAppClient.from_session()` creates per-request clients from stored session data. No env vars needed for web users.

## Auto-Signup Flow

1. User queues class via POST /api/queue (stores token + user_id)
2. `QueueService` persists to SQLite with credentials
3. `SignupScheduler` schedules APScheduler job for `signup_opens_at + 2s`
4. Job creates client from stored token via `WodAppClient.from_session()`
5. Job executes `client.subscribe()`, falls back to waitlist if full
