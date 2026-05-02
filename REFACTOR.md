# Refactor Candidates — Deepening Opportunities

Surfaced via `/improve-codebase-architecture`. Vocabulary: `LANGUAGE.md` (Module, Interface, Depth, Seam, Adapter, Leverage, Locality) + `CONTEXT.md` (Appointment, Schedule, Friend, Member, Class Type, Sign Up, Google Calendar Sync, 1RM).

ADRs not re-litigated: 0001 (reverse-engineered API), 0002 (cookie sessions), 0003 (SQLite single-process).

---

## 1. Two parallel Appointment-view builders, both shallow

**Files**
- `src/wodplanner/services/calendar_view.py:29-73`
- `src/wodplanner/app/routers/calendar.py:51-148`

**Problem**
Two near-clones build the same enriched Appointment shape. `build_calendar_view()` returns plain dicts with `friends`, `has_1rm`, `signup_open`, `is_past`. `routers/calendar.py` rebuilds an `AppointmentResponse` Pydantic shape with a subset (`friends` only, no 1RM, no signup_open). Field extraction (`time_start`, `spots_taken`, …) duplicated across `calendar.py:73-86` and `calendar.py:126-139`. HTML path enriches; JSON path under-enriches. Same domain concept, two implementations, neither deep.

Deletion test: drop `build_calendar_view` — Schedule lookup + Friend cross-ref + 1RM detection + signup-window rule reappear across two routers. Earns its keep, but interface shallow: callers still pick fields manually.

**Solution sketch**
One enriched-Appointment builder. JSON router and HTML view share enrichment. Tests target one surface (`given Appointments + Friends + Schedules + now → cards[]`) instead of patching `WodAppClient.from_session` per-router (`tests/app/conftest.py:88-92`).

**Concept**
The enriched Appointment — Appointment joined with Friend presence, matched Schedule, 1RM flag, sign-up status. No name in `CONTEXT.md`. Candidate term: **Day Card** or **Appointment Card**. Add to `CONTEXT.md` if adopted.

**Benefit**
Locality: one place owns enrichment rules. Leverage: HTML and JSON callers both shrink to "build cards, render". Test surface matches the interface.

---

## 2. Appointment ↔ Schedule lookup rule split across callers

**Files**
- `src/wodplanner/services/calendar_view.py:50` — inline fallback `schedule_map.get(appt.name) or schedule_map.get(normalize_class_name(appt.name))`
- `src/wodplanner/services/schedule.py:34-61` — `normalize_class_name`, `get_all_class_aliases`
- `src/wodplanner/services/calendar_sync.py:51-66` — private `_lookup_schedule` helper
- `src/wodplanner/app/routers/views.py:646` — schedule_modal_view direct call

**Problem**
"Given Appointment with Class Type X on date D, find matching Schedule" rule lives in three places. `calendar_view.py` does fallback lookup inline. `calendar_sync.py` wraps `find_for_appointment` in a try/except local helper. Schedule modal hits service directly. Normalization (`normalize_class_name`) leaks at call sites — caller must remember to fall back. Forget fallback, miss Schedule.

**Solution sketch**
One deepened lookup module: `match_schedule(appt, date) -> Schedule | None` owns alias map + normalization fallback + try/except + logging. Callers go to one line.

**Concept**
Schedule lookup rule. Already first-class in `CONTEXT.md` ("Matched to an Appointment at render time by `(date, class_type)`"). Not yet a module.

**Benefit**
Locality of the join rule; one test for "alias maps + normalization fallback both find the Schedule". Future additions (recurring weekly fallback, regex aliases) land in one place.

---

## 3. Sign Up + Google Calendar Sync orchestration repeated in three handlers

**Files**
- `src/wodplanner/app/routers/views.py:417-448` — subscribe_view
- `src/wodplanner/app/routers/views.py:451-482` — waitinglist_view
- `src/wodplanner/app/routers/views.py:485-521` — unsubscribe_view

**Problem**
Three handlers, near-identical body: parse datetimes → call `client.subscribe` / `subscribe_waitinglist` / `unsubscribe[_waitinglist]` → `_enqueue_google_sync` → re-render `calendar_day_partial`. Six dependencies injected per handler. Composition "Sign Up an Appointment + trigger Google Calendar Sync" is a domain concept (per `CONTEXT.md` example dialogue), but lives in routers. Tests must wire all six fakes per endpoint.

