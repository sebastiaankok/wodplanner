# Testing

## Running locally

```bash
# Unit tests (fast, no browser)
pytest

# With coverage report
pytest --cov=wodplanner --cov-report=term-missing

# Specific file or test
pytest tests/services/test_schedule.py
pytest tests/services/test_schedule.py::TestScheduleService::test_upsert_updates_existing

# E2E browser tests (requires Playwright Chromium)
pytest tests/e2e/ --browser chromium

# E2E headed + slow motion (visual sanity check)
pytest tests/e2e/ --browser chromium --headed --slowmo 500

# Lint
ruff check .

# Type check (basic — not strict)
mypy src/
```

Current coverage: **98%** across 409 unit tests + 33 E2E tests.

### First-time Playwright setup

```bash
pip install -e ".[api,dev]"
playwright install chromium
```

## CI

`.github/workflows/ci.yml` runs on every push: `ruff check .` then `pytest`. Uses Python 3.12 with pip caching. Docker build is a separate workflow (`docker.yml`, runs on `main` and version tags only).

To add E2E to CI:

```yaml
- run: pip install -e ".[api,dev]"
- run: playwright install --with-deps chromium
- run: pytest tests/e2e/ --browser chromium
```

## Test structure

```
tests/
├── conftest.py                          # shared db_path / clean_registry fixtures
├── e2e/
│   ├── conftest.py                      # live_server, mock_wodapp_client, authed_context, page
│   ├── test_login.py                    # redirect, bad creds, rate limiter
│   ├── test_calendar_nav.py             # HTMX date nav, OOB swap sync (#date-nav, #filters)
│   ├── test_filters.py                  # toggleFilters() JS, filter POST persistence
│   ├── test_appointment_actions.py      # subscribe → calendar refresh, people modal
│   ├── test_modals.py                   # schedule/people modal open/close
│   ├── test_one_rep_max.py              # log form toggle, add/delete entry
│   ├── test_friends.py                  # delete flow, per-user scoping
│   └── test_mobile.py                   # iPhone viewport, responsive layout
├── api/
│   ├── test_client.py                   # WodAppClient happy paths + cache
│   └── test_client_retry.py             # 502/503 retries, transport errors, status != OK
├── app/
│   ├── conftest.py                      # FastAPI fixtures (app_client, session_cookie, ...)
│   ├── test_main.py                     # exception handlers, middleware, /health, lifespan
│   ├── test_config.py
│   ├── test_dependencies.py             # _get_db_path, get_api_cache_service
│   ├── test_dependencies_full.py        # require_session*, get_session_from_cookie, factories
│   └── routers/
│       ├── test_auth.py                 # /me, /login (success/bad/rate-limited/error), /logout
│       ├── test_friends.py              # CRUD + 404
│       ├── test_schedules.py            # by-date / by-date-and-class
│       ├── test_appointments.py         # details / subscribe / waitinglist
│       ├── test_calendar.py             # /day, /week, include_friends paths
│       └── test_views.py                # all HTML pages + HTMX endpoints
├── cli/
│   ├── test_import_schedule.py          # parse_dutch_date, extract_schedules_from_pdf (mocked)
│   ├── test_import_schedule_main.py     # main() — missing PDF, dry-run, full run, no-schedules
│   ├── test_backup_db.py                # backup() + rotate()
│   ├── test_backup_db_main.py           # main() invokes backup + rotate
│   └── test_add_1rm.py
└── services/
    ├── test_friends.py                  # CRUD + owner scoping
    ├── test_friends_migration.py        # _migrate_v200 ALTER branch (legacy schema)
    ├── test_migrations.py
    ├── test_schedule.py
    ├── test_preferences.py
    ├── test_one_rep_max.py
    ├── test_login_limiter.py
    ├── test_session.py
    ├── test_day_card.py
    ├── test_api_cache.py
    ├── test_base.py
    └── test_db.py
```

