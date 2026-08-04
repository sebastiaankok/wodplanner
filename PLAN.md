# Database Redesign Plan

## Design Principles

1. **Single source of truth for user identity** — new `users` table, FK-referenced by all user-scoped tables
2. **Referential integrity** — FK constraints with `ON UPDATE CASCADE` / `ON DELETE CASCADE` / `ON DELETE RESTRICT`
3. **Soft deletes** — `deleted_at TEXT` on user-data and reference tables; queries filter `WHERE deleted_at IS NULL`
4. **Audit timestamps** — `created_at` (immutable) and `updated_at` (set on every change)
5. **Indexes** — every table indexed on its primary access path
6. **CHECK constraints** — guard against impossible values
7. **Consistent types** — all dates/timestamps as `TEXT` (ISO 8601)
8. **Lazy population** — `users` table populated on first authenticated request via `require_session` / `require_session_for_view`, not on login

## Target Schema

```
users (NEW — v800/v801)
├── id INTEGER PRIMARY KEY              -- WodApp user_id (from session)
├── appuser_id INTEGER UNIQUE           -- WodApp appuser_id (for member matching)
├── gym_id INTEGER                      -- user's default gym
├── display_name TEXT                   -- from WodApp firstname
├── avatar_filename TEXT                -- moved from preferences
├── tracking_disabled INTEGER NOT NULL DEFAULT 0  -- moved from preferences
├── created_at TEXT NOT NULL
└── updated_at TEXT NOT NULL

preferences (MODIFIED — v802, keeps only UI settings)
├── user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── key TEXT NOT NULL                   -- hidden_class_types, dismissed_tooltips
├── value TEXT NOT NULL                 -- JSON-encoded
└── PRIMARY KEY (user_id, key)
[Removed keys: my_appuser_id, tracking_disabled, avatar_filename → moved to users]

schedules (MODIFIED — v807)
├── gym_id INTEGER NOT NULL DEFAULT 0   -- was nullable, now NOT NULL (fixes NULL UNIQUE bug)
├── created_at TEXT NOT NULL            -- immutable on upsert
├── updated_at TEXT NOT NULL            -- new, set on every upsert
├── UNIQUE(date, class_type, gym_id)
└── INDEX(date, gym_id)                 -- new

friends (MODIFIED — v803)
├── owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── deleted_at TEXT                     -- new, soft delete
├── INDEX(owner_user_id)               -- new
└── UNIQUE(owner_user_id, appuser_id)

exercises (MODIFIED — v808)
├── deleted_at TEXT                     -- new, soft delete
└── updated_at TEXT                     -- new

one_rep_maxes (MODIFIED — v804)
├── user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── exercise TEXT NOT NULL REFERENCES exercises(name) ON UPDATE CASCADE ON DELETE RESTRICT
├── weight_kg REAL NOT NULL CHECK(weight_kg > 0)
├── deleted_at TEXT                     -- new, soft delete
├── updated_at TEXT NOT NULL            -- new
├── INDEX(user_id, exercise)            -- new
└── INDEX(user_id, recorded_at)         -- new

benchmark_wods (MODIFIED — v809)
├── deleted_at TEXT                     -- new, soft delete
└── updated_at TEXT                     -- new

benchmark_results (MODIFIED — v805)
├── user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
├── benchmark_name TEXT NOT NULL REFERENCES benchmark_wods(name) ON UPDATE CASCADE ON DELETE RESTRICT
├── time_seconds INTEGER NOT NULL CHECK(time_seconds > 0)
├── is_rx INTEGER NOT NULL DEFAULT 1 CHECK(is_rx IN (0, 1))
├── deleted_at TEXT                     -- new, soft delete
├── updated_at TEXT NOT NULL            -- new
└── INDEX(user_id, benchmark_name)      -- new

subscription_events (MODIFIED — v806)
├── user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
[No soft-delete — event log; no other changes]

schema_migrations (unchanged)
```

## Lazy Population Strategy

**Where:** `require_session` (`dependencies.py:78`) and `require_session_for_view` (`dependencies.py:94`)

Both receive `AuthSession` from the cookie, which carries `user_id`, `appuser_id`, `gym_id`, and `firstname`. After session validation, before returning, call:

```python
user_service.upsert(
    user_id=session.user_id,
    appuser_id=session.appuser_id,
    gym_id=session.gym_id,
    display_name=session.firstname,
)
```

