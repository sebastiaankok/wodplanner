"""Tests for cli/backup_db.py main()."""

import sqlite3

from wodplanner.cli import backup_db


class TestBackupDbMain:
    def test_runs_backup_and_rotate(self, monkeypatch, tmp_path, capsys):
        db = tmp_path / "src.db"
        backup_dir = tmp_path / "backups"

        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()

        # Pre-create old backups so rotate has something to delete
        backup_dir.mkdir()
        for i in range(1, 10):
            (backup_dir / f"wodplanner_2026010{i}_120000.db").touch()

        monkeypatch.setattr(
            "sys.argv",
            [
                "backup-db",
                "--db-path",
                str(db),
                "--backup-dir",
                str(backup_dir),
                "--keep",
                "3",
            ],
        )
        backup_db.main()
        out = capsys.readouterr().out
        assert "Backup written:" in out
        assert "Deleted old backup:" in out
