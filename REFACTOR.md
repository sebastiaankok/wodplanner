# WodPlanner Refactor & Optimization Plan

## Context

WodPlanner has grown organically from a CLI API client into a FastAPI app with HTMX views, multiple SQLite-backed services, and CLI tooling. This has produced:

- **Duplication hotspots** — `calendar_page` and `calendar_day_partial` are ~96 LOC near-copies; four service classes repeat the same init/connection/migration boilerplate; four subscribe/unsubscribe client methods are 95% identical.
- **Performance issues** — `calendar_page` fires N+1 API calls to `get_appointment_members()` (one per appointment), and N+1 DB calls to `find_for_appointment()` (alias scan per appointment). On a 10-class day, that's 20+ round trips that a single user sees per page load.
- **Hidden failures** — bare `except Exception: pass` blocks in both calendar views silently drop friend-member fetches.
- **Migration fragility** — schema migrations live inline in each service's `_init_db()`, with no version table; multiple services racing to migrate on startup.
- **Zero automated tests** — `tests/` is empty; `import_schedule.py` has ~90 LOC of untested regex-driven PDF parsing.

Goal: reduce the surface area that breaks with each feature, cut the calendar page's latency, and make schema/services safe to evolve. Changes should be shippable incrementally — no big-bang rewrite.

---

## Priorities

Ordered by impact × effort. Each item is independently mergeable.

### P1 — Preferences batch fetch + single friends query

**Problem:**
- `preferences.py:get_all` calls `get_hidden_class_types()` and `get_dismissed_tooltips()` sequentially (two DB hits where one would do).
- Views do `friends_service.get_appuser_ids(user_id)` **and** `friends_service.get_all(user_id)` back-to-back (`views.py:202-203`, `:303-304`) — same table, twice.

**Fix:**
1. Add `PreferencesService.get_for_user(user_id) -> dict` combining both lists in a single query (or two queries in one transaction if schema forces it).
2. Replace the two friends calls with a single `get_all(user_id)` and derive `appuser_ids` from it in Python: `{f.appuser_id for f in friends}`. Remove `get_appuser_ids` if unused elsewhere.

**Files:** `services/preferences.py`, `services/friends.py`, `app/routers/views.py`, `app/routers/calendar.py`.

### P1 — Extract calendar-template shared partial

**Problem:** `docs/frontend.md` documents that `calendar.html:9-46` and `partials/calendar_day.html:7-58` must stay byte-identical for OOB swaps. That's a maintenance trap (already noted in docs — make the fix, not just the warning).

**Fix:** Extract date-nav + filters block into `partials/_calendar_header.html`, include from both templates. OOB swap target IDs remain; only the source template changes.

**Files:** `app/templates/calendar.html`, `app/templates/partials/calendar_day.html`, new `app/templates/partials/_calendar_header.html`.

### P2 — Move view helpers into services

**Problem:** `views.py:37-93` houses `_format_1rm_entries`, `_similarity_score`, `_build_exercises_chart_data`, `is_signup_open` — business logic co-located with HTTP routing.

**Fix:** Move to `services/one_rep_max.py` (1RM/chart helpers) and `services/schedule.py` (`is_signup_open`). Only routing glue stays in `views.py`.

**Files:** `app/routers/views.py`, `services/one_rep_max.py`, `services/schedule.py`.

### P2 — Centralize date parsing

**Problem:** `date.fromisoformat`, `datetime.strptime(..., "%Y-%m-%d %H:%M")` scattered across `views.py` (lines 538, 568, 599, 630, 702, 729) and client methods. Any format change touches 10+ sites.

**Fix:** `src/wodplanner/utils/dates.py` with `parse_iso_date`, `parse_api_datetime`, `fmt_api_datetime`. Replace call sites.

**Files:** new `utils/dates.py`, `api/client.py`, `app/routers/views.py`.

### P2 — Tooling + test bootstrap

**Problem:** No ruff, no mypy, no pytest config in `pyproject.toml`. `tests/` is empty; `import_schedule.py` PDF regex parsing has zero tests.

**Fix:**
1. Add `[tool.pytest.ini_options]` with `testpaths = ["tests"]`, add `[tool.ruff]` (line-length 100), add `[tool.mypy]` (basic, not strict — strict is a follow-up).
2. Seed `tests/` with: `tests/services/test_schedule.py`, `tests/services/test_friends.py`, `tests/services/test_migrations.py` (new), `tests/cli/test_import_schedule.py` with a checked-in fixture PDF. Temp-DB fixture lives in `tests/conftest.py`.
3. Add a CI workflow (`.github/workflows/ci.yml`) running `pytest` + `ruff check` on push.

**Files:** `pyproject.toml`, new `tests/` tree, new `.github/workflows/ci.yml`.

### P3 — Config & CLI cleanup

**Problem:**
- `cli/backup_db.py:38` hardcodes `/data/wodplanner.db` (production path); `cli/import_schedule.py:244` defaults to relative `wodplanner.db`.
- `cli/backup_db.py:17-22` opens raw `sqlite3.connect` — bypasses WAL/PRAGMA setup from `services/db.py`.

**Fix:**
1. Add `DB_PATH` to `app/config.Settings`; CLI entry points import `settings` and use it as default. `.env` loads for CLI via `pydantic-settings` (already a dep).
2. Rewrite `backup_db.py` to use `services.db.get_connection` as the source handle so PRAGMA/WAL settings are consistent.

**Files:** `app/config.py`, `cli/backup_db.py`, `cli/import_schedule.py`, `cli/add_1rm.py`.

### P3 — Model cleanup

**Problem:** Unused fields (`Appointment.id_parent`, `Subscriptions.subscribed`/`full`, `AppointmentDetails.unsubscribe_closed`); loose typing (`int = 0` bool-ish flags; `Gym.unsubscribed_for_mailing: int = 0` should be `bool`); `AppointmentDetails` duplicates `Appointment` fields instead of inheriting.

**Fix:** Delete unused fields (verify with `grep` first), switch flag ints to `bool`, make `AppointmentDetails(Appointment)` via inheritance. Business methods on models (`is_open_for_signup`, `has_spots_available`) — leave them; they're pure and small.

**Files:** `src/wodplanner/models/calendar.py`, `src/wodplanner/models/auth.py`.

---

## Out of Scope (explicitly not doing now)

- SQLite connection pooling — premature; WAL handles contention at current load. Revisit if a profile shows lock waits.
- Replacing `pdfplumber` — heavy but works, used only by one CLI tool.
- Async API client rewrite — the sync client + bounded thread pool (P0) gets most of the latency win without touching every call site.
- Cache eviction policy in `api_cache.py` — unbounded growth is theoretical; cache keys are bounded by (gym × date × appointment).
