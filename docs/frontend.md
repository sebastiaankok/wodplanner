# Frontend

## Stack

Server-rendered HTML with HTMX. Views router serves pages, API routers handle data. Templates use partials for HTMX swaps. Login page is standalone (no base.html navbar). Single CSS file: `app/static/css/style.css`. Mobile breakpoint: `640px`.

## OOB Swap Gotcha

`calendar.html` and `partials/calendar_day.html` both contain date-nav and filters HTML. `calendar_day.html` replaces them via `hx-swap-oob="true"` on every navigation/filter change. **Any change to date-nav or filters HTML must be made in both files.** This includes the `.filter-btn-wrapper` tooltip markup — both files must stay in sync.

## Schedule Import

`import-schedule` CLI parses CrossFit Purmerend PDF schedules (Dutch format) using pdfplumber. Extracts workout details per class type: warmup/mobility, strength/specialty, metcon. Stored in `schedules` table scoped to a gym via `--gym-id` (required arg). Unique constraint is `(date, class_type, gym_id)`. Class names normalized via `CLASS_NAME_MAPPING` in `services/schedule.py` to match API appointment names (e.g. "CF101" → "CrossFit 101").

**Class name normalization**: pdfplumber can emit class names with embedded newlines when the PDF cell wraps (e.g. `"CrossFit\n& Teen Athlete"`). `normalize_class_name()` collapses all internal whitespace (`re.sub(r'\s+', ' ', ...)`) before lookup, so "CrossFit\n& Teen Athlete" and "CrossFit & Teen Athlete" always resolve to the same canonical key. **Do not revert this to `.strip()` only.**

**Reverse alias lookup**: `get_all_class_aliases()` does bidirectional resolution. If the API reports a class as "CrossFit" but the PDF schedule only has a combined "CrossFit & Teen Athlete" entry, the lookup still finds the schedule because `CLASS_NAME_MAPPING["CrossFit & Teen Athlete"] = ["CrossFit", "Teen Athlete"]` — "CrossFit" appears as an alias, so `get_all_class_aliases("CrossFit")` returns `["CrossFit", "CrossFit & Teen Athlete"]` and the SQL query covers both.

Calendar views pass `session.gym_id` to all schedule queries. Query filter is `gym_id = ? OR gym_id IS NULL` — the NULL fallback covers rows imported before gym scoping was added.

`ScheduleService.get_all_for_date(date, gym_id)` fetches all schedules for a date in one query and returns `dict[str, Schedule]` keyed by every known alias for each class type. Used by the calendar view builder to avoid per-appointment DB queries.

## Calendar View Builder

`services/calendar_view.py` — shared logic for both `calendar_page` and `calendar_day_partial`.

**`build_calendar_view(session, target_date, client, friends_service, schedule_service, hidden_types) -> list[dict]`**:
1. Fetches appointments via `client.get_day_schedule()`
2. Filters hidden class types
3. Pre-loads all schedules for the date via `schedule_service.get_all_for_date()` — one DB query, O(1) per-appointment lookup
4. If user has friends: parallelizes `get_appointment_members()` calls across a `ThreadPoolExecutor(max_workers=5)` — bounded to avoid overloading upstream API
5. Failures in member fetch are caught and logged as warnings; affected appointments render with empty friends list

`is_signup_open(appt_name, appt_start)` also lives here (not in `views.py`). Regular classes open 7 days before start; CF101/101 classes open 14 weeks before.

After PDF parsing, `import-schedule` collects all unique raw 1RM exercise names across all schedules and runs `resolve_exercise_interactive()` for each. Exact matches are silent. Fuzzy matches prompt: `[1] Accept match [2] Add as new [3] Rename [4] Skip`. No match prompts: `[1] Add as new [2] Rename [3] Skip`. Choosing rename recurses with the new name. New exercise names are persisted to the `exercises` table before DB save.

## 1RM Tracking

`services/one_rep_max.py` provides module-level utilities and a service class:

- `has_1rm_exercise(text)` — returns `True` if `text` contains "1rm" as an exercise name (not a percentage reference like "70% 1rm"). Checks the 6 chars preceding each match for `\d+%\s*$`.
- `extract_1rm_exercises(text)` — returns list of exercise names following non-percentage "1rm" occurrences. Captures full name (including across line breaks — pdfplumber can wrap a cell across lines) up to next `A./B./C.` section delimiter or end of string, then strips parenthetical weight annotations and collapses internal whitespace. **Uses `re.DOTALL` + `\Z`** so `.+?` can cross embedded newlines and `$` doesn't short-circuit at line end. **Do not change to `re.MULTILINE` or `$`** — that breaks multi-line exercise names like "Future Method\nMiniband Small Grip Benchpress".
- `resolve_exercise_interactive(raw_name, exercises)` — interactive CLI prompt (stdout/stdin). Exact match returns silently. Fuzzy match (via `difflib.get_close_matches`, cutoff 0.6) offers accept/add-new/rename/skip. No match offers add-new/rename/skip. Rename recurses. Returns a canonical name (existing or new) or `None` (skip). Caller persists new names to DB.
- `OneRepMaxService` — manages both exercise list and user 1RM records. Key methods:
  - `get_exercise_list()` — all exercise names from `exercises` table, alphabetically sorted
  - `add_exercise(name)` — inserts into `exercises`; returns `False` if duplicate
  - `validate_exercise(name)` — checks `exercises` table; used server-side before insert
  - `match_exercise(name, cutoff=0.6)` — fuzzy matches against `exercises` table via difflib
  - `get_max_for_exercise(user_id, exercise)` — `MAX(weight_kg)` for the percentage calculator
  - `get_exercises(user_id)` — distinct exercise names the user has actually logged (for chart selector)
  - CRUD: `add()`, `get_all()`, `get_for_exercise()`, `delete()` — all scoped by `user_id`

