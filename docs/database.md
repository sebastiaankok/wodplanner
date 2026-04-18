# Database

SQLite (`wodplanner.db`). Schema auto-created on first run.

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
- `preferences` — scoped per `user_id`; primary key `(user_id, key)`; value is JSON-encoded
- `schedules` — scoped per `gym_id`; unique on `(date, class_type, gym_id)`; `gym_id` nullable for legacy rows imported before gym scoping was added
- `one_rep_maxes` — scoped per `user_id`; columns: `id`, `user_id`, `exercise`, `weight_kg`, `recorded_at` (ISO date), `notes`, `created_at`

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
