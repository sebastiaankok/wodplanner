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

- `friends` — scoped per `owner_user_id`; unique on `(owner_user_id, appuser_id)`
- `preferences` — scoped per `user_id`; primary key `(user_id, key)`; value is JSON-encoded. Known keys: `hidden_class_types` (JSON array of class type strings), `dismissed_tooltips` (JSON array of tooltip ID strings)
- `schedules` — scoped per `gym_id`; unique on `(date, class_type, gym_id)`; `gym_id` nullable for legacy rows imported before gym scoping was added
- `exercises` — canonical list of 1RM exercise names; columns: `id`, `name` (UNIQUE), `created_at`; seeded with 28 predefined exercises on first run if table is empty; extended via `add-1rm` CLI
- `one_rep_maxes` — scoped per `user_id`; columns: `id`, `user_id`, `exercise` (must match a name in `exercises`), `weight_kg`, `recorded_at` (ISO date), `notes`, `created_at`

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
