# Database

SQLite (`wodplanner.db`). Schema auto-created on first run.

## Tables

- `friends` — scoped per `user_id`
- `preferences`
- `schedules` — unique on `(date, class_type)`
- `one_rep_maxes` — scoped per `user_id`; columns: `id`, `user_id`, `exercise`, `weight_kg`, `recorded_at` (ISO date), `notes`, `created_at`

## Auth

Sessions are stored client-side in a signed `session` cookie (itsdangerous `URLSafeTimedSerializer`). No sessions table in the database.
