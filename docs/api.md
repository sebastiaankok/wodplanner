# WodApp API Documentation

Reverse-engineered API documentation for `ws.paynplan.nl` backend used by `app.wodapp.nl`.

## Base Configuration

- **Base URL**: `https://ws.paynplan.nl/`
- **Method**: All requests are `POST`
- **Content-Type**: `application/x-www-form-urlencoded`
- **Response Format**: JSON

## Common Parameters

All authenticated requests require these parameters:

| Parameter | Description |
|-----------|-------------|
| `data[app]` | Always `wodapp` |
| `data[language]` | Language code, e.g., `nl_NL` |
| `data[version]` | API version, e.g., `14.0` |
| `data[clientUserAgent]` | Client type, e.g., `browser` |
| `data[token]` | Auth token (from login response) |
| `data[id_appuser_li]` | User ID (from login response) |
| `data[id_gym]` | Gym ID |
| `data[idc]` | Company ID (same as gym ID) |

---

## Authentication

### Login

Authenticate a user and retrieve access token.

**Service**: `user`
**Method**: `login`

**Request Parameters**:
```
data[service]=user
data[method]=login
data[username]=<email>
data[pass]=<password>
data[gcl]=1
data[app]=wodapp
data[language]=nl_NL
data[version]=14.0
data[clientUserAgent]=browser
data[id_appuser_li]=
```

**Response**:
```json
{
  "status": "OK",
  "id_user": 388211,
  "id_appuser": 388211,
  "username": "user@example.com",
  "firstname": "Sebastiaan",
  "token": "40fff8ae77408d6f9aed4e72a60a354c",
  "gyms": [
    {
      "id_gym": 2495,
      "idc": 2495,
      "name": "CrossFit Purmerend",
      "city": "Purmerend"
    }
  ]
}
```

**Key Response Fields**:
- `token` - Use this for all subsequent authenticated requests
- `id_user` - User account ID; used as `id_appuser_li` in all subsequent requests
- `id_appuser` - App-user ID; may differ from `id_user`; matches `id_appuser` in `subscriptions.members[]`. Use this (not `id_user`) to detect whether the current user appears in a participant list. May be absent from the response — fall back to `id_user` if so.
- `gyms[].id_gym` - Gym ID for gym-specific requests

---

## Calendar / Schedule

### Get Day Schedule

Fetch all appointments for a specific date.

**Service**: `agenda`
**Method**: `day`

**Request Parameters**:
```
data[service]=agenda
data[method]=day
data[idc]=2495
data[type]=gym
data[id_agenda]=19488
data[dateInfo][date]=2026-04-15
data[token]=<token>
data[id_gym]=2495
data[id_appuser_li]=388211
```

**Response** (simplified):
```json
{
  "status": "OK",
  "resultset": [
    {
      "id_appointment": 5039978,
      "id_appointment_type": 574,
      "name": "CrossFit",
      "date_start": "2026-04-15 07:00:00",
      "date_end": "2026-04-15 08:00:00",
      "max_subscriptions": 17,
      "total_subscriptions": 11,
      "status": "open"
    }
  ]
}
```

**Appointment Status Values**:
- `open` - Spots available
- `closed` - Class is full
- `subscribed` - You are subscribed to this class

---

## Appointment Details

### Get Appointment Info

Get detailed info about an appointment **including participant list**.

**Service**: `agenda`
**Method**: `appointment`

**Request Parameters**:
```
data[service]=agenda
data[method]=appointment
data[idc]=2495
data[id_agenda]=19488
data[id]=5046413
data[date_start]=2026-04-19 11:00
data[date_end]=2026-04-19 12:00
data[token]=<token>
data[id_gym]=2495
data[id_appuser_li]=388211
```

**Response** (simplified):
```json
{
  "status": "OK",
  "resultset": {
    "id_appointment": 5046413,
    "name": "Olympic Lifting",
    "max_subscriptions": 17,
    "waiting_list": 1,
    "number_hours_before_subscription_opens": 168,
    "subscription_open_date": "12-04-2026 11:00",
    "subscribe_not_opened_yet": 0,
    "subscribe_closed": 0,
    "subscriptions": {
      "subscribed": 0,
      "total": 5,
      "full": 0,
      "members": [
        {
          "name": "Annika",
          "id_appuser": 353394,
          "imageURL": ""
        },
        {
          "name": "Jasper",
          "id_appuser": 364508,
          "imageURL": ""
        }
      ]
    },
    "waitinglist": {
      "total": 0,
      "members": []
    }
  }
}
```

