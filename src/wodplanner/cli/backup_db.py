"""CLI tool for backing up the SQLite database."""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path


MAX_BACKUPS = 7


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

    return dest


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
