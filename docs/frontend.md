# Frontend

## Stack

Server-rendered HTML with HTMX. Views router serves pages, API routers handle data. Templates use partials for HTMX swaps. Login page is standalone (no base.html navbar). Single CSS file: `app/static/css/style.css`. Mobile breakpoint: `640px`.

## OOB Swap Gotcha

`calendar.html` and `partials/calendar_day.html` both contain date-nav and filters HTML. `calendar_day.html` replaces them via `hx-swap-oob="true"` on every navigation/filter change. **Any change to date-nav or filters HTML must be made in both files.**

## Schedule Import

`import-schedule` CLI parses CrossFit Purmerend PDF schedules (Dutch format) using pdfplumber. Extracts workout details per class type: warmup/mobility, strength/specialty, metcon. Stored in `schedules` table scoped to a gym via `--gym-id` (required arg). Unique constraint is `(date, class_type, gym_id)`. Class names normalized via `CLASS_NAME_MAPPING` in `services/schedule.py` to match API appointment names (e.g. "CF101" → "CrossFit 101").

Calendar views pass `session.gym_id` to all schedule queries. Query filter is `gym_id = ? OR gym_id IS NULL` — the NULL fallback covers rows imported before gym scoping was added.

## 1RM Tracking

`services/one_rep_max.py` provides two utilities and a service class:

- `has_1rm_exercise(text)` — returns `True` if `text` contains "1rm" as an exercise name (not a percentage reference like "70% 1rm"). Checks the 6 chars preceding each match for `\d+%\s*$`.
- `extract_1rm_exercises(text)` — returns list of exercise names following non-percentage "1rm" occurrences. Captures full name up to next `A./B./C.` section delimiter, then strips parenthetical weight annotations (e.g. `(2x 20kg)`). **Uses `re.DOTALL`** — pdfplumber can split a cell across lines (e.g. `(2x\n20kg)`), and without DOTALL the `.+?` can't cross the embedded newline, causing the match to fail silently and return no exercises.
- `OneRepMaxService` — CRUD over `one_rep_maxes` table; all methods take explicit `user_id`.

**Calendar enrichment**: `calendar_day_partial` calls `schedule_service.find_for_appointment()` per appointment and sets `has_1rm=True` on the appointment dict when `strength_specialty` or `warmup_mobility` contains a 1rm exercise. Triggers a dumbbell icon (`.btn-1rm`, purple) in `partials/calendar_content.html`.

**Modal**: clicking the icon does `hx-get="/appointments/{id}/1rm"` → loads `partials/one_rep_max_modal.html` into `#one-rep-max-modal-container`. Modal contains a log form (exercise pre-filled from schedule, datalist from past exercises) and history table partial. History is sorted by `_similarity_score` against `suggested_exercises`: exact name match = 2, substring/word overlap = 1, no match = 0 — so relevant past entries float to the top.

**1RM page** (`/1rm`): chart (Chart.js CDN, line chart) with exercise dropdown — auto-selects first exercise on load. "+ Log" button toggles a collapsible form; exercise input defaults to the most recently logged exercise (`entries[0].exercise`). History table below. After add/delete HTMX swaps `#one-rep-max-history`; the partial carries updated chart data in `data-exercises` JSON attribute; `htmx:afterSwap` listener refreshes the Chart.js instance and dropdown without a page reload.

**`.form-control` class**: defined in `style.css` with explicit `background-color: white; color: var(--gray-900)`. Required to prevent white-on-white datalist text when OS is in dark mode (browser applies dark native styles to the dropdown while the input background stays white without an explicit declaration).

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