The upsert SQL:

```sql
INSERT INTO users (id, appuser_id, gym_id, display_name, tracking_disabled, created_at, updated_at)
VALUES (?, ?, ?, ?, 0, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    appuser_id = excluded.appuser_id,
    gym_id = excluded.gym_id,
    display_name = excluded.display_name,
    updated_at = excluded.updated_at
```

This updates `appuser_id`, `gym_id`, and `display_name` from the session on every request (keeping them fresh if the user changes gyms or name in WodApp). It does **not** overwrite `tracking_disabled` or `avatar_filename` — those are user-managed.

**Removal condition:** Once `SELECT COUNT(*) FROM users WHERE display_name IS NULL OR gym_id IS NULL` returns 0, the upsert call can be removed from `require_session`. After removal, `display_name` and `gym_id` become static (won't auto-update from WodApp changes). Acceptable tradeoff for this app.

> **Note (decision, 2026-08-04):** the count will never reach 0 on its own because of legacy rows (e.g. `user 0` from the single-user era and stale rows like `309755`) that no real session will ever populate. Decision: **keep the per-request upsert in `require_session` indefinitely** (negligible cost for this low-traffic app) and leave those rows in place. If the removal condition is ever revisited, it should count only session-created users (e.g. `WHERE id != 0`).

## Migration Plan

All new migrations use version range **800–899**. They run after all existing migrations (100–701).

| Version | Description | Approach |
|---------|-------------|----------|
| **v800** | Create `users` table | `CREATE TABLE IF NOT EXISTS` |
| **v801** | Populate `users` from existing data + clean preferences | Procedural: collect distinct `user_id` from `preferences`, `friends`, `one_rep_maxes`, `benchmark_results`, `subscription_events`. For each, extract `my_appuser_id` / `tracking_disabled` / `avatar_filename` from `preferences` if present. Insert into `users` (`display_name` and `gym_id` left NULL — filled by lazy population). Delete migrated keys from `preferences`. |
| **v802** | Recreate `preferences` with FK to `users` | Create `preferences_new` with FK, copy remaining keys (`hidden_class_types`, `dismissed_tooltips`), drop old, rename. |
| **v803** | Recreate `friends` with FK + soft-delete + index | Create `friends_new`, copy data (`deleted_at = NULL`), drop old, rename, create index. |
| **v804** | Recreate `one_rep_maxes` with FK + CHECK + soft-delete + indexes + updated_at | FK to `users(id)` and `exercises(name) ON UPDATE CASCADE`. |
| **v805** | Recreate `benchmark_results` with FK + CHECK + soft-delete + index + updated_at | FK to `users(id)` and `benchmark_wods(name) ON UPDATE CASCADE`. |
| **v806** | Recreate `subscription_events` with FK to `users` | Keep existing indexes. FK to `users(id) ON DELETE CASCADE`. |
| **v807** | Recreate `schedules` — fix NULL `gym_id`, add `updated_at`, add index | Create `schedules_new` with `gym_id INTEGER NOT NULL DEFAULT 0`, copy data (NULL → 0), drop old, rename, create index. |
| **v808** | Add `deleted_at` + `updated_at` to `exercises` | `ALTER TABLE exercises ADD COLUMN` (2 statements) |
| **v809** | Add `deleted_at` + `updated_at` to `benchmark_wods` | `ALTER TABLE benchmark_wods ADD COLUMN` (2 statements) |

All recreate-and-copy migrations must:

- Check whether the table already has the new schema (idempotent for pre-existing prod DBs)
- Preserve all existing data
- Be wrapped in a single migration function

## Application Code Changes

### New `UserService` (`services/users.py`)

- `upsert(user_id, appuser_id, gym_id, display_name)` — called from `require_session` / `require_session_for_view`
- `get(user_id) -> User | None`
- `get_avatar_filename(user_id) -> str | None`
- `get_avatar_filenames_by_appuser_ids(appuser_ids) -> dict[int, str | None]` — single query: `SELECT appuser_id, avatar_filename FROM users WHERE appuser_id IN (...)`
- `is_tracking_disabled(user_id) -> bool`
- `set_tracking_disabled(user_id, disabled)`
- `set_avatar_filename(user_id, filename)` / `delete_avatar_filename(user_id)`

### `PreferencesService` changes

- **Remove:** `get_my_appuser_id`, `set_my_appuser_id`, `is_tracking_disabled`, `set_tracking_disabled`, `get_avatar_filename`, `set_avatar_filename`, `delete_avatar_filename`, `get_avatar_filenames`, `get_avatar_filenames_by_appuser_ids` — all moved to `UserService`
- **Keep:** `get_hidden_class_types`, `set_hidden_class_types`, `toggle_hidden_class_type`, `get_dismissed_tooltips`, `dismiss_tooltip`, `reset_tooltips`

### `dependencies.py` changes

- Add `get_user_service()` singleton (like existing service getters)
- Add `user_service` upsert call in `require_session` and `require_session_for_view` after session validation

### `views.py` changes

- Replace all `prefs_service.get_avatar_filename` / `is_tracking_disabled` / `get_my_appuser_id` calls with `user_service.*` equivalents
- `get_avatar_filenames_by_appuser_ids` simplifies from 3 queries to 1

### Service query changes (all user-data tables)

- Add `AND deleted_at IS NULL` to every SELECT in `FriendsService`, `OneRepMaxService`, `BenchmarkService`
- `get_exercise_list()`: add `WHERE deleted_at IS NULL`
- `BenchmarkService.get_benchmark_list()`: add `WHERE deleted_at IS NULL`
- Delete methods: change `DELETE FROM` to `UPDATE SET deleted_at = ?`
- `ScheduleService` upsert: stop overwriting `created_at` on conflict; set `updated_at` instead
- `ScheduleService` queries: replace `gym_id IS NULL` checks with `gym_id = 0`

### `backup-db` CLI

- After `src.backup(dst)`, run `PRAGMA integrity_check` and `PRAGMA foreign_key_check` on the destination
- If either fails, delete the backup file and log an error

### Dead code cleanup

- Remove `ScheduleService.find_for_appointment` (never called)
- Remove `BenchmarkService.get_benchmark_names_for_user` (never called)
- Remove `PreferencesService.get_for_user` / `get_all` (only used in tests)

### Documentation

- Update `docs/database.md` with all 10 tables (including `users`)
- Update migration version range table (add 600–699 benchmark, 700–799 subscription_tracker, 800–899 users)
- Document soft-delete convention, FK relationships, lazy population strategy, and removal condition

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Migration data loss | Every recreate-and-copy migration checks if new schema is already in place (idempotent). `ALTER TABLE ADD COLUMN` is non-destructive. |
| FK enforcement breaks existing data | v801 (populate users) runs before any FK migration. Any `user_id` in user-scoped tables without a `preferences` row → insert a placeholder `users` row with `user_id` only. |
| `exercises(name)` FK blocks renames | `ON UPDATE CASCADE` propagates renames to `one_rep_maxes.exercise`. |
| `benchmark_wods(name)` FK blocks renames | Same — `ON UPDATE CASCADE`. |
| Soft-delete changes query behavior | All queries explicitly filter `deleted_at IS NULL`. Existing tests updated. |
| `schedules` gym_id 0 vs NULL | Migrate NULL → 0 in v807. All queries change from `gym_id IS NULL` to `gym_id = 0`. |
| Per-request upsert cost | Single-row PK upsert — negligible for low-traffic app. Removable once all rows populated. |

## Testing Strategy

1. **Migration tests**: Create a test DB with old schema + sample data, run all migrations, verify data preserved and new constraints in place
2. **FK enforcement tests**: Insert `one_rep_maxes` row with non-existent `exercises.name` → expect `IntegrityError`
3. **Soft-delete tests**: Delete a friend, verify filtered from `get_all` but still in DB; verify `get` returns None
4. **Upsert test**: Upsert a schedule twice, verify `created_at` unchanged and `updated_at` updated
5. **Lazy population test**: Simulate `require_session_for_view` with a user not in `users` table, verify row created
6. **Backup verification test**: Create a backup, verify `PRAGMA integrity_check` passes

## Execution Order

1. Create `UserService` + `User` model
2. Write migrations v800–v809
3. Write migration tests
4. Update `dependencies.py` (add `get_user_service`, lazy upsert in `require_session` / `require_session_for_view`)
5. Update `PreferencesService` (remove migrated methods)
6. Update all service queries (soft-delete filters, updated_at, gym_id=0)
7. Update `views.py` (use `UserService` for avatars/tracking/identity)
8. Update `backup-db` CLI (integrity check)
9. Update `docs/database.md`
10. Clean up dead code
11. Run full test suite

