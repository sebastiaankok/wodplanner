"""CLI tool for backing up the SQLite database."""

import argparse
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

MAX_BACKUPS = 7

logger = logging.getLogger(__name__)


def backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"wodplanner_{timestamp}.db"

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    _verify_backup(dest)
    return dest


def _verify_backup(dest: Path) -> None:
    """Run integrity + FK checks on the backup; delete it if either fails."""
    conn = sqlite3.connect(dest)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            logger.error("Backup %s failed integrity_check: %s", dest, integrity)
            _discard(dest)
            return
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            logger.error("Backup %s has %d FK violations", dest, len(fk_violations))
            _discard(dest)
            return
    finally:
        conn.close()


def _discard(dest: Path) -> None:
    dest.unlink(missing_ok=True)


def rotate(backup_dir: Path, keep: int = MAX_BACKUPS) -> list[Path]:
    backups = sorted(backup_dir.glob("wodplanner_*.db"))
    to_delete = backups[:-keep] if len(backups) > keep else []
    for f in to_delete:
        f.unlink()
    return to_delete


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup the wodplanner SQLite database")
    parser.add_argument("--db-path", default="/data/wodplanner.db", type=Path)
    parser.add_argument("--backup-dir", default="/data/backups", type=Path)
    parser.add_argument("--keep", default=MAX_BACKUPS, type=int, help="Max backups to keep")
    args = parser.parse_args()

    dest = backup(args.db_path, args.backup_dir)
    print(f"Backup written: {dest}")

    deleted = rotate(args.backup_dir, keep=args.keep)
    for f in deleted:
        print(f"Deleted old backup: {f}")
