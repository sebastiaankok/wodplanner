"""End-to-end migration tests for the v800-v809 database redesign.

Simulates a production DB with the pre-redesign schema (all tables + data from
the 100-701 migrations) and verifies that applying v800-v809 preserves data and
installs the new constraints.
"""

import sqlite3

import pytest

from wodplanner.services import migrations
from wodplanner.services.users import UserService

_OLD_VERSIONS = [100, 200, 300, 400, 401, 600, 601, 602, 700, 701]


def _build_old_schema(path) -> None:
    """Create the pre-redesign schema with representative data and mark the old
    migrations as already applied so only v800+ run."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE preferences (
            user_id INTEGER NOT NULL DEFAULT 0,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );
        CREATE TABLE friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER NOT NULL DEFAULT 0,
            appuser_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            added_at TEXT NOT NULL,
            UNIQUE(owner_user_id, appuser_id)
        );
        CREATE TABLE exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE one_rep_maxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise TEXT NOT NULL,
            weight_kg REAL NOT NULL,
            recorded_at TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE benchmark_wods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE benchmark_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            benchmark_name TEXT NOT NULL,
            time_seconds INTEGER NOT NULL,
            is_rx INTEGER NOT NULL DEFAULT 1,
            recorded_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE subscription_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            appointment_id INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('subscribe', 'unsubscribe')),
            class_date TEXT NOT NULL,
            class_end TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_sub_events_user_date ON subscription_events(user_id, class_date);
        CREATE INDEX idx_sub_events_user_appt ON subscription_events(user_id, appointment_id);
        CREATE TABLE schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gym_id INTEGER,
            date DATE NOT NULL,
            class_type TEXT NOT NULL,
            warmup_mobility TEXT,
            strength_specialty TEXT,
            metcon TEXT,
            raw_content TEXT,
            source_file TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(date, class_type, gym_id)
        );
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, 'old', '2026-01-01T00:00:00')",
        [(v,) for v in _OLD_VERSIONS],
    )
    conn.executemany(
        "INSERT INTO preferences (user_id, key, value) VALUES (?, ?, ?)",
        [
            (77, "hidden_class_types", '["CrossFit"]'),
            (77, "dismissed_tooltips", '["welcome"]'),
            (77, "my_appuser_id", "8888"),
            (77, "tracking_disabled", "true"),
            (77, "avatar_filename", "ava_77.png"),
        ],
    )
    conn.execute(
        "INSERT INTO friends (owner_user_id, appuser_id, name, added_at) VALUES (77, 111, 'Alice', '2026-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO exercises (name, created_at) VALUES ('Back Squat', '2026-01-01T00:00:00')"
    )
    conn.execute(
        """
        INSERT INTO one_rep_maxes (user_id, exercise, weight_kg, recorded_at, notes, created_at)
        VALUES (77, 'Back Squat', 120.5, '2026-01-02', 'pr', '2026-01-02T00:00:00')
        """
    )
    conn.execute(
        "INSERT INTO benchmark_wods (name, category, created_at) VALUES ('Fran', 'The Girls', '2026-01-01T00:00:00')"
    )
    conn.execute(
        """
        INSERT INTO benchmark_results (user_id, benchmark_name, time_seconds, is_rx, recorded_at, created_at)
        VALUES (77, 'Fran', 360, 1, '2026-01-02', '2026-01-02T00:00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO subscription_events (user_id, appointment_id, class_name, event_type, class_date, class_end, created_at)
        VALUES (77, 501, 'CrossFit', 'subscribe', '2026-01-05', NULL, '2026-01-05T00:00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO schedules (gym_id, date, class_type, warmup_mobility, strength_specialty, metcon, raw_content, source_file, created_at)
        VALUES (NULL, '2026-01-01', 'CrossFit', NULL, NULL, 'AMRAP', NULL, 'Bull_202601.pdf', '2026-01-01T00:00:00')
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture
def migrated_db(tmp_path):
    migrations._reset_for_tests()
    path = tmp_path / "old.db"
    _build_old_schema(path)
    ran = migrations.ensure_migrations(path)
    assert set(ran) == {210, 800, 801, 802, 803, 804, 805, 806, 807, 808, 809, 810}
    return path


def _open(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def test_users_populated_from_existing_data(migrated_db):
    with _open(migrated_db) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = 77").fetchone()
    assert row is not None
    assert row["appuser_id"] == 8888
    assert row["tracking_disabled"] == 1
    assert row["avatar_filename"] == "ava_77.png"
    assert row["display_name"] is None
    assert row["gym_id"] is None


def test_migrated_keys_removed_from_preferences(migrated_db):
    with _open(migrated_db) as conn:
        keys = {r["key"] for r in conn.execute("SELECT key FROM preferences WHERE user_id = 77")}
    assert keys == {"hidden_class_types", "dismissed_tooltips"}


def test_user_scoped_tables_preserved_and_fk_installed(migrated_db):
    with _open(migrated_db) as conn:
        friends = conn.execute("SELECT * FROM friends").fetchone()
        orm = conn.execute("SELECT * FROM one_rep_maxes").fetchone()
        bmr = conn.execute("SELECT * FROM benchmark_results").fetchone()
        evts = conn.execute("SELECT * FROM subscription_events").fetchone()
        assert friends["owner_user_id"] == 77
        assert orm["weight_kg"] == 120.5
        assert bmr["time_seconds"] == 360
        assert evts["appointment_id"] == 501


def test_fk_to_users_present(migrated_db):
    with _open(migrated_db) as conn:
        for table in (
            "preferences",
            "friends",
            "one_rep_maxes",
            "benchmark_results",
            "subscription_events",
        ):
            parents = [r["table"] for r in conn.execute(f"PRAGMA foreign_key_list({table})")]
            assert "users" in parents, f"{table} should reference users"


def test_soft_delete_columns_present(migrated_db):
    with _open(migrated_db) as conn:
        for table in ("friends", "one_rep_maxes", "benchmark_results", "exercises", "benchmark_wods"):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            assert "deleted_at" in cols, f"{table} missing deleted_at"
        for table in ("one_rep_maxes", "benchmark_results", "exercises", "benchmark_wods", "schedules"):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            assert "updated_at" in cols, f"{table} missing updated_at"


def test_schedules_gym_id_null_migrated_to_zero(migrated_db):
    with _open(migrated_db) as conn:
        row = conn.execute("SELECT * FROM schedules").fetchone()
    assert row["gym_id"] == 0
    assert row["updated_at"] is not None


def test_fk_enforcement_unknown_user(migrated_db):
    with _open(migrated_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO one_rep_maxes (user_id, exercise, weight_kg, recorded_at, created_at, updated_at) VALUES (999, 'Back Squat', 1.0, '2026-01-01', 'x', 'x')"
            )


def test_fk_enforcement_unknown_exercise(migrated_db):
    with _open(migrated_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO one_rep_maxes (user_id, exercise, weight_kg, recorded_at, created_at, updated_at) VALUES (77, 'Does Not Exist', 1.0, '2026-01-01', 'x', 'x')"
            )


def test_check_constraint_negative_weight(migrated_db):
    with _open(migrated_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO one_rep_maxes (user_id, exercise, weight_kg, recorded_at, created_at, updated_at) VALUES (77, 'Back Squat', -5.0, '2026-01-01', 'x', 'x')"
            )


def test_on_delete_cascade_removes_user_data(migrated_db):
    with _open(migrated_db) as conn:
        conn.execute("DELETE FROM users WHERE id = 77")
        conn.commit()
        for table, col in (
            ("preferences", "user_id"),
            ("friends", "owner_user_id"),
            ("one_rep_maxes", "user_id"),
            ("benchmark_results", "user_id"),
            ("subscription_events", "user_id"),
        ):
            count = conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {col} = 77"
            ).fetchone()["c"]
            assert count == 0, f"{table} rows not cascaded"


def test_on_update_cascade_renames_exercise(migrated_db):
    with _open(migrated_db) as conn:
        conn.execute("UPDATE exercises SET name = 'Back Squat 2.0' WHERE name = 'Back Squat'")
        conn.commit()
        orm = conn.execute("SELECT * FROM one_rep_maxes").fetchone()
        assert orm["exercise"] == "Back Squat 2.0"


class TestUserService:
    def test_upsert_creates_row(self, db_path):
        svc = UserService(db_path)
        svc.upsert(user_id=1, appuser_id=42, gym_id=7, display_name="Bob")
        u = svc.get(1)
        assert u is not None
        assert u.appuser_id == 42
        assert u.gym_id == 7
        assert u.display_name == "Bob"

    def test_upsert_does_not_overwrite_tracking_or_avatar(self, db_path):
        svc = UserService(db_path)
        svc.upsert(user_id=1, appuser_id=42, gym_id=7, display_name="Bob")
        svc.set_tracking_disabled(1, True)
        svc.set_avatar_filename(1, "a.png")
        created_after_first = svc.get(1).created_at
        svc.upsert(user_id=1, appuser_id=99, gym_id=8, display_name="Robert")
        u = svc.get(1)
        assert u.tracking_disabled is True
        assert u.avatar_filename == "a.png"
        assert u.appuser_id == 99
        assert u.gym_id == 8
        assert u.created_at == created_after_first

    def test_upsert_preserves_appuser_id_when_null(self, db_path):
        """appuser_id must not be overwritten with NULL (breaks friend avatar lookup)."""
        svc = UserService(db_path)
        svc.upsert(user_id=1, appuser_id=42, gym_id=7, display_name="Bob")
        svc.upsert(user_id=1, appuser_id=None, gym_id=7, display_name="Bob")
        u = svc.get(1)
        assert u.appuser_id == 42

    def test_get_avatar_filenames_by_appuser_ids(self, db_path):
        svc = UserService(db_path)
        svc.upsert(user_id=5, appuser_id=100, gym_id=1, display_name="x")
        svc.upsert(user_id=6, appuser_id=200, gym_id=1, display_name="y")
        svc.set_avatar_filename(5, "five.png")
        result = svc.get_avatar_filenames_by_appuser_ids([100, 200, 300])
        assert result[100] == "five.png"
        assert 200 not in result
        assert 300 not in result

    def test_tracking_disabled_roundtrip(self, db_path):
        svc = UserService(db_path)
        assert svc.is_tracking_disabled(1) is False
        svc.upsert(user_id=1, appuser_id=42, gym_id=7, display_name="Bob")
        svc.set_tracking_disabled(1, True)
        assert svc.is_tracking_disabled(1) is True

    def test_avatar_roundtrip(self, db_path):
        svc = UserService(db_path)
        svc.upsert(user_id=1, appuser_id=42, gym_id=7, display_name="Bob")
        assert svc.get_avatar_filename(1) is None
        svc.set_avatar_filename(1, "b.png")
        assert svc.get_avatar_filename(1) == "b.png"
        svc.delete_avatar_filename(1)
        assert svc.get_avatar_filename(1) is None
