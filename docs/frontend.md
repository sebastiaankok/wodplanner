# Frontend

## Stack

Server-rendered HTML with HTMX. Views router serves pages, API routers handle data. Templates use partials for HTMX swaps. Login page is standalone (no base.html navbar). Single CSS file: `app/static/css/style.css`. Mobile breakpoint: `640px`.

## OOB Swap Gotcha

`calendar.html` and `partials/calendar_day.html` both contain date-nav and filters HTML. `calendar_day.html` replaces them via `hx-swap-oob="true"` on every navigation/filter change. **Any change to date-nav or filters HTML must be made in both files.**

## Schedule Import

`import-schedule` CLI parses CrossFit Purmerend PDF schedules (Dutch format) using pdfplumber. Extracts workout details per class type: warmup/mobility, strength/specialty, metcon. Stored in `schedules` table with `(date, class_type)` unique constraint. Class names normalized via `CLASS_NAME_MAPPING` in `services/schedule.py` to match API appointment names (e.g. "CF101" → "CrossFit 101").
