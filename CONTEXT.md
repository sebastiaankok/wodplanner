# WodPlanner

A personal tool that wraps the WodApp gym platform to add friends tracking, workout schedules, 1RM logging, and Google Calendar sync — features WodApp itself does not provide.

## Language

### External platform

**WodApp**:
The upstream gym management SaaS (`app.wodapp.nl / ws.paynplan.nl`) that WodPlanner wraps. WodApp owns all class scheduling and user account data; WodPlanner reads and acts on it via a reverse-engineered internal API.
_Avoid_: backend, API, upstream app

**Gym**:
The CrossFit facility registered in WodApp. WodPlanner is single-gym (CrossFit Purmerend, id 2495).
_Avoid_: club, box, location

### Classes and workouts

**Appointment**:
A gym class slot as returned by WodApp — has a time, capacity, participant list, and sign-up status. Live data; not stored locally.
_Avoid_: class, event, session

**Class Type**:
The name of an appointment as WodApp reports it (e.g. "CrossFit", "Olympic Lifting"). Used as the join key between Appointments and Schedules. Aliases are normalised via `CLASS_NAME_MAPPING`.
_Avoid_: class name, appointment name

**Schedule**:
Workout content (warmup/mobility, strength/specialty, metcon) for a specific date and Class Type. Parsed from the gym's PDF and stored locally. Matched to an Appointment at render time by `(date, class_type)`.
_Avoid_: workout, wod, programme

**Sign Up**:
The act of enrolling in an Appointment when spots are available.
_Avoid_: subscribe, register, reserve, book

**Waiting List**:
A queue joined when an Appointment is full. WodApp automatically promotes waiting members when a spot opens.
_Avoid_: waitlist, queue

### People

**Member**:
A WodApp user who is signed up for an Appointment. Has a name and a Member ID. Comes from `subscriptions.members[]` in the WodApp API.
_Avoid_: participant, athlete, user

**Friend**:
A Member whose class attendance the current user tracks. Stored locally per user; not a WodApp concept. Discovered by viewing participants in the people modal.
_Avoid_: contact, follower

**Account ID** (`user_id`):
WodApp's identifier for a user account. Sent as `id_appuser_li` in every API request for authentication. Does **not** match the Member ID and cannot be used to find the current user in a participant list.
_Avoid_: user ID (ambiguous)

**Member ID** (`appuser_id`):
WodApp's identifier for a user in participant lists (`id_appuser` in `subscriptions.members[]`). Used to detect friends in a class. Different from Account ID.
_Avoid_: user ID (ambiguous)

### Performance tracking

**1RM (One-Rep Max)**:
A CrossFit athlete's personal best weight for a single repetition of a lift (e.g. Back Squat 100 kg). When a Schedule contains a 1RM exercise, the calendar flags the Appointment so the user knows to bring their numbers.
_Avoid_: personal best, max lift

**Exercise**:
A named barbell or gymnastics movement with a canonical name (e.g. "Back Squat"). Stored in the `exercises` table; seeded with 28 defaults. Users log 1RMs against canonical Exercise names.
_Avoid_: movement, lift

### Integrations

**Google Calendar Sync**:
One-way push of the user's WodApp sign-ups to a Google Calendar. One-way because WodApp exposes no external write API for reservations.
_Avoid_: calendar integration, two-way sync

## Relationships

- An **Appointment** has a **Class Type**; a **Schedule** is looked up by `(date, Class Type)` to enrich it
- A **Friend** is a **Member** the user has chosen to track
- **Account ID** and **Member ID** are different values for the same WodApp user — never use Account ID to match against a participant list
- **Signing Up** for an **Appointment** triggers a **Google Calendar Sync** in the background
- A **Schedule** may reference a **1RM** exercise, which flags the corresponding **Appointment** on the calendar

## Example dialogue

> **Dev:** "When a user clicks 'sign up' on an Appointment, do we store anything locally?"
> **Domain expert:** "No — we call the WodApp subscribe endpoint and trigger a Google Calendar Sync. The Appointment itself is never persisted; next page load fetches it live."

> **Dev:** "How does the calendar know which Friends are in a class?"
> **Domain expert:** "We fetch the Appointment's Member list from WodApp and cross-reference it against the user's stored Friend Member IDs."

> **Dev:** "Why can't I use `session.user_id` to find myself in the participant list?"
> **Domain expert:** "Account ID and Member ID are different. `user_id` is for API auth; `id_appuser` in the member list is the Member ID. We discover the current user's Member ID once by name-matching and persist it."

## Flagged ambiguities

- **"user ID"** appears in both WodApp API docs and code with two distinct meanings. Resolved: use **Account ID** (`user_id`) for the auth credential and **Member ID** (`appuser_id`) for participant identity — never conflate them.
- **"class"** is used colloquially but overlaps with Python's `class` keyword. Resolved: use **Appointment** for the gym class slot and **Class Type** for its name.
