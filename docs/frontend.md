# Frontend

## Stack

Server-rendered HTML with HTMX. Views router serves pages, API routers handle data. Templates use partials for HTMX swaps. Login page is standalone (no base.html navbar). Single CSS file: `app/static/css/style.css`. Mobile breakpoint: `640px`.

## OOB Swap Gotcha

`calendar.html` and `partials/calendar_day.html` both contain date-nav and filters HTML. `calendar_day.html` replaces them via `hx-swap-oob="true"` on every navigation/filter change. **Any change to date-nav or filters HTML must be made in both files.**

## Schedule Import

`import-schedule` CLI parses CrossFit Purmerend PDF schedules (Dutch format) using pdfplumber. Extracts workout details per class type: warmup/mobility, strength/specialty, metcon. Stored in `schedules` table with `(date, class_type)` unique constraint. Class names normalized via `CLASS_NAME_MAPPING` in `services/schedule.py` to match API appointment names (e.g. "CF101" → "CrossFit 101").

## 1RM Tracking

`services/one_rep_max.py` provides two utilities and a service class:

- `has_1rm_exercise(text)` — returns `True` if `text` contains "1rm" as an exercise name (not a percentage reference like "70% 1rm"). Checks the 6 chars preceding each match for `\d+%\s*$`.
- `extract_1rm_exercises(text)` — returns list of exercise names following non-percentage "1rm" occurrences. Captures full name up to next `A./B./C.` section delimiter, then strips parenthetical weight annotations (e.g. `(2x 20kg)`). **Uses `re.DOTALL`** — pdfplumber can split a cell across lines (e.g. `(2x\n20kg)`), and without DOTALL the `.+?` can't cross the embedded newline, causing the match to fail silently and return no exercises.
- `OneRepMaxService` — CRUD over `one_rep_maxes` table; all methods take explicit `user_id`.

**Calendar enrichment**: `calendar_day_partial` calls `schedule_service.find_for_appointment()` per appointment and sets `has_1rm=True` on the appointment dict when `strength_specialty` or `warmup_mobility` contains a 1rm exercise. Triggers a dumbbell icon (`.btn-1rm`, purple) in `partials/calendar_content.html`.

**Modal**: clicking the icon does `hx-get="/appointments/{id}/1rm"` → loads `partials/one_rep_max_modal.html` into `#one-rep-max-modal-container`. Modal contains a log form (exercise pre-filled from schedule, datalist from past exercises) and history table partial.

**1RM page** (`/1rm`): chart (Chart.js CDN, line chart) with exercise dropdown — auto-selects first exercise on load. "+ Log" button toggles a collapsible form. History table below. After add/delete HTMX swaps `#one-rep-max-history`; the partial carries updated chart data in `data-exercises` JSON attribute; `htmx:afterSwap` listener refreshes the Chart.js instance and dropdown without a page reload.
