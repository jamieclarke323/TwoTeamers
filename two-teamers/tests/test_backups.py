import json
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys

import pytest

from backup_database import create_backup, restore_copy, verify_backup
from cleanup_retention import cleanup
from test_offline import offline_app


def test_backup_is_private_consistent_and_restores_without_overwriting(tmp_path, offline_app):
    database = Path(offline_app.config["DATABASE"])
    key = tmp_path / "key.pem"
    key.write_text("test-only-key")
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO guest_progress (visitor_id, quiz_id) VALUES ('sample', 'quiz')")
    backup = create_backup(database, tmp_path / "backups", key)
    assert stat.S_IMODE(backup.stat().st_mode) == 0o700
    for name in ("database.sqlite", "vapid-private.pem", "manifest.json"):
        assert stat.S_IMODE((backup / name).stat().st_mode) == 0o600
    assert verify_backup(backup)["files"]
    recovered = tmp_path / "recovered.sqlite"
    restore_copy(backup, recovered)
    with sqlite3.connect(recovered) as db:
        assert db.execute("SELECT COUNT(*) FROM guest_progress").fetchone()[0] == 1
    with pytest.raises(FileExistsError):
        restore_copy(backup, recovered)
    (backup / "vapid-private.pem").write_text("changed")
    with pytest.raises(ValueError, match="checksum"):
        verify_backup(backup)


def test_backup_refuses_public_repository_location(offline_app):
    from backup_database import PROJECT
    with pytest.raises(ValueError, match="outside the repository"):
        create_backup(Path(offline_app.config["DATABASE"]), PROJECT / "static" / "backups")


def test_weekly_due_guard_skips_second_snapshot(tmp_path, offline_app):
    from backup_database import PROJECT
    destination = tmp_path / "weekly"
    arguments = [
        sys.executable, str(PROJECT / "backup_database.py"),
        "--database", offline_app.config["DATABASE"], "--destination", str(destination), "--if-due",
    ]
    first = subprocess.run(arguments, check=True, capture_output=True, text=True)
    second = subprocess.run(arguments, check=True, capture_output=True, text=True)
    assert "backup created" in first.stdout
    assert "no new snapshot needed" in second.stdout
    assert len(list(destination.glob("backup-*"))) == 1


def test_retention_is_preview_first_and_requires_fresh_matching_backup(tmp_path, offline_app):
    database = Path(offline_app.config["DATABASE"])
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO guest_progress (visitor_id, quiz_id, updated_at) VALUES ('old', 'quiz', datetime('now', '-91 days'))")
        db.execute("INSERT INTO guest_progress (visitor_id, quiz_id) VALUES ('recent', 'quiz')")
    assert cleanup(database)["guest_progress"] == 1
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM guest_progress").fetchone()[0] == 2
    with pytest.raises(ValueError, match="backup"):
        cleanup(database, apply=True)
    backup = create_backup(database, tmp_path / "backups")
    assert cleanup(database, apply=True, backup=backup)["guest_progress"] == 1
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT visitor_id FROM guest_progress").fetchall() == [("recent",)]
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["created_at"] -= 2 * 86400
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="24 hours"):
        cleanup(database, apply=True, backup=backup)