## Fixtures

### Root `tests/conftest.py`

#### `db_path` (function scope)

Path to fresh SQLite DB in `tmp_path` with all migrations applied. Calls `migrations._reset_for_tests()` so the process-level applied-paths cache doesn't block re-runs against new paths.

```python
def test_something(db_path):
    svc = ScheduleService(db_path)
    ...
```

#### `clean_registry` (function scope)

Saves/restores `migrations._registry` around a test. Use when test temporarily registers a migration version.

### `tests/app/conftest.py` — FastAPI fixtures

Auto-isolation via `_isolate_dependency_caches` (autouse): every test gets `DB_PATH` env pointed at fresh `db_path`, all `lru_cache`-backed dependency factories cleared before/after, and the login rate limiter reset.

| Fixture | What it provides |
|---|---|
| `app_client` | `TestClient(app)` with `WodAppClient.from_session` patched to return `mock_wodapp_client`. Auth chain (`require_session`) still runs — 401 behavior is testable. |
| `auth_session` | Sample `AuthSession` (user_id=42, gym_id=100). |
| `session_cookie` | Signed cookie value via `cookie_session.encode(auth_session, settings.secret_key)`. Set via `app_client.cookies.set("session", session_cookie)`. |
| `mock_wodapp_client` | `MagicMock(spec=WodAppClient)`. Tests assign return values per call. |
| `friends_service`, `schedule_service`, `preferences_service`, `one_rep_max_service` | Real services bound to the test `db_path` for direct seeding/assertion. |

Why patch `WodAppClient.from_session` instead of overriding `get_client_from_session` via `app.dependency_overrides`? FastAPI overrides bypass the entire dep chain — overriding the client dep would skip `require_session` and break 401 tests. Patching `from_session` keeps the auth chain intact.

#### Auth pattern

```python
def test_authenticated_route(app_client, session_cookie, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = []
    app_client.cookies.set("session", session_cookie)
    response = app_client.get("/api/calendar/day")
    assert response.status_code == 200
```

#### Triggering exception handlers

`app/main.py` global handlers (`WodAppError`, `AuthenticationError`) are tested by attaching a temp router that raises:

```python
router = APIRouter()

@router.get("/__test__/wodapp_err")
def boom():
    raise WodAppError("service down")

app.include_router(router)
# call route, assert handler response, then remove route
```

### `tests/e2e/conftest.py` — Playwright fixtures

E2E tests run against a real FastAPI server in a background thread — no `TestClient` magic, full HTMX and JS execution.

#### `live_server` (session scope)

Starts uvicorn on a free port against a temp SQLite DB. Patches `WodAppClient.from_session` at the class level to return the current per-test `_mock_holder[0]` value, so every request to the live server uses the test's mock.

```python
def test_something(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = [...]
    page.goto("/calendar")
    ...
```

#### `mock_wodapp_client` (function scope)

`MagicMock(spec=WodAppClient)` swapped into `_mock_holder` before each test, cleared after. Default return values: `get_upcoming_reservations → ([], {})`, `get_day_schedule → []`. Tests override per-call return values or use `side_effect` for multi-call sequences.

#### `authed_context` (function scope)

`BrowserContext` with a signed session cookie (encoded via `cookie_session.encode(auth_session, settings.secret_key)`) — same signing key the live server uses, so the cookie is valid.

#### `page` (function scope)

Authenticated page derived from `authed_context`. Pre-dismisses all tooltips for the test user before yielding, so tooltip overlays don't intercept clicks.

#### `unauthed_page` (function scope)

Browser page with no session cookie — used for login/redirect tests.

#### DB isolation

All E2E tests share a single session-scoped temp DB. Tests needing isolated state use distinct `user_id`s (filters: 100, friends: 200/201) or clean up explicitly at the end of the test.

#### Patching in live-server tests

For routes that call `WodAppClient()` directly (e.g. the login route), use `unittest.mock.patch` in the test body — it modifies the same module object the server thread uses:

