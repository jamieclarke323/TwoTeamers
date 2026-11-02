"""Preview expired technical records; deletion requires confirmation and a fresh backup."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import time

from backup_database import PROJECT, source_id, verify_backup


def cleanup(database: Path, *, apply: bool = False, backup: Path | None = None) -> dict[str, int]:
    if not database.is_file():
        raise ValueError("Database does not exist.")
    if apply:
        if backup is None:
            raise ValueError("Deletion requires a verified backup created within the last 24 hours.")
        manifest = verify_backup(backup)
        age = time.time() - manifest["created_at"]
        if manifest["source_id"] != source_id(database) or not 0 <= age < 86400:
            raise ValueError("Backup must be for this database and less than 24 hours old.")
    rules = {
        "guest_progress": ("updated_at < datetime('now', '-90 days')", ()),
        "push_notification_deliveries": ("updated_at < datetime('now', '-90 days')", ()),
        "push_notification_sends": ("notification_date < date('now', '-90 days')", ()),
        "offline_sessions": ("created_at < ?", (int(time.time()) - 7 * 86400,)),
        "auth_attempts": ("attempted_at < ?", (int(time.time()) - 3600,)),
    }
    with sqlite3.connect(database) as db:
        db.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        counts = {}
        for table, (condition, parameters) in rules.items():
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            counts[table] = (
                db.execute(f"SELECT COUNT(*) FROM {table} WHERE {condition}", parameters).fetchone()[0]
                if exists else 0
            )
            if apply and counts[table]:
                db.execute(f"DELETE FROM {table} WHERE {condition}", parameters)
        if not apply:
            db.rollback()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path(os.environ.get(
        "DATABASE_PATH", str(PROJECT / "instance" / "two-teamers.sqlite")
    )))
    parser.add_argument("--confirm-delete", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    try:
        counts = cleanup(args.database, apply=args.confirm_delete, backup=args.backup)
        print("Deleted records:" if args.confirm_delete else "Preview only; no records deleted:")
        for table, count in counts.items():
            print(f"{table}: {count}")
    except (OSError, ValueError, sqlite3.Error, KeyError) as error:
        parser.exit(1, f"Retention operation failed: {error}\n")


if __name__ == "__main__":
    main()
