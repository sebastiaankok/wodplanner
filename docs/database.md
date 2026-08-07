# Database

SQLite (`wodplanner.db`). Schema created and upgraded by migration registry on first run.

## Schema migrations

Schema lives in a central registry (`services/migrations.py`), not inline in service constructors. Each service module registers its migrations at import time; the registry applies pending ones once per process per db_path.

### Registration

Services call `migrations.register(version, description, sql_or_callable)` at module load. `sql` is either a SQL string (run via `executescript`) or a callable `(conn) -> None` for procedural migrations (e.g. column-presence checks).

Version ranges per service (keep grouped, avoid collisions):

| Range | Service |
|-------|---------|
| 100–199 | `schedule` |
| 200–299 | `friends` |
| 300–399 | `preferences` |
| 400–499 | `one_rep_max` |
| 500–599 | *(reserved — was `google_accounts`)* |
| 600–699 | `benchmark` |
| 700–799 | `subscription_tracker` |
| 800–899 | `users` (single source of truth for user identity) |

### Applying migrations

- **App**: FastAPI lifespan handler in `app/main.py` calls `ensure_migrations(db_path)` at startup. Applied versions logged at INFO.
- **CLI tools** (`add-1rm`, `import-schedule`): call `ensure_migrations(db_path)` before using any service.
- **Tests**: use `migrations._reset_for_tests()` to clear the process-level applied-paths cache when re-using a DB path across fixtures.

`ensure_migrations` is idempotent — locked, once per (process, resolved db_path). Service constructors do **not** run migrations; constructing a service against an un-migrated DB will fail on first query.

### `schema_migrations` table

Tracks which versions have been applied:

| Column | Type |
|--------|------|
| `version` | INTEGER PRIMARY KEY |
| `description` | TEXT |
| `applied_at` | TEXT (ISO timestamp) |

On an existing pre-registry prod DB (schema already in final state, no `schema_migrations` table yet), baseline migrations re-run as no-ops: `CREATE TABLE IF NOT EXISTS` skips, seed migrations check row count, ALTER-path migrations check column existence. Data is preserved; all versions are then recorded as applied.

### Adding a new migration

1. Pick the next free version in the service's range.
2. Add a `_migrate_vNNN(conn)` function (or raw SQL string) in the service module.
3. Call `migrations.register(NNN, "short description", _migrate_vNNN)` at module scope.
4. Migrations must be idempotent if they may collide with pre-existing final-state schemas — guard `ALTER`/`DROP` with `PRAGMA table_info` / `sqlite_master` checks.

## Connection settings

All connections go through `services/db.py:get_connection()`, which sets:

| Pragma | Value | Reason |
|--------|-------|--------|
| `journal_mode` | `WAL` | Concurrent readers never block writer; better crash recovery |
| `synchronous` | `NORMAL` | Safe with WAL, faster than `FULL` |
| `foreign_keys` | `ON` | Enforce referential integrity |
| `busy_timeout` | `5000` ms | Retry on write lock instead of immediate `OperationalError` |

WAL mode is persistent (stored in DB file header) — set once on first connection, stays active.

## Tables