**Calendar enrichment**: sets `has_1rm=True` on the appointment dict when `strength_specialty`, `warmup_mobility`, **or `metcon`** contains a 1rm exercise. Triggers a dumbbell icon (`.btn-1rm`, purple) in `partials/calendar_content.html`.

**Modal**: clicking the icon does `hx-get="/appointments/{id}/1rm"` → loads `partials/one_rep_max_modal.html` into `#one-rep-max-modal-container`. Raw exercise names extracted from the schedule are fuzzy-matched to canonical names via `match_exercise()`; the first match pre-selects the `<select>` dropdown. Full exercise list (`exercises` table) is always available in the dropdown. History is sorted by `_similarity_score` against `suggested_exercises` so relevant past entries float to the top.

**1RM page** (`/1rm`): chart (Chart.js CDN, line chart) with exercise dropdown (shows only exercises the user has logged) — auto-selects first on load. "+ Log" button toggles a collapsible form with a `<select>` populated from `exercises` table (full canonical list). Exercise defaults to most recently logged (`entries[0].exercise`). History table below. After add/delete HTMX swaps `#one-rep-max-history`; the partial carries updated chart data in `data-exercises` JSON attribute; `htmx:afterSwap` listener refreshes Chart.js and dropdown without page reload.

**Percentage calculator**: appears below the card header when an exercise with data is selected. Two-column stat display (Percentage | Weight) with a range slider (50–100%, step 5). Max weight for the selected exercise is computed client-side from `__1rmData` (already embedded in page as JSON). Weight updates on every slider move: `Math.round(max * pct/100 * 2) / 2` rounds to nearest 0.5 kg. Slider fill color is kept in sync via a CSS custom property `--fill` set inline by `syncSliderFill()`.

**`add-1rm` CLI**: `add-1rm [--exercise NAME] [--db PATH]` — adds an exercise to the `exercises` table. Uses `resolve_exercise_interactive()` for the same fuzzy-match/rename/skip flow as the PDF importer. Prints existing list when `--exercise` is omitted.

**`.form-control` class**: defined in `style.css` with explicit `background-color: white; color: var(--gray-900)`. Required to prevent white-on-white select/input text when OS is in dark mode.

## Dark Mode

CSS-only via `@media (prefers-color-scheme: dark)` at the bottom of `style.css`. Does **not** flip `:root` variables — uses explicit overrides per element class to avoid conflicts with the always-dark navbar (which uses `var(--gray-900)` as background). `:root` declares `color-scheme: light dark` so native browser controls (scrollbars, datalist, select) also honor the system theme. `login.html` has its own inline dark-mode block (it doesn't extend `base.html`).

## PWA Install Banner

`base.html` renders a fixed-bottom install banner when `user` is set (logged in). Logic runs in an IIFE on page load:

- Skips if already installed (`display-mode: standalone` or `navigator.standalone`)
- Skips if user dismissed (`localStorage` key `pwa-prompt-dismissed`)
- **Android/Chrome**: listens for `beforeinstallprompt`, defers it, shows banner with Install + Dismiss buttons. Install triggers `deferredPrompt.prompt()`.
- **iOS/Safari**: detects `/iphone|ipad|ipod/i` UA, shows "tap Share → Add to Home Screen" instruction.

Dismissing (or accepting install) sets `pwa-prompt-dismissed` in localStorage — banner never reappears.

## Calendar Filters

Filter state stored in `preferences` table as `hidden_class_types` JSON list (per `user_id`). Defaults to `[]` — new users see all classes. UI label is **"Hide:"** — a checked checkbox means that class type is in `hidden_class_types` (hidden). Toggle endpoint `POST /filters/toggle/{class_type}` adds/removes the type from the list and returns a full calendar content swap.

## Tooltips

One-time onboarding hints stored in `preferences` table as `dismissed_tooltips` JSON list (per `user_id`). Defaults to `[]` — tooltip shows until dismissed. Dismissal is persistent: survives logout/login and page reload.

**Flow**: template renders tooltip conditionally on `show_filter_tooltip` (passed from view). User clicks "Got it" → `hx-post="/tooltips/dismiss/{tooltip_id}"` with `hx-target="#filter-tooltip" hx-swap="outerHTML"` → endpoint calls `PreferencesService.dismiss_tooltip()`, returns empty string → HTMX replaces the tooltip element with nothing.

**Adding new tooltips**: add a new `tooltip_id` string, check it against `dismissed_tooltips` in the view, pass a `show_{id}_tooltip` bool to the template. No schema change needed — `dismissed_tooltips` is an unbounded JSON array.

**Service methods** (`services/preferences.py`):
- `get_dismissed_tooltips(user_id)` — returns list of dismissed tooltip IDs
- `dismiss_tooltip(user_id, tooltip_id)` — appends ID if not already present (idempotent)