**Key Fields for Your Features**:
- `subscriptions.members[]` - **List of people signed up** (for friends feature)
- `subscription_open_date` - Exact datetime when signup opens (shown in calendar)
- `subscribe_not_opened_yet` - `1` if signup hasn't opened yet
- `waiting_list` - `1` if waiting list is enabled

---

## Sign Up / Subscribe

### Subscribe to Appointment

Sign up for a class.

**Service**: `agenda`
**Method**: `subscribeAppointment`

**Request Parameters**:
```
data[service]=agenda
data[method]=subscribeAppointment
data[idc]=2495
data[id_agenda]=19488
data[id]=5046413
data[date_start_org]=2026-04-19 11:00
data[date_end_org]=2026-04-19 12:00
data[action]=subscribe
data[token]=<token>
data[id_gym]=2495
data[id_appuser_li]=388211
```

**Response**:
```json
{
  "status": "OK",
  "notice": "De inschrijving is succesvol\nEr is ingeschreven met abonnement",
  "subscribedWithSuccess": 1,
  "resultset": {
    "id_appointment": "5046413"
  }
}
```

### Subscribe to Waiting List

Join the waiting list when class is full.

**Service**: `agenda`
**Method**: `subscribeWaitingList`

**Request Parameters**:
```
data[service]=agenda
data[method]=subscribeWaitingList
data[idc]=2495
data[id_agenda]=19488
data[id]=5036777
data[date_start_org]=2026-04-19 10:00
data[date_end_org]=2026-04-19 11:00
data[action]=subscribe
data[token]=<token>
data[id_gym]=2495
data[id_appuser_li]=388211
```

**Response**:
```json
{
  "status": "OK",
  "notice": "Je bent ingeschreven voor de wachtlijst en wordt automatisch ingeschreven indien je aan de beurt komt",
  "resultset": {
    "id_appointment": "5036777"
  }
}
```

---

## Get Enabled Modules + Upcoming Reservations

Fetches gym modules and user widgets including upcoming reservations.

**Service**: `gym`
**Method**: `getModulesEnabledGym`

**Request Parameters**:
```
data[service]=gym
data[method]=getModulesEnabledGym
data[idc]=2495
data[id_gym]=2495
data[id_gym_group]=2495
data[gyms][0]=2495
data[companyImages]=0
data[numberOutstandingInvoices]=0
data[token]=<token>
data[id_appuser_li]=388211
```

**Response** (simplified):
```json
{
  "status": "OK",
  "widgets": {
    "reservations": {
      "enabled": 1,
      "data": [
        {
          "id_appointment": 5048373,
          "id_agenda": 19488,
          "name": "CrossFit",
          "date_start": "21-04-2026 16:30"
        },
        {
          "id_appointment": 5049539,
          "id_agenda": 19488,
          "name": "Strength Class",
          "date_start": "22-04-2026 18:30"
        }
      ]
    }
  }
}
```

**Key Fields**:
- `widgets.reservations.data[]` — upcoming classes the user is signed up for
- `date_start` — format `DD-MM-YYYY HH:MM` (note: day-first, unlike the `agenda.day` endpoint)
- `id_appointment` — same appointment ID used by other endpoints

---

## Other Endpoints

### Load Profile Image
- **Service**: `user`
- **Method**: `loadProfileImage`

### Get Agendas
- **Service**: `agenda`
- **Method**: `getAgendas`

### Initialize Settings
- **Service**: `agenda`
- **Method**: `initSettings`

---

## Implementation Notes

### Friends Feature

The `appointment` endpoint returns `subscriptions.members[]` with:
- `name` - First name of participant
- `id_appuser` - Unique app-user ID

**Strategy**:
1. Store a list of friend `id_appuser` values
2. For each day, fetch appointments using `day` method
3. Fetch all member lists in parallel via `ThreadPoolExecutor(max_workers=5)` in `services/calendar_view.py` — avoids N sequential round-trips; bounded concurrency to avoid rate-limiting upstream
4. Check if any friend's `id_appuser` is in `subscriptions.members[]`

**Self-detection**: the WodApp login response does **not** return the user's `id_appuser`; `id_user` and `id_appuser` are different values. Resolution strategy:

1. Prefer `session.appuser_id` (from login response `id_appuser`, reserved — likely stays `None`)
2. Fall back to `preferences.get_my_appuser_id(user_id)` — persisted after one-time discovery
3. On first-time discovery: match `member.name == session.firstname` against the participant list; accept **only if exactly one member matches** (ambiguous matches are skipped to avoid wrong self-assignment). Persist the matched `id_appuser` to `preferences` so subsequent loads use pure ID comparison.

Never compare against `session.user_id` for member identity — `id_user` is an account ID used for request auth (`id_appuser_li`), not the member/subscription ID.

