import sqlite3

from wodplanner.cli.backup_db import backup, rotate


class TestBackup:
    def test_backup_creates_file(self, tmp_path):
        db_path = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"

        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO test VALUES (1), (2)")
        conn.commit()
        conn.close()

        result = backup(db_path, backup_dir)

        assert result.exists()
        assert result.name.startswith("wodplanner_")
        assert result.name.endswith(".db")

    def test_backup_preserves_data(self, tmp_path):
        db_path = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"

        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'alice'), (2, 'bob')")
        conn.commit()
        conn.close()

        result = backup(db_path, backup_dir)

        conn2 = sqlite3.connect(result)
        rows = conn2.execute("SELECT * FROM test ORDER BY id").fetchall()
        conn2.close()

        assert len(rows) == 2
        assert rows[0] == (1, "alice")
        assert rows[1] == (2, "bob")

    def test_backup_creates_backup_dir(self, tmp_path):
        db_path = tmp_path / "source.db"
        backup_dir = tmp_path / "newdir" / "nested"

        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()

        result = backup(db_path, backup_dir)

        assert result.exists()
        assert backup_dir.exists()


class TestRotate:
    def test_rotate_keeps_all_when_under_limit(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        (backup_dir / "wodplanner_20260101_120000.db").touch()
        (backup_dir / "wodplanner_20260102_120000.db").touch()

        deleted = rotate(backup_dir, keep=5)

        assert len(deleted) == 0
        assert len(list(backup_dir.glob("wodplanner_*.db"))) == 2

    def test_rotate_deletes_old_backups(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        (backup_dir / "wodplanner_20260101_120000.db").touch()
        (backup_dir / "wodplanner_20260102_120000.db").touch()
        (backup_dir / "wodplanner_20260103_120000.db").touch()
        (backup_dir / "wodplanner_20260104_120000.db").touch()
        (backup_dir / "wodplanner_20260105_120000.db").touch()
        (backup_dir / "wodplanner_20260106_120000.db").touch()
        (backup_dir / "wodplanner_20260107_120000.db").touch()
        (backup_dir / "wodplanner_20260108_120000.db").touch()

        deleted = rotate(backup_dir, keep=5)

        assert len(deleted) == 3
        remaining = list(backup_dir.glob("wodplanner_*.db"))
        assert len(remaining) == 5

    def test_rotate_keeps_most_recent(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        for i in range(1, 8):
            (backup_dir / f"wodplanner_2026010{i}_120000.db").touch()

        rotate(backup_dir, keep=3)

        remaining = sorted(f.name for f in backup_dir.glob("wodplanner_*.db"))
        assert len(remaining) == 3
        assert "wodplanner_20260105_120000.db" in remaining
        assert "wodplanner_20260107_120000.db" in remaining