**Solution sketch**
`SubscriptionService.subscribe(appt_id, when, mode)` (mode ∈ {direct, waitlist, cancel, cancel_waitlist}). Router becomes thin parse-and-render shell. "Sign-up triggers sync" rule has one home.

**Concept**
Sign Up (existing `CONTEXT.md` term). Composition rule: sign-up triggers Google Calendar Sync.

**Benefit**
One test that asserts "subscribe enqueues sync". Routers stop being orchestrators. Real seam: future "sign-up triggers Slack notification" plugs in here, not in three handlers.

---

## 4. WodApp reservation dict shape leaks past API-client seam

**Files**
- `src/wodplanner/api/client.py` — `get_upcoming_reservations` returns `list[dict]`
- `src/wodplanner/services/calendar_sync.py:187-260` — indexes `reservation["name"]`, `reservation["date_start"]`, `reservation.get("date_end")`, `reservation["id_appointment"]`
- `src/wodplanner/app/routers/views.py` — home_page builds dicts from same keys

**Problem**
`WodAppClient` returns parsed `Appointment` models for `get_day_schedule()` but raw `dict` for `get_upcoming_reservations()`. Two callers index those keys directly. ADR-0001 already flags WodApp's contract as silently breakable — leaking the dict shape across non-client modules amplifies blast radius of an upstream rename.

**Solution sketch**
Add `Reservation` Pydantic model alongside `Appointment`. Client parses once. Callers hold a model.

**Concept**
Reservation — sub-case of Sign Up: current user's signed-up future Appointments. Not yet in `CONTEXT.md`. Add if adopted.

**Benefit**
One place reads `id_appointment` / `date_start` / `name`; rest of code holds a model. Aligns with existing `Appointment` modelling. Limits blast radius of WodApp API drift.

---

## 5. `is_signup_open`, `has_1rm_exercise` — pure functions with no test surface

**Files**
- `src/wodplanner/services/calendar_view.py:19-26` — `is_signup_open`: 14-day vs 7-day rule via substring `"CF101" or "101" in appt_name`
- `src/wodplanner/services/one_rep_max.py:79-87` — `has_1rm_exercise`
- `src/wodplanner/services/calendar_view.py:51-55` — three OR-ed calls across Schedule fields

**Problem**
Both pure helpers, easy to unit-test in isolation. Real bugs hide in *use*. `is_signup_open` keys off appointment-name substring (`"101" in appt_name`) — fragile, untested at call site (only called from inside `build_calendar_view`). `has_1rm_exercise` invoked three times in a row across three Schedule fields; call site, not function, holds the rule "Schedule flags a 1RM if any of {warmup, strength, metcon} matches".

**Solution sketch**
Roll both rules into the Day Card module (candidate 1). Card interface owns `signup_open: bool`, `has_1rm: bool`. Pure helpers stay private.

**Concept**
- Sign-Up window rule (not in `CONTEXT.md`; CF101 has early 14-week window).
- 1RM-flagged Appointment rule (also missing).

Add both to `CONTEXT.md` if adopted.

**Benefit**
Tests assert "Card.signup_open true 7 days before non-CF101, 14 weeks before CF101" without reaching for `WodAppClient`. 1RM-flag rule has one definition, not a copy-pasted OR chain.

---

## Skipped

- **Per-service connection lifecycle** (`src/wodplanner/services/base.py:19-20`). Single-process single-node SQLite (ADR-0003) makes a UnitOfWork seam over-engineered. Two-call atomicity not required today.
- **WodApp client coupling generally**. ADR-0001 acknowledges fragility; existing `Appointment` / `Member` models right shape, just incomplete (see candidate 4).

---

## Recommended ordering

1. **#2 Schedule lookup** — smallest, unblocks #1.
2. **#1 Day Card** — absorbs #5 (sign-up window + 1RM flag rules become Card interface).
3. **#4 Reservation model** — independent, low-risk, narrows ADR-0001 blast radius.
4. **#3 SubscriptionService** — separate work; touches three router handlers.
