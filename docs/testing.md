# Testing

## Running locally

```bash
# All tests
pytest

# With coverage report
pytest --cov=wodplanner --cov-report=term-missing

# Specific file or test
pytest tests/services/test_schedule.py
pytest tests/services/test_schedule.py::TestScheduleService::test_upsert_updates_existing

# Lint
ruff check .

# Type check (basic — not strict)
mypy src/
```

Current coverage: **98%** across 409 tests.

## CI

`.github/workflows/ci.yml` runs on every push: `ruff check .` then `pytest`. Uses Python 3.12 with pip caching. Docker build is a separate workflow (`docker.yml`, runs on `main` and version tags only).

## Test structure

```
tests/
├── conftest.py                          # shared db_path / clean_registry fixtures
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
    ├── test_calendar_view.py
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
| pytest | `[tool.pytest.ini_options]` | `testpaths = ["tests"]` |
| pytest-cov | dev dep | Run via `pytest --cov=wodplanner` |
| ruff | `[tool.ruff]` | `line-length = 100`; selects E, F, I; E501 ignored (pre-existing long lines) |
| mypy | `[tool.mypy]` | `python_version = "3.11"`, `warn_return_any`, `ignore_missing_imports`; not strict |

## Adding new tests

- **New service**: `tests/services/test_<name>.py`. Use `db_path` — it runs all registered migrations.
- **New migration**: test in `test_migrations.py` (or service-specific migration test, e.g. `test_friends_migration.py`) that verifies schema + data preservation. Use `clean_registry` for test-only versions.
- **New router**: `tests/app/routers/test_<name>.py`. Use `app_client` + `session_cookie` for authenticated requests; assign return values on `mock_wodapp_client` for API stubs.
- **New view requiring HTML rendering**: assert status + presence of key strings (e.g. exercise name, partial wrapper id), not full HTML diffs.
- **New CLI subcommand**: pure-function tests for parsers, plus a `main()` test that uses `monkeypatch.setattr("sys.argv", [...])` and patches I/O (`pdfplumber.open`, `input`, etc.).
```