```python
def test_login_bad_credentials_shows_error(unauthed_page):
    with patch("wodplanner.app.routers.auth.WodAppClient") as MockClient:
        MockClient.return_value.login.side_effect = AuthenticationError("bad")
        unauthed_page.fill("input[name=username]", "x@x.com")
        unauthed_page.fill("input[name=password]", "bad")
        unauthed_page.click("button[type=submit]")
    expect(unauthed_page.locator(".login-error")).to_contain_text("Invalid")
```

#### Waiting for HTMX swaps

Use `page.expect_response(lambda r: "/path" in r.url)` to wait for the XHR to complete before asserting DOM state. Playwright's `expect(locator)` assertions auto-retry, so you can also just assert directly after a click and let the timeout handle the wait.

```python
with page.expect_response(lambda r: "/calendar/2026-04-25" in r.url):
    page.get_by_title("Previous day").click()
expect(page.locator(".current-date")).to_have_text("April 25, 2026")
```

## Mocking pdfplumber

`extract_schedules_from_pdf` tested via `unittest.mock.patch("pdfplumber.open")`. Mock provides fake table data (list of rows) — no real PDF needed.

```python
def _mock_pdf(self, tables_per_page):
    pages = []
    for tables in tables_per_page:
        page = MagicMock()
        page.extract_tables.return_value = tables
        pages.append(page)
    pdf = MagicMock()
    pdf.__enter__ = MagicMock(return_value=pdf)
    pdf.__exit__ = MagicMock(return_value=False)
    pdf.pages = pages
    return pdf
```

## Mocking httpx (WodApp API)

`WodAppClient` tests patch `wodplanner.api.client.httpx.Client` and feed `MockResponse(json_data, status_code)` to `mock_client.post`. Retry tests also patch `time.sleep` to avoid real waits. See `tests/api/test_client.py` and `tests/api/test_client_retry.py`.

## Tool configuration (`pyproject.toml`)

| Tool | Config section | Notes |
|------|---------------|-------|
| pytest | `[tool.pytest.ini_options]` | `testpaths = ["tests"]`; `e2e` marker registered |
| pytest-cov | dev dep | Run via `pytest --cov=wodplanner` |
| pytest-playwright | dev dep | Browser tests; run `playwright install chromium` once |
| ruff | `[tool.ruff]` | `line-length = 100`; selects E, F, I; E501 ignored (pre-existing long lines) |
| mypy | `[tool.mypy]` | `python_version = "3.11"`, `warn_return_any`, `ignore_missing_imports`; not strict |

## Adding new tests

- **New service**: `tests/services/test_<name>.py`. Use `db_path` — it runs all registered migrations.
- **New migration**: test in `test_migrations.py` (or service-specific migration test, e.g. `test_friends_migration.py`) that verifies schema + data preservation. Use `clean_registry` for test-only versions.
- **New router**: `tests/app/routers/test_<name>.py`. Use `app_client` + `session_cookie` for authenticated requests; assign return values on `mock_wodapp_client` for API stubs.
- **New view requiring HTML rendering**: assert status + presence of key strings (e.g. exercise name, partial wrapper id), not full HTML diffs.
- **New CLI subcommand**: pure-function tests for parsers, plus a `main()` test that uses `monkeypatch.setattr("sys.argv", [...])` and patches I/O (`pdfplumber.open`, `input`, etc.).
- **New HTMX behavior or JS feature**: add to the relevant `tests/e2e/test_*.py`. Use `mock_wodapp_client` to control server data, `page.expect_response(...)` to wait for XHR, and service classes to seed/verify DB state. Keep `user_id` distinct from 42 if the test writes to the preferences or friends table.
- **New template element that needs E2E targeting**: prefer `get_by_role` / `get_by_text` / `get_by_title`; add `data-testid` only when role/text is ambiguous.
