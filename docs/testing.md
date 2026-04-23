# Testing

## Running locally

```bash
# All tests
pytest

# Specific file or test
pytest tests/services/test_schedule.py
pytest tests/services/test_schedule.py::TestScheduleService::test_upsert_updates_existing

# Lint
ruff check .

# Type check (basic — not strict)
mypy src/
```

## CI

`.github/workflows/ci.yml` runs on every push: `ruff check .` then `pytest`. Uses Python 3.12 with pip caching. Docker build is a separate workflow (`docker.yml`, runs on `main` and version tags only).

## Test structure

```
tests/
├── conftest.py                    # shared fixtures
├── cli/
│   └── test_import_schedule.py   # parse_dutch_date, is_date_row, is_class_name,
│                                  # clean_text, extract_schedules_from_pdf (mocked)
└── services/
    ├── test_friends.py            # FriendsService CRUD + owner scoping
    ├── test_migrations.py         # register(), run_all(), ensure_migrations()
    └── test_schedule.py           # normalize/alias helpers + ScheduleService CRUD
```

## Fixtures (`tests/conftest.py`)

### `db_path` (function scope)

Provides a `Path` to a fresh SQLite DB in `tmp_path` with all migrations already applied.

```python
def test_something(db_path):
    svc = ScheduleService(db_path)
    ...
```

Calls `migrations._reset_for_tests()` before each test so the process-level applied-paths cache doesn't prevent migrations from running against the new path. Each test gets its own `tmp_path` directory, so DB files never collide between tests.

### `clean_registry` (function scope)

Saves and restores `migrations._registry` around a test. Use when your test temporarily registers a migration version (e.g. to test duplicate-version detection) so those entries don't leak into subsequent tests.

```python
def test_register_duplicate(clean_registry):
    migrations.register(9999, "test", lambda conn: None)
    with pytest.raises(ValueError):
        migrations.register(9999, "other", lambda conn: None)
```

## Mocking pdfplumber

`extract_schedules_from_pdf` is tested via `unittest.mock.patch("pdfplumber.open")`. The mock provides fake table data (list of rows) without needing a real PDF file. This exercises all parsing logic: date detection, class-name normalization, continuation rows, header skipping, source-file attribution.

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

## Tool configuration (`pyproject.toml`)

| Tool | Config section | Notes |
|------|---------------|-------|
| pytest | `[tool.pytest.ini_options]` | `testpaths = ["tests"]` |
| ruff | `[tool.ruff]` | `line-length = 100`; selects E, F, I; E501 ignored (pre-existing long lines) |
| mypy | `[tool.mypy]` | `python_version = "3.11"`, `warn_return_any`, `ignore_missing_imports`; not strict |

## Adding new tests

- **New service**: add `tests/services/test_<name>.py`. Use the `db_path` fixture — it runs all registered migrations, including your new one.
- **New migration**: add a test in `test_migrations.py` that verifies the migration creates/alters the expected schema. Use `clean_registry` if you need to register test-only migration versions.
- **New CLI parser**: add pure-function tests (no DB, no PDF) plus a `patch("pdfplumber.open")` test for any `extract_*` function.