**User-specific vs. cacheable data**:

| Data | API call | Cached? | Reason |
|------|----------|---------|--------|
| `Appointment.status` (`"subscribed"`) | `agenda.day` → `get_day_schedule()` | No — live per request | User-specific: reflects current user's subscription state |
| `AppointmentDetails.subscriptions.subscribed` | `agenda.appointment` → `get_appointment_details()` | No | User-specific |
| `subscriptions.members[]` | `agenda.appointment` → `get_appointment_members()` | Yes (TTL 600s) | Same for all users of the gym |
| `waitinglist.members[]` | `agenda.appointment` → `get_appointment_members()` | Yes (TTL 600s) | Same for all users of the gym |

Cache key: `{agenda_id}:{appointment_id}:{date_start}:{date_end}` — deliberately excludes `user_id` because the cached value is non-user-specific. A user's subscription status always comes from `get_day_schedule()`, called live with their own auth token.

- `get_appointment_members()` is the cache-aware entry point; `get_appointment_details()` always hits the API
- `people_modal_view` uses `get_appointment_details()` directly (correct — needs full user-specific detail)

---

## Google Calendar Sync

One-way sync: WodApp reservations → Google Calendar. Implemented in `services/calendar_sync.py`.

### Configuration

| Env var | Required | Notes |
|---------|----------|-------|
| `GOOGLE_CLIENT_ID` | Yes | OAuth 2.0 Web Application client ID from GCP |
| `GOOGLE_CLIENT_SECRET` | Yes | Corresponding client secret |
| `GOOGLE_REDIRECT_URI` | No | Default: `http://localhost:8000/google/callback`; set to your public URL in production |
| `GOOGLE_TOKEN_ENC_KEY` | No | Explicit Fernet key for token encryption; if unset, derived from `SECRET_KEY`. Set explicitly in production so key survives restarts. |

### OAuth flow

1. User visits `/google/connect` → redirect to Google OAuth consent screen
2. Google redirects back to `/google/callback` with `code`
3. App exchanges code for `access_token` + `refresh_token` (stored Fernet-encrypted in `google_accounts`)
4. WodApp `AuthSession` also stored encrypted in `google_accounts.wodapp_session_enc` for background sync
5. User selects a target calendar via `/google/calendars` → initial sync runs immediately

CSRF protection: `state` token signed with `itsdangerous.URLSafeTimedSerializer` (max_age 600 s), stored in `g_state` HttpOnly cookie.

### Sync engine (`calendar_sync.sync_user`)

Full diff on each run:

| Phase | Action |
|-------|--------|
| Insert | Reservations in WodApp not yet in `synced_events` → `gcal.insert_event` |
| Update | Reservation date or name changed → `gcal.update_event` |
| Delete | Future event in `synced_events` no longer in WodApp → `gcal.delete_event` + remove DB row |

**Safety rules**:
- Past events (already started) are never deleted — kept as calendar history.
- If the WodApp `get_upcoming_reservations` call fails, sync aborts without touching Google Calendar (no phantom deletes).
- Only events tracked in `synced_events` are ever modified — events the user created themselves are untouched, even on the primary calendar.

**Recovery**: if `synced_events` is empty but WodApp shows reservations, `_rebuild_from_google` scans the calendar for events tagged with the `wodplanner_appointment_id` private extended property and repopulates `synced_events` before the diff. Prevents duplicate inserts after a DB wipe.

Events are tagged with `extendedProperties.private.wodplanner_appointment_id = <id_appointment>` so recovery can identify WodPlanner-owned events.

### Sync triggers

| Trigger | Location |
|---------|----------|
| Manual "Sync Now" | `POST /google/sync` |
| Subscribe to class | `views.subscribe_view` → `BackgroundTasks` |
| Join waiting list | `views.waitinglist_view` → `BackgroundTasks` |
| Unsubscribe | `views.unsubscribe_view` → `BackgroundTasks` |
| Periodic | `main._periodic_sync_task` — every 30 min, all users with `sync_enabled=1` |

Periodic sync uses the stored encrypted `AuthSession` to reconstruct a `WodAppClient` without an active browser session. Per-user `asyncio.Lock` prevents overlapping syncs for the same user.

### Token management

Access tokens are refreshed automatically when within 5 minutes of expiry (`get_valid_token`). If refresh fails, sync is disabled (`sync_enabled=0`) and the user must reconnect.

---

## Your Account Info (from HAR)

- **User ID**: 388211
- **Gym ID**: 2495
- **Gym Name**: CrossFit Purmerend
- **Agenda ID**: 19488