- `users` — single source of truth for user identity. PK `id` = WodApp `user_id` (from session); also stores `appuser_id` (for member matching), `gym_id`, `display_name`, `avatar_filename`, `tracking_disabled`. Referenced by every user-scoped table via FK. Rows are populated lazily on first authenticated request.
- `friends` — scoped per `owner_user_id` (FK → `users`); unique on `(owner_user_id, appuser_id)`; soft-deletable via `deleted_at`
- `preferences` — scoped per `user_id` (FK → `users`); primary key `(user_id, key)`; value is JSON-encoded. Keeps only UI settings: `hidden_class_types`, `dismissed_tooltips`. Identity/tracking/avatar keys moved to `users`.
- `schedules` — scoped per `gym_id` (NOT NULL, default 0); unique on `(date, class_type, gym_id)`; index on `(date, gym_id)`; `created_at` is immutable, `updated_at` set on every upsert
- `exercises` — canonical list of 1RM exercise names; columns: `id`, `name` (UNIQUE), `created_at`, `updated_at`, `deleted_at`; seeded with 28 predefined exercises on first run if table is empty; extended via `add-1rm` CLI
- `one_rep_maxes` — scoped per `user_id` (FK → `users`); `exercise` FK → `exercises(name)`; columns: `id`, `user_id`, `exercise`, `weight_kg` (>0), `recorded_at`, `notes`, `created_at`, `updated_at`, `deleted_at`; indexes on `(user_id, exercise)` and `(user_id, recorded_at)`
- `benchmark_wods` — canonical list of benchmark WOD names; columns `id`, `name` (UNIQUE), `category`, `created_at`, `updated_at`, `deleted_at`
- `benchmark_results` — scoped per `user_id` (FK → `users`); `benchmark_name` FK → `benchmark_wods(name)`; columns `id`, `user_id`, `benchmark_name`, `time_seconds` (>0), `is_rx`, `recorded_at`, `created_at`, `updated_at`, `deleted_at`; index on `(user_id, benchmark_name)`
- `subscription_events` — event log, scoped per `user_id` (FK → `users`, ON DELETE CASCADE); no soft-delete; indexes on `(user_id, class_date)` and `(user_id, appointment_id)`

### Conventions

- **Soft deletes**: user-data and reference tables (`friends`, `one_rep_maxes`, `benchmark_results`, `exercises`, `benchmark_wods`) expose `deleted_at TEXT`. All SELECT queries filter `WHERE deleted_at IS NULL`; delete methods set `deleted_at` instead of issuing `DELETE`.
- **Audit timestamps**: all tables carry `created_at` (immutable) and `updated_at` (set on every change), stored as ISO-8601 `TEXT`.
- **Login-time creation**: `users` rows are created/updated at login time via `auth.login` (`UserService.upsert`). The `appuser_id` is later refined when the user's people modal discovers their ID via name-match. Never overwrites `tracking_disabled` or `avatar_filename`.


## Auth

Sessions are stored client-side in a signed `session` cookie (itsdangerous `URLSafeTimedSerializer`). No sessions table in the database.

Cookie behavior is controlled by environment variables in `app/config.py`:

| Variable | Default | Notes |
|----------|---------|-------|
| `ENVIRONMENT` | `development` | Set to `production` to auto-enable `COOKIE_SECURE` |
| `COOKIE_SECURE` | auto | `true` when `ENVIRONMENT=production`; explicit value overrides auto |
| `SESSION_EXPIRE_DAYS` | unset | Unset = never expire (browser max_age 400 days, no server-side signature expiry check) |
| `SECRET_KEY` | random | Set in production — random default invalidates all sessions on restart |

When `SESSION_EXPIRE_DAYS` is set, expiry is enforced both in the browser (`max_age`) and server-side by itsdangerous signature validation.

## Backups

Use the `backup-db` CLI — wraps SQLite's Online Backup API, safe during live writes. rsync is **not** safe (copies `.db`, `.db-wal`, `.db-shm` non-atomically).

```bash
# Default: /data/wodplanner.db → /data/backups/, keep 7
backup-db

# Custom paths / retention
backup-db --db-path /data/wodplanner.db --backup-dir /data/backups --keep 7
```

Backups are named `wodplanner_YYYYMMDD_HHMMSS.db`. Oldest files beyond `--keep` are deleted automatically.

## K8s / multi-pod notes

- **Recreate strategy**: safe — sequential pod access, no overlap.
- **Rolling update** (brief overlap): safe when both pods land on the same node with a `ReadWriteOnce` PVC. WAL + `busy_timeout` handles transient write contention.
- **ReadWriteMany / NFS**: not safe — SQLite `fcntl` locks are broken on many NFS implementations. Use PostgreSQL instead.
