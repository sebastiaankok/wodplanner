# Database

SQLite (`wodplanner.db`). Schema auto-created on first run.

## Tables

- `signup_queue` — includes `user_token` and `user_id` for scheduled job auth
- `friends` — scoped per `user_id`
- `preferences`
- `schedules` — unique on `(date, class_type)`
- `sessions` — `session_id`, `token`, `user_id`, `username`, `firstname`, `gym_id`, `gym_name`, `agenda_id`, `created_at`, `expires_at`
- `one_rep_maxes` — scoped per `user_id`; columns: `id`, `user_id`, `exercise`, `weight_kg`, `recorded_at` (ISO date), `notes`, `created_at`
